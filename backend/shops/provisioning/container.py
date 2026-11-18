"""
What every platform shares on the shop node from infra/shops: a shop is its own container behind
the Traefik proxy, with its files in a volume and a separate database in the shared MariaDB.
"""

import secrets
import time
from functools import cached_property

import docker
from django.conf import settings
from django.db.models import Count, F, Q
from docker.errors import NotFound

from ..models import Server, Shop, ShopCredentials
from .base import BaseProvisioner, ProvisioningError

# Where the platform's files live in the container, in the shop's volume.
FILES_PATH = "/var/www/html"


class CommandError(Exception):
    """A command inside a container failed. The message is for logs only: it may contain internals."""


class ContainerProvisioner(BaseProvisioner):
    """
    Base for platforms that run as one container per shop. Subclasses say which image to run with
    what environment, and which file shows the container is ready; they add the platform's own steps.
    """

    # Environment variables the platform's container is configured with; a change means a new container.
    ENV_KEYS = ()
    # Shown when the container doesn't get ready in time.
    START_FAILED = "Sklep nie wystartował."
    # Where the shop's volume is mounted: the platform's files, or only the shop's own data when the code is in the image.
    VOLUME_PATH = FILES_PATH
    # Seconds the container gets to become ready.
    START_TIMEOUT = 60

    @cached_property
    def client(self):
        # Lazy: the web process never runs steps and has no access to the Docker socket.
        return docker.from_env()

    # --- what subclasses define ---

    def image(self):
        raise NotImplementedError

    def container_environment(self, shop):
        raise NotImplementedError

    def ready_command(self):
        """A command that succeeds inside the container once its entrypoint has set things up."""
        raise NotImplementedError

    def default_admin_login(self, shop):
        raise NotImplementedError

    def memory(self, shop):
        """The container's memory limit, e.g. "512m"."""
        return container_memory(shop)

    # --- steps every platform has ---

    def step_allocate_server(self, shop):
        if shop.server_id:
            return
        server = (
            Server.objects.filter(is_active=True)
            .annotate(live_shops=Count("shops", filter=~Q(shops__status=Shop.Status.DELETED)))
            .filter(live_shops__lt=F("max_shops"))
            .first()
        )
        if server is None:
            raise ProvisioningError("Brak wolnego serwera. Spróbuj ponownie później.")
        shop.server = server
        shop.save(update_fields=["server", "updated_at"])

    def step_create_database(self, shop):
        credentials = self._credentials(shop)
        if not credentials.db_password:
            credentials.db_password = secrets.token_urlsafe(24)
            credentials.save(update_fields=["db_password", "updated_at"])
        name, password = db_name(shop), credentials.db_password
        # Safe to interpolate: name comes from the shop id, password from token_urlsafe.
        self._sql(
            f"CREATE DATABASE IF NOT EXISTS `{name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
            f"CREATE USER IF NOT EXISTS '{name}'@'%' IDENTIFIED BY '{password}';"
            f"ALTER USER '{name}'@'%' IDENTIFIED BY '{password}';"
            f"GRANT ALL PRIVILEGES ON `{name}`.* TO '{name}'@'%';"
        )

    def step_start_container(self, shop):
        name = container_name(shop)
        environment = self.container_environment(shop)
        labels = {
            "traefik.enable": "true",
            f"traefik.http.routers.{name}.rule": f"Host(`{shop.domain}`)",
            f"traefik.http.routers.{name}.entrypoints": "web",
            f"traefik.http.services.{name}.loadbalancer.server.port": "80",
            "shops.id": str(shop.pk),
            "shops.slug": shop.slug,
        }
        container = self._find_container(shop)
        # The files live in the volume, so a container with outdated env or Traefik labels (a new domain)
        # can be replaced without losing anything.
        memory = self.memory(shop)
        outdated = container is not None and (
            container_env(container, self.ENV_KEYS) != environment
            or not labels.items() <= container.labels.items()
            # A different plan means a different memory limit.
            or container.attrs.get("HostConfig", {}).get("Memory") != memory_bytes(memory)
            # A rebuilt image (e.g. new platform code) reaches running shops this way.
            or self._image_changed(container)
        )
        if outdated:
            container.remove(force=True)
            container = None
        if container is None:
            container = self.client.containers.run(
                self.image(),
                name=name,
                detach=True,
                network=settings.SHOPS_NETWORK,
                restart_policy={"Name": "unless-stopped"},
                mem_limit=memory,
                nano_cpus=1_000_000_000,
                volumes={name: {"bind": self.VOLUME_PATH, "mode": "rw"}},
                environment=environment,
                labels=labels,
            )
        container.start()
        for _ in range(self.START_TIMEOUT):
            if container.exec_run(self.ready_command()).exit_code == 0:
                return
            time.sleep(1)
        raise ProvisioningError(self.START_FAILED)

    def _check_pages(self, shop, checks):
        """Fetch `checks` ([(label, [curl args… url])]) through the proxy like a visitor would; each must be 200."""
        host = shop.url.split("://", 1)[1]
        for label, args in checks:
            status = self._exec(
                container_name(shop),
                ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "--max-time", "60", "-H", f"Host: {host}", *args],
            )
            if status != "200":
                raise ProvisioningError(f"Sklep nie odpowiada poprawnie ({label}: HTTP {status}).")

    @staticmethod
    def proxy_url(path="/"):
        return f"http://{settings.SHOPS_PROXY_CONTAINER}{path}"

    # --- lifecycle ---

    def cleanup(self, shop):
        # Keep everything: a retry continues from what's already there.
        pass

    def teardown(self, shop):
        container = self._find_container(shop)
        if container is not None:
            container.remove(force=True)
        try:
            self.client.volumes.get(container_name(shop)).remove(force=True)
        except NotFound:
            pass
        db = db_name(shop)
        self._sql(f"DROP DATABASE IF EXISTS `{db}`; DROP USER IF EXISTS '{db}'@'%';")

    def suspend(self, shop):
        container = self._find_container(shop)
        if container is not None:
            container.stop()

    def resume(self, shop):
        self.step_start_container(shop)

    def refresh_resources(self, shop):
        if self._find_container(shop) is not None:
            self.step_start_container(shop)

    def configure_mail(self, shop):
        relay = mail_relay(shop)
        if relay is None or self._find_container(shop) is None:
            return False
        # A container of an older image is replaced first, so the shop runs the current mail code.
        self.step_start_container(shop)
        self._configure_mail(shop, relay)
        return True

    def _configure_mail(self, shop, relay):
        """Point the platform at `relay` ({host, port, sender}); see mail_relay."""
        raise NotImplementedError

    # --- helpers ---

    def _credentials(self, shop):
        credentials, _ = ShopCredentials.objects.get_or_create(
            shop=shop, defaults={"admin_login": self.default_admin_login(shop)},
        )
        return credentials

    def _find_container(self, shop):
        try:
            return self.client.containers.get(container_name(shop))
        except NotFound:
            return None

    def _image_changed(self, container):
        try:
            return container.image.id != self.client.images.get(self.image()).id
        except NotFound:
            # The image is gone (e.g. renamed); keep the container rather than fail.
            return False

    def _write_file(self, shop, path, content):
        """Write `content` to `path` inside the shop's container, as the web server's user, creating folders."""
        # Through the environment, so the content needs no quoting.
        self._exec(
            container_name(shop),
            ["sh", "-c", 'mkdir -p "$(dirname "$FILE")" && printf "%s" "$CONTENT" > "$FILE"'],
            user="www-data",
            environment={"FILE": path, "CONTENT": content},
        )

    def _exec(self, container_name, command, user="", environment=None):
        container = self.client.containers.get(container_name)
        result = container.exec_run(command, user=user, environment=environment)
        output = result.output.decode(errors="replace").strip()
        if result.exit_code != 0:
            # Only the command name: arguments may contain passwords.
            # The start and the end: some tools put the cause first and their usage after it.
            excerpt = output if len(output) <= 3000 else f"{output[:1500]}\n…\n{output[-1500:]}"
            raise CommandError(f"{' '.join(command[:4])}… exited with {result.exit_code}: {excerpt}")
        return output

    def _sql(self, statement, database=None, raw=False):
        """Runs SQL as root; `raw` keeps values as they are (no \\n escapes), e.g. for JSON built in the query."""
        if not settings.SHOPS_DB_ROOT_PASSWORD:
            raise CommandError("SHOPS_DB_ROOT_PASSWORD is not set")
        return self._exec(
            settings.SHOPS_DB_CONTAINER,
            ["mariadb", "-uroot", "--batch", "--skip-column-names", *(["--raw"] if raw else []),
             *([database] if database else []), "-e", statement],
            environment={"MYSQL_PWD": settings.SHOPS_DB_ROOT_PASSWORD},
        )


