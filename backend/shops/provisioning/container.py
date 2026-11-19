"""
What every platform shares on the shop node from infra/shops: a shop is its own container behind
the Traefik proxy, with its files in a volume and a separate database in the shared MariaDB.
"""

import io
import json
import posixpath
import secrets
import tarfile
import time
from functools import cached_property

import docker
import requests
from django.conf import settings
from django.db.models import Count, F, Q
from django.utils.dateparse import parse_datetime
from docker.errors import DockerException, NotFound

from ..models import Server, Shop, ShopCredentials
from ..unavailable import UNAVAILABLE_HEADER
from .base import (
    Backup, BaseProvisioner, ContainerState, NothingToBackUp, PageCheck, ProvisioningError, Snapshot,
)

# Where the platform's files live in the container, in the shop's volume.
FILES_PATH = "/var/www/html"

# Where the backup container (infra/shops/backup) has the repository, restic's cache and the shop's volume.
BACKUP_REPOSITORY = "/repository"
BACKUP_CACHE = "/cache"
BACKUP_FILES = "/shop/files"
# Marks backup containers, with the shop's id ("" for work on the whole repository).
BACKUP_LABEL = "shops.backup"
# Marks shop containers, with the shop's id.
SHOP_LABEL = "shops.id"


class _Healthcheck(docker.types.Healthcheck):
    """docker-py's Healthcheck that keeps StartInterval."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        start_interval = kwargs.get("start_interval", kwargs.get("StartInterval"))
        if start_interval is not None:
            self["StartInterval"] = start_interval


# docker-py (7.2) rebuilds a container's healthcheck from the options it knows, which end at API 1.29, so it drops
# StartInterval (API 1.44) and a starting shop would be checked once a minute instead of every few seconds.
docker.types.containers.Healthcheck = _Healthcheck

# Docker's check of a shop's web server (seconds). Traefik sends visitors only to a healthy container, so a shop
# that is starting or hangs gets the platform's "temporarily unavailable" page instead of an error. While the shop
# starts, it is checked every few seconds and failures don't count; then once a minute, unhealthy after 3 failures.
HEALTH_INTERVAL = 60
HEALTH_TIMEOUT = 15
HEALTH_RETRIES = 3
HEALTH_START_PERIOD = 300
HEALTH_START_INTERVAL = 3
# How long the monitor's visit to a page may take (seconds).
PAGE_TIMEOUT = 20
# Seconds to wait for Traefik to send visitors to a container that just became healthy.
ROUTE_TIMEOUT = 30


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
    # Paths in the shop's volume left out of backups: caches the platform builds again by itself.
    BACKUP_EXCLUDES = ()
    # Seconds one backup or restore may take, waiting for a busy repository included (up to 30 minutes).
    BACKUP_TIMEOUT = 3600

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

    def after_restore(self, shop):
        """Bring what lives outside the shop's files and database (e.g. its search index) in line with them."""

    def healthcheck(self, shop):
        """
        Docker's healthcheck of the shop's container: its home page, as the shop's address. Any answer below 500
        counts, and 503 too, so a redirect or a closed shop (PrestaShop's maintenance mode) keeps its visitors.
        """
        host = shop.url.split("://", 1)[1]
        test = (
            f"code=$(curl -s -o /dev/null -w '%{{http_code}}' --max-time {HEALTH_TIMEOUT - 5} "
            f"-H 'Host: {host}' http://localhost/); "
            '[ "$code" = 503 ] || { [ "$code" -ge 200 ] && [ "$code" -lt 500 ]; }'
        )
        return {
            "Test": ["CMD-SHELL", test],
            "Interval": seconds(HEALTH_INTERVAL),
            "Timeout": seconds(HEALTH_TIMEOUT),
            "Retries": HEALTH_RETRIES,
            "StartPeriod": seconds(HEALTH_START_PERIOD),
            "StartInterval": seconds(HEALTH_START_INTERVAL),
        }

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
            SHOP_LABEL: str(shop.pk),
            "shops.slug": shop.slug,
        }
        container = self._find_container(shop)
        memory = self.memory(shop)
        healthcheck = self.healthcheck(shop)
        # The files live in the volume, so an outdated container can be replaced without losing anything.
        if container is not None and self._outdated(container, environment, labels, memory, healthcheck):
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
                healthcheck=healthcheck,
            )
        container.start()
        for _ in range(self.START_TIMEOUT):
            if container.exec_run(self.ready_command()).exit_code == 0:
                return
            time.sleep(1)
        raise ProvisioningError(self.START_FAILED)

    def container_outdated(self, shop):
        """Whether the shop's container is not as step_start_container would make it now (False without one)."""
        container = self._find_container(shop)
        if container is None:
            return False
        name = container_name(shop)
        labels = {f"traefik.http.routers.{name}.rule": f"Host(`{shop.domain}`)", SHOP_LABEL: str(shop.pk)}
        return self._outdated(
            container, self.container_environment(shop), labels, self.memory(shop), self.healthcheck(shop),
        )

    def _outdated(self, container, environment, labels, memory, healthcheck):
        current_health = container.attrs.get("Config", {}).get("Healthcheck") or {}
        return (
            # Outdated env or Traefik labels (a new domain).
            container_env(container, self.ENV_KEYS) != environment
            or not labels.items() <= container.labels.items()
            # A different plan means a different memory limit.
            or container.attrs.get("HostConfig", {}).get("Memory") != memory_bytes(memory)
            # Containers from before the healthcheck, or with an older one.
            or any(current_health.get(key) != value for key, value in healthcheck.items())
            # A rebuilt image (e.g. new platform code) reaches running shops this way.
            or self._image_changed(container)
        )

    def _wait_until_routed(self, shop, timeout=None):
        """
        Wait until the shop's container is healthy and Traefik sends visitors to it (it skips containers that are
        starting or unhealthy). Returns whether it happened within `timeout` seconds; the caller finds out what's wrong.
        """
        deadline = time.monotonic() + (timeout or HEALTH_START_PERIOD)
        container = self._find_container(shop)
        while container is not None and time.monotonic() < deadline:
            container.reload()
            health = (container.attrs.get("State", {}).get("Health") or {}).get("Status")
            if health is None:
                # A container from before the healthcheck: Traefik sends visitors to it as soon as it runs.
                return container.status == "running"
            if health == "healthy":
                break
            time.sleep(HEALTH_START_INTERVAL)
        else:
            return False
        # Traefik learns about the change from Docker's events, a moment later.
        routed_by = min(deadline, time.monotonic() + ROUTE_TIMEOUT)
        while True:
            if not self.check_page(shop).unavailable:
                return True
            if time.monotonic() >= routed_by:
                return False
            time.sleep(1)

    def _check_pages(self, shop, checks):
        """Fetch `checks` ([(label, [curl args… url])]) through the proxy like a visitor would; each must be 200."""
        # The shop may have just started: until its first healthcheck passes, the proxy shows the platform's page.
        self._wait_until_routed(shop)
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

    # --- backups: a throwaway container of infra/shops/backup does the work, next to the shop's volume ---

    def can_back_up(self):
        return bool(settings.SHOPS_BACKUP_PASSWORD)

    def backup(self, shop, tag):
        # Mounting a volume that isn't there would create an empty one.
        if not self._volume_exists(shop):
            raise NothingToBackUp()
        output = self._backup_tool(["backup", tag, *self.BACKUP_EXCLUDES], shop=shop, files="ro")
        summary = backup_summary(output)
        return Backup(snapshot_id=summary["snapshot_id"], size=summary["total_bytes_processed"])

    def restore_backup(self, shop, snapshot_id):
        container = self._find_container(shop)
        if container is not None:
            container.stop()
        # A deleted shop being brought back has no database or database user any more.
        self.step_create_database(shop)
        self._backup_tool(["restore", snapshot_id], shop=shop, files="rw")
        self.step_start_container(shop)
        self.after_restore(shop)
        # The backup may be from before the shop moved to another domain, got another mail relay or a new password.
        self.update_address(shop)
        self.configure_mail(shop)
        password = self._credentials(shop).admin_password
        if password:
            self.set_admin_password(shop, password)

    def list_backups(self):
        # Runs every night, so it also clears containers left behind by a worker that died waiting for one.
        for leftover in self.client.containers.list(all=True, filters={"label": BACKUP_LABEL, "status": "exited"}):
            leftover.remove(force=True)
        return [snapshot_of(item) for item in json.loads(self._backup_tool(["snapshots"]) or "[]")]

    def forget_backups(self, snapshot_ids):
        snapshot_ids = list(snapshot_ids)
        for start in range(0, len(snapshot_ids), 100):
            self._backup_tool(["forget", *snapshot_ids[start:start + 100]])

    def prune_backups(self):
        self._backup_tool(["prune"])

    # --- health: what the monitor checks (monitoring/) ---

    def can_monitor(self):
        return True

    def container_states(self):
        states = {}
        for container in self.client.containers.list(all=True, filters={"label": SHOP_LABEL}):
            try:
                shop_id = int(container.labels[SHOP_LABEL])
            except (KeyError, ValueError):
                continue
            state = container.attrs.get("State", {})
            health = (state.get("Health") or {}).get("Status")
            states[shop_id] = ContainerState(status=state.get("Status", container.status), health=health)
        return states

    def check_page(self, shop, path="/"):
        host = shop.url.split("://", 1)[1]
        command = [
            "curl", "-s", "-o", "/dev/null", "--max-time", str(PAGE_TIMEOUT), "-H", f"Host: {host}",
            "-w", f"%{{http_code}} %{{time_total}} %header{{{UNAVAILABLE_HEADER}}}", self.proxy_url(path),
        ]
        # From inside the shop's container: the worker is not in the shops' network.
        try:
            result = self.client.containers.get(container_name(shop)).exec_run(command)
        except (DockerException, requests.RequestException) as exc:
            return PageCheck(status=None, error=f"Nie da się wejść do kontenera sklepu ({exc.__class__.__name__}).")
        status, _, rest = result.output.decode(errors="replace").strip().partition(" ")
        took, _, unavailable = rest.partition(" ")
        if result.exit_code != 0 or not status.isdigit() or status == "000":
            reason = CURL_ERRORS.get(result.exit_code, f"curl zakończył się kodem {result.exit_code}")
            return PageCheck(status=None, seconds=_float(took), error=reason)
        return PageCheck(status=int(status), seconds=_float(took), unavailable=bool(unavailable.strip()))

    def start_shop(self, shop):
        if self._find_container(shop) is None and not self._volume_exists(shop):
            # A new container would start an empty shop in place of the lost one: that is for a person to decide
            # (e.g. python manage.py restore_shop).
            raise ProvisioningError(f"Nie ma kontenera ani wolumenu {container_name(shop)} z plikami sklepu.")
        self.step_start_container(shop)
        return self._wait_until_routed(shop)

    def restart_shop(self, shop):
        container = self.client.containers.get(container_name(shop))
        container.restart(timeout=30)
        return self._wait_until_routed(shop)

    def service_problems(self, required, optional=()):
        try:
            self.client.ping()
        except (DockerException, requests.RequestException):
            return {"docker": "Docker nie odpowiada."}
        problems = {}
        for name in [*required, *optional]:
            try:
                container = self.client.containers.get(name)
            except NotFound:
                if name not in optional:
                    problems[name] = "Nie ma takiego kontenera."
                continue
            except (DockerException, requests.RequestException) as exc:
                problems[name] = f"Docker nie podał stanu kontenera ({exc.__class__.__name__})."
                continue
            state = container.attrs.get("State", {})
            health = (state.get("Health") or {}).get("Status")
            if state.get("Status") != "running":
                problems[name] = f"Kontener nie działa ({state.get('Status')})."
            elif health == "unhealthy":
                problems[name] = "Kontener działa, ale nie przechodzi swojego healthchecka."
        return problems

    def disk_space(self):
        # The shops' database and Docker volumes are on one disk; the database container can say how full it is.
        try:
            output = self._exec(settings.SHOPS_DB_CONTAINER, ["df", "-Pk", "/var/lib/mysql"])
            fields = output.splitlines()[-1].split()
            total, free = int(fields[1]) * 1024, int(fields[3]) * 1024
        except (CommandError, DockerException, requests.RequestException, IndexError, ValueError):
            return None
        return free, total

    def _volume_exists(self, shop):
        try:
            self.client.volumes.get(container_name(shop))
        except NotFound:
            return False
        return True

    def _backup_tool(self, command, shop=None, files=None):
        """
        Runs shop-backup `command` in a throwaway container and returns what it printed. With `shop` it reaches
        the shop's database, and with `files` ("ro" or "rw") the shop's volume too.
        """
        if not settings.SHOPS_BACKUP_PASSWORD:
            raise CommandError("SHOPS_BACKUP_PASSWORD is not set")
        environment = {
            "RESTIC_REPOSITORY": BACKUP_REPOSITORY,
            "RESTIC_PASSWORD": settings.SHOPS_BACKUP_PASSWORD,
            "RESTIC_CACHE_DIR": BACKUP_CACHE,
        }
        volumes = {
            settings.SHOPS_BACKUP_VOLUME: {"bind": BACKUP_REPOSITORY, "mode": "rw"},
            settings.SHOPS_BACKUP_CACHE_VOLUME: {"bind": BACKUP_CACHE, "mode": "rw"},
        }
        if shop is not None:
            environment.update(
                SHOP=container_name(shop), SHOP_DB=db_name(shop), DB_HOST=settings.SHOPS_DB_CONTAINER,
                MYSQL_PWD=settings.SHOPS_DB_ROOT_PASSWORD,
            )
            if files:
                volumes[container_name(shop)] = {"bind": BACKUP_FILES, "mode": files}
        container = self.client.containers.run(
            settings.SHOPS_BACKUP_IMAGE, command, detach=True, network=settings.SHOPS_NETWORK,
            environment=environment, volumes=volumes, labels={BACKUP_LABEL: str(shop.pk) if shop else ""},
        )
        try:
            try:
                exit_code = container.wait(timeout=self.BACKUP_TIMEOUT)["StatusCode"]
            except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectionError):
                container.kill()
                raise CommandError(f"shop-backup {command[0]} took longer than {self.BACKUP_TIMEOUT} s") from None
            if exit_code != 0:
                errors = container.logs(stdout=False, stderr=True).decode(errors="replace").strip()
                raise CommandError(f"shop-backup {command[0]} exited with {exit_code}: {errors[-3000:]}")
            return container.logs(stdout=True, stderr=False).decode(errors="replace")
        finally:
            container.remove(force=True)

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

    def _upload(self, shop, path, data):
        """Put `data` (bytes) in the shop's container as the file `path`, readable for everyone."""
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w") as archive:
            info = tarfile.TarInfo(posixpath.basename(path))
            info.size, info.mode, info.mtime = len(data), 0o644, int(time.time())
            archive.addfile(info, io.BytesIO(data))
        container = self.client.containers.get(container_name(shop))
        if not container.put_archive(posixpath.dirname(path), buffer.getvalue()):
            raise CommandError(f"uploading {path} failed")

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


