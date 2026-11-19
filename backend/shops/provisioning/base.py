from dataclasses import dataclass, field
from datetime import datetime


class ProvisioningError(Exception):
    pass


class NothingToBackUp(Exception):
    """The shop has no files on the shop node (e.g. its setup failed early, or it was torn down)."""


@dataclass(frozen=True)
class Backup:
    """A copy just made: its snapshot in the repository and how many bytes of files and database it holds."""

    snapshot_id: str
    size: int


@dataclass(frozen=True)
class Snapshot:
    """A snapshot in the backup repository; `host` names the shop (shop-<id>), `tags` the kind of backup."""

    id: str
    host: str
    time: datetime
    tags: tuple = field(default=())
    size: int | None = None


@dataclass(frozen=True)
class ContainerState:
    """
    A shop's container as Docker sees it: `status` as Docker names it (running, exited, restarting…) and `health`
    from its healthcheck (healthy, unhealthy, starting), None for a container without one.
    """

    status: str
    health: str | None = None

    @property
    def running(self):
        return self.status == "running"


@dataclass(frozen=True)
class PageCheck:
    """
    A visit to a page of the shop through the proxy, as a customer would make it: the HTTP status (None when nothing
    came back, `error` says why), how long it took, and whether the platform's "temporarily unavailable" page answered
    instead of the shop (the proxy had no healthy container to send it to).
    """

    status: int | None
    seconds: float | None = None
    unavailable: bool = False
    error: str = ""


@dataclass(frozen=True)
class ProductCount:
    """Products in the shop, in any state but deleted: the owner's own, and the samples added at setup."""

    products: int
    samples: int


class BaseProvisioner:
    """
    Sets up a shop on one platform step by step: the steps are listed in shops/platforms/__init__.py.

    Every step must be idempotent: a retry creates a new job and runs all steps
    again, so a step has to cope with work left behind by a failed attempt.
    Implementations define a `step_<key>(shop)` method for each step.
    """

    def run_step(self, key, shop):
        getattr(self, f"step_{key}")(shop)

    def cleanup(self, shop):
        """Called after a failed run. Must be safe to call anytime."""

    def teardown(self, shop):
        """Remove everything the shop uses. Must be safe to call more than once."""

    def update_address(self, shop):
        """
        Move a running shop to its current `shop.url`, e.g. after SHOPS_BASE_DOMAIN changed.
        Returns the previous address, or None when there is nothing to move.
        """
        return None

    def suspend(self, shop):
        """Stop serving the shop, keeping everything it has. Safe to call more than once."""

    def resume(self, shop):
        """Serve a suspended shop again, with the resources its owner's plan gives now."""

    def refresh_resources(self, shop):
        """Apply the owner's current plan (e.g. memory) to a running shop."""

    def container_outdated(self, shop):
        """
        Whether the shop's container is not as a new one would be now, e.g. from before the healthcheck (False
        without one). start_shop replaces it.
        """
        return False

    def configure_mail(self, shop):
        """
        Send the running shop's e-mail through the platform's mail relay (settings SHOPS_SMTP_*), from the shop's
        own sender address. Returns False when the shop has nothing running to configure.
        """
        return False

    # --- running shops (see provisioning/operations.py) ---

    def read_settings(self, shop):
        """The shop's current settings, {section: {field: value}} as in shops/shop_settings.py."""
        raise NotImplementedError

    def apply_settings(self, shop, changes, values):
        """
        Make the shop match `changes` ({section: {field: new value}}, only what changed).
        `values` are the complete settings after the change, for sections that need them all.
        `shop` and `shop.config` already carry the new name, language, currency, country and theme.
        """
        raise NotImplementedError

    def publish_documents(self, shop, documents):
        """
        Publish the terms of sale and privacy policy (shops.documents.Document, keys "terms" and "privacy") as pages
        of the shop, replacing the ones it has, and show them where customers accept them. Returns {key: page URL}.
        """
        raise NotImplementedError

    def reset_admin_password(self, shop):
        """Give the shop administrator a new password and store it in the shop's credentials."""
        raise NotImplementedError

    def set_admin_password(self, shop, password):
        """Make `password` the shop administrator's password in the shop, logging out whoever is signed in."""
        raise NotImplementedError

    def remove_sample_products(self, shop):
        """Delete the sample products added at provisioning. Returns how many were removed."""
        raise NotImplementedError

    def count_products(self, shop):
        """ProductCount of the shop. Read-only: the shop is not changed."""
        raise NotImplementedError

    def read_orders(self, shop, since, limit):
        """
        Orders changed at or after `since` (an aware datetime), the oldest change first, at most `limit` of them,
        as shops.orders.Order. Read-only: the shop is not changed.
        """
        raise NotImplementedError

    # --- backups (see shops/backups.py) ---

    def can_back_up(self):
        """Whether backups are set up at all."""
        return False

    def backup(self, shop, tag):
        """
        Copy the shop's files and database into the backup repository, as a snapshot tagged `tag`, without stopping
        the shop. Returns a Backup; raises NothingToBackUp when the shop has no files.
        """
        raise NotImplementedError

    def restore_backup(self, shop, snapshot_id):
        """
        Replace the shop's files and database with those of the snapshot and leave the shop running at its current
        address, mail relay and admin password. Also brings back a deleted shop, whose files and database are gone.
        """
        raise NotImplementedError

    def list_backups(self):
        """Every snapshot in the repository, as Snapshot."""
        raise NotImplementedError

    def forget_backups(self, snapshot_ids):
        """Remove snapshots from the repository; ids it doesn't have are skipped. The space is freed by prune."""
        raise NotImplementedError

    def prune_backups(self):
        """Free the space of removed snapshots."""
        raise NotImplementedError

    # --- health (see monitoring/) ---

    def can_monitor(self):
        """Whether the shops' containers can be checked at all."""
        return False

    def container_states(self):
        """{shop id: ContainerState} for every shop container on the node; a shop without a container is missing."""
        raise NotImplementedError

    def check_page(self, shop):
        """Visit the shop's home page through the proxy (PageCheck). The shop's container must be running."""
        raise NotImplementedError

    def start_shop(self, shop):
        """
        Start the shop's stopped container (a new one when only the container is gone, not the shop's files) and wait
        until the proxy reaches it; returns whether it does.
        """
        raise NotImplementedError

    def restart_shop(self, shop):
        """Restart the shop's running container and wait until the proxy reaches it; returns whether it does."""
        raise NotImplementedError

    def service_problems(self, required, optional=()):
        """
        {name: what is wrong} for the shared services (containers) that don't work, {"docker": ...} when Docker
        itself doesn't answer. An `optional` service is only checked when its container exists (e.g. the shops'
        mail relay is a container locally, but a provider's server in production).
        """
        raise NotImplementedError

    def disk_space(self):
        """(free bytes, total bytes) of the disk the shops keep their data on, or None when unknown."""
        return None