def container_name(shop):
    # Keyed by id, not slug: a deleted shop's leftovers never clash with a new shop using the same slug.
    return f"shop-{shop.pk}"


def db_name(shop):
    return f"shop_{shop.pk}"


def mail_relay(shop):
    """Where the shop sends e-mail and from which address, or None when shops get no mail server."""
    if not settings.SHOPS_SMTP_HOST:
        return None
    return {"host": settings.SHOPS_SMTP_HOST, "port": settings.SHOPS_SMTP_PORT, "sender": shop.mail_sender}


def container_env(container, keys):
    """The container's values of `keys`; None for those it doesn't have."""
    pairs = (item.split("=", 1) for item in container.attrs["Config"]["Env"])
    current = dict(pair for pair in pairs if len(pair) == 2)
    return {key: current.get(key) for key in keys}


def container_memory(shop):
    """The owner's plan sets how much memory a shop gets; test shops and shops without a plan get the default."""
    from billing.models import Subscription

    subscription = Subscription.objects.select_related("plan").filter(user_id=shop.owner_id).first()
    if shop.is_test or subscription is None or subscription.status not in (
        Subscription.Status.ACTIVE, Subscription.Status.PAST_DUE,
    ):
        return settings.SHOPS_CONTAINER_MEMORY
    return f"{subscription.plan.shop_memory_mb}m"


def memory_bytes(limit):
    """Docker's memory limit in bytes for "512m" / "1g"."""
    units = {"k": 1024, "m": 1024 ** 2, "g": 1024 ** 3}
    limit = str(limit).lower()
    return int(limit[:-1]) * units[limit[-1]] if limit[-1] in units else int(limit)
