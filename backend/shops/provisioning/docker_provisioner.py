import json
import logging
import secrets
import time
from functools import cached_property

import docker
from django.conf import settings
from django.db.models import Count, F, Q
from docker.errors import NotFound

from ..categories import category_names
from ..models import Server, Shop, ShopCredentials
from .base import BaseProvisioner, ProvisioningError

logger = logging.getLogger(__name__)

WP_PATH = "/var/www/html"
ADMIN_USERNAME = "admin"
SAMPLE_PRODUCT_CATEGORIES = 3
SAMPLE_PRODUCTS_PER_CATEGORY = 2

TIMEZONES = {
    "PL": "Europe/Warsaw",
    "DE": "Europe/Berlin",
    "CZ": "Europe/Prague",
    "SK": "Europe/Bratislava",
    "GB": "Europe/London",
    "US": "America/New_York",
}
# Currencies written like "1 234,56 zł" rather than "$1,234.56".
COMMA_DECIMAL_CURRENCIES = {"PLN", "EUR"}

# How each theme shows the shop sidebar. `options` are PHP statements turning the sidebar on
# for the product archive, on the left; `search` is False where the header already has one.
THEME_NAVIGATION = {
    "storefront": {
        "sidebar": "sidebar-1",
        "search": False,
        "options": "set_theme_mod('storefront_layout', 'left');",
    },
    "astra": {
        "sidebar": "astra-woo-shop-sidebar",
        "search": True,
        "options": (
            "$s = get_option('astra-settings', array());"
            "$s['archive-product-sidebar-layout'] = 'left-sidebar';"
            "update_option('astra-settings', $s);"
        ),
    },
    "kadence": {
        "sidebar": "sidebar-primary",
        "search": True,
        # The front page (our shop page) takes its layout from the page itself, not the archive setting.
        "options": (
            "set_theme_mod('product_archive_layout', 'left');"
            "update_post_meta(wc_get_page_id('shop'), '_kad_post_layout', 'left');"
        ),
    },
}

NAVIGATION_TITLES = {
    "pl_PL": {"search": "Szukaj produktów", "categories": "Kategorie", "active": "Aktywne filtry",
              "price": "Cena", "rating": "Ocena"},
    "en_US": {"search": "Search products", "categories": "Categories", "active": "Active filters",
              "price": "Price", "rating": "Rating"},
    "de_DE": {"search": "Produkte suchen", "categories": "Kategorien", "active": "Aktive Filter",
              "price": "Preis", "rating": "Bewertung"},
}


class CommandError(Exception):
    """A command inside a container failed. The message is for logs only: it may contain internals."""


