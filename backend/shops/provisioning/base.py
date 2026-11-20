from dataclasses import dataclass, field
from datetime import datetime


class ProvisioningError(Exception):
    pass


class NothingToBackUp(Exception):
    """The shop has no files on the shop node (setup failed early, or it was torn down)."""


@dataclass(frozen=True)
class Backup:
    """`size`: bytes of files and database in the snapshot."""

    snapshot_id: str
    size: int


@dataclass(frozen=True)
class Snapshot:
    """`host` is shop-<id>, `tags` the kind of backup."""

    id: str
    host: str
    time: datetime
    tags: tuple = field(default=())
    size: int | None = None


@dataclass(frozen=True)
class ContainerState:
    """`status` as Docker names it (running, exited…); `health` from the healthcheck, None without one."""

    status: str
    health: str | None = None

    @property
    def running(self):
        return self.status == "running"


@dataclass(frozen=True)
class PageCheck:
    """A visit through the proxy. `status` None: no answer (`error` says why); `unavailable`: no healthy container."""

    status: int | None
    seconds: float | None = None
    unavailable: bool = False
    error: str = ""


@dataclass(frozen=True)
class ProductCount:
    """Products in any state but deleted: the owner's own and the samples added at setup."""

    products: int
    samples: int


class BaseProvisioner:
    """
    Sets up a shop via `step_<key>(shop)` methods, one per step listed in shops/platforms/__init__.py.
    Every step must be idempotent: a retry reruns all steps over whatever a failed attempt left behind.
    """

    def run_step(self, key, shop):
        getattr(self, f"step_{key}")(shop)

    def cleanup(self, shop):
        """Called after a failed run. Must be safe to call anytime."""

    def teardown(self, shop):
        """Remove everything the shop uses. Must be safe to call more than once."""

    def update_address(self, shop):
        """Move a running shop to its current `shop.url`. Returns the previous address, or None if nothing moved."""
        return None

    def suspend(self, shop):
        """Stop serving the shop, keeping its data. Safe to call more than once."""

    def resume(self, shop):
        """Serve a suspended shop again, with the resources of the owner's current plan."""

    def refresh_resources(self, shop):
        """Apply the owner's current plan (e.g. memory) to a running shop."""

    def container_outdated(self, shop):
        """Whether the container differs from a new one (e.g. predates the healthcheck); start_shop replaces it."""
        return False

    def configure_mail(self, shop):
        """Send mail through the relay (SHOPS_SMTP_*) from the shop's own sender. False when nothing is running."""
        return False

    # --- running shops (see provisioning/operations.py) ---

    def api(self, shop):
        """The shop's REST API (shops.remote); raises ShopNotConnected while the shop has no key."""
        raise NotImplementedError

    def read_settings(self, shop):
        """{section: {field: value}}, as in shops/shop_settings.py."""
        raise NotImplementedError

    def apply_settings(self, shop, changes, values):
        """
        `changes`: {section: {field: new value}}, only what changed; `values`: the complete settings after it.
        `shop` and `shop.config` already carry the new name, language, currency, country and theme.
        """
        raise NotImplementedError

    def publish_documents(self, shop, documents):
        """Publish "terms" and "privacy" as shop pages, shown where customers accept them. Returns {key: page URL}."""
        raise NotImplementedError

    def reset_admin_password(self, shop):
        """New admin password, stored in the shop's credentials."""
        raise NotImplementedError

    def set_admin_password(self, shop, password):
        """Logs out whoever is signed in."""
        raise NotImplementedError

    def remove_sample_products(self, shop):
        """Returns how many sample products were removed."""
        raise NotImplementedError

    def count_products(self, shop):
        """ProductCount. Read-only."""
        raise NotImplementedError

    def read_orders(self, shop, since, limit):
        """shops.orders.Order changed at/after `since` (aware datetime), oldest first, at most `limit`. Read-only."""
        raise NotImplementedError

    def read_order(self, shop, external_id):
        """
        shops.orders.OrderDetail through the shop's API, so in a web request. Raises shops.remote.ShopApiError,
        NotInShop for an id the shop doesn't have. Read-only.
        """
        raise NotImplementedError

    # --- backups (see shops/backups.py) ---

    def can_back_up(self):
        return False

    def backup(self, shop, tag):
        """Snapshot files and DB tagged `tag`, without stopping the shop. Raises NothingToBackUp when no files."""
        raise NotImplementedError

    def restore_backup(self, shop, snapshot_id):
        """Restore files and DB from the snapshot (even a deleted shop), keeping address, mail relay, admin password."""
        raise NotImplementedError

    def list_backups(self):
        """Every snapshot in the repository, as Snapshot."""
        raise NotImplementedError

    def forget_backups(self, snapshot_ids):
        """Unknown ids are skipped. Space is freed only by prune_backups."""
        raise NotImplementedError

    def prune_backups(self):
        raise NotImplementedError

    # --- health (see monitoring/) ---

    def can_monitor(self):
        return False

    def container_states(self):
        """{shop id: ContainerState} for every shop container on the node; a shop without one is absent."""
        raise NotImplementedError

    def check_page(self, shop):
        """PageCheck of the home page through the proxy. The container must be running."""
        raise NotImplementedError

    def start_shop(self, shop):
        """Start the container (recreated if only it is gone); waits and returns whether the proxy reaches it."""
        raise NotImplementedError

    def restart_shop(self, shop):
        """Restart the running container and wait until the proxy reaches it; returns whether it does."""
        raise NotImplementedError

    def service_problems(self, required, optional=()):
        """
        {name: what is wrong} for broken shared service containers, {"docker": ...} when Docker doesn't answer.
        `optional` ones are checked only if their container exists (e.g. mail relay: local container, remote in prod).
        """
        raise NotImplementedError

    def disk_space(self):
        """(free, total) bytes of the shops' data disk, or None when unknown."""
        return None