# Why curl got no answer, by its exit code.
CURL_ERRORS = {
    6: "Nie da się ustalić adresu serwera proxy.",
    7: "Serwer proxy nie przyjmuje połączeń.",
    28: f"Brak odpowiedzi w {PAGE_TIMEOUT} s.",
    52: "Serwer zakończył połączenie bez odpowiedzi.",
    56: "Połączenie zerwane w trakcie odpowiedzi.",
}


def seconds(value):
    """Docker takes durations in nanoseconds."""
    return int(value * 1_000_000_000)


def _float(value):
    try:
        return float(value)
    except ValueError:
        return None


def container_name(shop):
    # Keyed by id, not slug: a deleted shop's leftovers never clash with a new shop using the same slug.
    return f"shop-{shop.pk}"


def db_name(shop):
    return f"shop_{shop.pk}"


def backup_summary(output):
    """restic's summary of a backup, from the JSON lines shop-backup printed."""
    for line in reversed(output.splitlines()):
        try:
            data = json.loads(line)
        except ValueError:
            continue
        if isinstance(data, dict) and data.get("message_type") == "summary":
            return data
    raise CommandError("shop-backup backup printed no summary")


def snapshot_of(item):
    """A Snapshot from one item of `restic snapshots --json`."""
    return Snapshot(
        id=item["id"], host=item.get("hostname", ""), time=parse_datetime(item["time"]),
        tags=tuple(item.get("tags") or ()), size=(item.get("summary") or {}).get("total_bytes_processed"),
    )


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