class DockerProvisioner(BaseProvisioner):
    """
    Runs every shop as its own WordPress container on the shop node from infra/shops,
    behind its Traefik proxy, with a separate database in its shared MariaDB.
    Mirrors infra/shops/provision-shop.sh step by step.
    """

    @cached_property
    def client(self):
        # Lazy: the web process only reads STEPS and has no access to the Docker socket.
        return docker.from_env()

    # --- steps ---

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
        name, password = _db_name(shop), credentials.db_password
        # Safe to interpolate: name comes from the shop id, password from token_urlsafe.
        self._sql(
            f"CREATE DATABASE IF NOT EXISTS `{name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
            f"CREATE USER IF NOT EXISTS '{name}'@'%' IDENTIFIED BY '{password}';"
            f"ALTER USER '{name}'@'%' IDENTIFIED BY '{password}';"
            f"GRANT ALL PRIVILEGES ON `{name}`.* TO '{name}'@'%';"
        )

    def step_start_container(self, shop):
        name = _container_name(shop)
        environment = {
            "WORDPRESS_DB_HOST": settings.SHOPS_DB_CONTAINER,
            "WORDPRESS_DB_NAME": _db_name(shop),
            "WORDPRESS_DB_USER": _db_name(shop),
            "WORDPRESS_DB_PASSWORD": self._credentials(shop).db_password,
            "WORDPRESS_CONFIG_EXTRA": (
                f"define('WP_ENVIRONMENT_TYPE', '{settings.SHOPS_WP_ENVIRONMENT}');"
                "define('DISALLOW_FILE_EDIT', true);"
            ),
        }
        container = self._find_container(shop)
        # The official image reads DB settings from env at runtime, so a container
        # with outdated env can be replaced without touching the files in the volume.
        if container is not None and _env(container) != environment:
            container.remove(force=True)
            container = None
        if container is None:
            container = self.client.containers.run(
                settings.SHOPS_WORDPRESS_IMAGE,
                name=name,
                detach=True,
                network=settings.SHOPS_NETWORK,
                restart_policy={"Name": "unless-stopped"},
                mem_limit=settings.SHOPS_CONTAINER_MEMORY,
                nano_cpus=1_000_000_000,
                volumes={name: {"bind": WP_PATH, "mode": "rw"}},
                environment=environment,
                labels={
                    "traefik.enable": "true",
                    f"traefik.http.routers.{name}.rule": f"Host(`{shop.domain}`)",
                    f"traefik.http.routers.{name}.entrypoints": "web",
                    f"traefik.http.services.{name}.loadbalancer.server.port": "80",
                    "shops.id": str(shop.pk),
                    "shops.slug": shop.slug,
                },
            )
        container.start()
        # The entrypoint copies WordPress into the volume and writes wp-config.php.
        for _ in range(60):
            if container.exec_run(["test", "-f", f"{WP_PATH}/wp-config.php"]).exit_code == 0:
                return
            time.sleep(1)
        raise ProvisioningError("WordPress nie wystartował.")

    def step_install_wordpress(self, shop):
        credentials = self._credentials(shop)
        installed = self._wp_succeeds(shop, "core", "is-installed")
        if not credentials.wp_admin_password:
            credentials.wp_admin_username = ADMIN_USERNAME
            credentials.wp_admin_password = secrets.token_urlsafe(18)
            credentials.save(update_fields=["wp_admin_username", "wp_admin_password", "updated_at"])
            if installed:
                # Installed by an earlier attempt whose password never got stored.
                self._wp(shop, "user", "update", ADMIN_USERNAME,
                         f"--user_pass={credentials.wp_admin_password}", "--skip-email")
        if not installed:
            self._wp(
                shop, "core", "install",
                f"--url={shop.url}",
                f"--title={shop.name}",
                f"--admin_user={credentials.wp_admin_username}",
                f"--admin_password={credentials.wp_admin_password}",
                f"--admin_email={shop.config.contact_email}",
                "--skip-email",
            )
            # Drop "Hello world" and "Sample Page". Only on a fresh install.
            default_content = self._wp(
                shop, "post", "list", "--post_type=post,page", "--post_status=any", "--format=ids",
            ).split()
            if default_content:
                self._wp(shop, "post", "delete", *default_content, "--force")
        self._wp(shop, "option", "update", "blogname", shop.name)
        self._wp(shop, "option", "update", "blogdescription", shop.config.description)

    def step_configure_locale(self, shop):
        language = shop.config.language
        if language != "en_US":
            self._wp(shop, "language", "core", "install", language)
            self._wp(shop, "site", "switch-language", language)
        self._wp(shop, "option", "update", "timezone_string", TIMEZONES.get(shop.config.country, "UTC"))
        self._wp(shop, "rewrite", "structure", "/%postname%/")
        self._wp(shop, "rewrite", "flush", "--hard")

    def step_configure_woocommerce(self, shop):
        config = shop.config
        # Translation first: activation creates the shop pages in the active language.
        if config.language != "en_US":
            self._wp(shop, "language", "plugin", "install", "woocommerce", config.language)
        if not self._wp_succeeds(shop, "plugin", "is-active", "woocommerce"):
            self._wp(shop, "plugin", "activate", "woocommerce")

        comma_decimal = config.currency in COMMA_DECIMAL_CURRENCIES
        options = {
            "woocommerce_default_country": config.country,
            "woocommerce_currency": config.currency,
            "woocommerce_currency_pos": "right_space" if comma_decimal else "left",
            "woocommerce_price_thousand_sep": " " if comma_decimal else ",",
            "woocommerce_price_decimal_sep": "," if comma_decimal else ".",
            "woocommerce_weight_unit": "kg",
            "woocommerce_dimension_unit": "cm",
            "woocommerce_email_from_address": config.contact_email,
            "woocommerce_email_from_name": shop.name,
            # New stores start in "coming soon" mode; open them right away.
            "woocommerce_coming_soon": "no",
            "woocommerce_allow_tracking": "no",
            "woocommerce_show_marketplace_suggestions": "no",
        }
        for key, value in options.items():
            self._wp(shop, "option", "update", key, value)
        # Skip the onboarding wizard and the setup task list (WooCommerce 11 option names).
        self._wp(shop, "option", "update", "woocommerce_onboarding_profile",
                 json.dumps({"skipped": True}), "--format=json")
        self._wp(shop, "option", "update", "woocommerce_task_list_hidden_lists",
                 json.dumps(["setup", "extended"]), "--format=json")
        self._wp(shop, "wc", "tool", "run", "install_pages", f"--user={ADMIN_USERNAME}")
        self._wp(shop, "option", "update", "show_on_front", "page")
        shop_page = self._wp(shop, "option", "get", "woocommerce_shop_page_id")
        self._wp(shop, "option", "update", "page_on_front", shop_page)

    def step_install_theme(self, shop):
        theme = shop.config.template.wp_theme
        if self._wp(shop, "option", "get", "stylesheet") != theme:
            self._wp(shop, "theme", "activate", theme)
            # Drop the default blog widgets the theme picked up. Block themes have no sidebars.
            self._wp_succeeds(shop, "widget", "reset", "--all")
        if shop.config.language != "en_US":
            # Not every theme ships every translation.
            self._wp_succeeds(shop, "language", "theme", "install", theme, shop.config.language)

    def step_create_categories(self, shop):
        config = shop.config
        category_ids = []
        for name in category_names(config.industry, config.category_count):
            existing = self._wp(shop, "term", "list", "product_cat", f"--name={name}", "--field=term_id")
            category_ids.append(existing or self._wp(
                shop, "wc", "product_cat", "create", f"--name={name}", f"--user={ADMIN_USERNAME}", "--porcelain",
            ))

        # Make our first category the default one, so "Uncategorized" doesn't show up in the menu.
        default_category = self._wp(shop, "option", "get", "default_product_cat")
        if default_category not in category_ids:
            self._wp(shop, "option", "update", "default_product_cat", category_ids[0])
            self._wp_succeeds(shop, "term", "delete", "product_cat", default_category)

        has_products = self._wp(shop, "wc", "product", "list", f"--user={ADMIN_USERNAME}", "--format=count") != "0"
        if not config.include_sample_products or has_products:
            return
        number = 1
        for category_id in category_ids[:SAMPLE_PRODUCT_CATEGORIES]:
            for _ in range(SAMPLE_PRODUCTS_PER_CATEGORY):
                self._wp(
                    shop, "wc", "product", "create", f"--user={ADMIN_USERNAME}", "--porcelain",
                    f"--name=Przykładowy produkt {number}",
                    "--type=simple", "--status=publish",
                    f"--regular_price={number * 25 + 24}.99",
                    "--description=To jest przykładowy produkt. Zmień jego opis, zdjęcia i cenę w panelu sklepu.",
                    f"--categories={json.dumps([{'id': int(category_id)}])}",
                )
                number += 1

    def step_configure_navigation(self, shop):
        navigation = THEME_NAVIGATION.get(shop.config.template.wp_theme)
        if navigation is None:
            return
        titles = NAVIGATION_TITLES.get(shop.config.language, NAVIGATION_TITLES["en_US"])
        sidebar = navigation["sidebar"]
        self._wp(shop, "eval", navigation["options"])
        # Rebuilt from scratch, so running it again gives the same sidebar.
        self._wp_succeeds(shop, "widget", "reset", sidebar)
        widgets = [
            ("woocommerce_product_search", [f"--title={titles['search']}"]),
            ("woocommerce_product_categories",
             [f"--title={titles['categories']}", "--count=1", "--hierarchical=1", "--orderby=name"]),
            # Shown only once a filter is applied / once products have reviews.
            ("woocommerce_layered_nav_filters", [f"--title={titles['active']}"]),
            ("woocommerce_price_filter", [f"--title={titles['price']}"]),
            ("woocommerce_rating_filter", [f"--title={titles['rating']}"]),
        ]
        if not navigation["search"]:
            widgets = widgets[1:]
        for position, (widget, args) in enumerate(widgets, start=1):
            self._wp(shop, "widget", "add", widget, sidebar, str(position), *args)

    def step_generate_api_keys(self, shop):
        credentials = self._credentials(shop)
        username = credentials.wp_admin_username
        existing = self._wp(shop, "user", "application-password", "list", username,
                            "--name=platform", "--field=uuid").split()
        for uuid in existing:
            self._wp(shop, "user", "application-password", "delete", username, uuid)
        credentials.wp_application_password = self._wp(
            shop, "user", "application-password", "create", username, "platform", "--porcelain",
        )
        credentials.save(update_fields=["wp_application_password", "updated_at"])

    def step_health_check(self, shop):
        # Goes through the proxy like a visitor would, so routing gets checked too.
        host = shop.url.split("://", 1)[1]
        base = f"http://{settings.SHOPS_PROXY_CONTAINER}"
        credentials = self._credentials(shop)
        checks = [
            ("strona sklepu", [base + "/"]),
            ("API sklepu", ["-u", f"{credentials.wp_admin_username}:{credentials.wp_application_password}",
                            base + "/wp-json/wc/v3/system_status"]),
        ]
        for label, args in checks:
            status = self._exec(
                _container_name(shop),
                ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "-H", f"Host: {host}", *args],
            )
            if status != "200":
                raise ProvisioningError(f"Sklep nie odpowiada poprawnie ({label}: HTTP {status}).")

    # --- lifecycle ---

    def cleanup(self, shop):
        # Keep everything: a retry continues from what's already there.
        pass

    def teardown(self, shop):
        name = _container_name(shop)
        container = self._find_container(shop)
        if container is not None:
            container.remove(force=True)
        try:
            self.client.volumes.get(name).remove(force=True)
        except NotFound:
            pass
        db = _db_name(shop)
        self._sql(f"DROP DATABASE IF EXISTS `{db}`; DROP USER IF EXISTS '{db}'@'%';")

    # --- helpers ---

    def _credentials(self, shop):
        credentials, _ = ShopCredentials.objects.get_or_create(
            shop=shop, defaults={"wp_admin_username": ADMIN_USERNAME},
        )
        return credentials

    def _find_container(self, shop):
        try:
            return self.client.containers.get(_container_name(shop))
        except NotFound:
            return None

    def _exec(self, container_name, command, user="", environment=None):
        container = self.client.containers.get(container_name)
        result = container.exec_run(command, user=user, environment=environment)
        output = result.output.decode(errors="replace").strip()
        if result.exit_code != 0:
            # Only the command name: arguments may contain passwords.
            raise CommandError(f"{' '.join(command[:4])}… exited with {result.exit_code}: {output[-2000:]}")
        return output

    def _wp(self, shop, *args):
        return self._exec(_container_name(shop), ["wp", f"--path={WP_PATH}", *args], user="www-data")

    def _wp_succeeds(self, shop, *args):
        try:
            self._wp(shop, *args)
        except CommandError:
            return False
        return True

    def _sql(self, statement):
        if not settings.SHOPS_DB_ROOT_PASSWORD:
            raise CommandError("SHOPS_DB_ROOT_PASSWORD is not set")
        self._exec(
            settings.SHOPS_DB_CONTAINER,
            ["mariadb", "-uroot", "-e", statement],
            environment={"MYSQL_PWD": settings.SHOPS_DB_ROOT_PASSWORD},
        )


def _container_name(shop):
    # Keyed by id, not slug: a deleted shop's leftovers never clash with a new shop using the same slug.
    return f"shop-{shop.pk}"


def _db_name(shop):
    return f"shop_{shop.pk}"


def _env(container):
    pairs = (item.split("=", 1) for item in container.attrs["Config"]["Env"])
    current = dict(pair for pair in pairs if len(pair) == 2)
    return {key: current.get(key) for key in (
        "WORDPRESS_DB_HOST", "WORDPRESS_DB_NAME", "WORDPRESS_DB_USER", "WORDPRESS_DB_PASSWORD", "WORDPRESS_CONFIG_EXTRA",
    )}
