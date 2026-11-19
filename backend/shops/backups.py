"""
Backups of the shops. Every night the worker copies each shop's files and database into the backup repository on
the shop node (one restic snapshot per shop and backup, made by the provisioner, see infra/shops/backup), and the
owner can make one and bring the shop back to any of them in the app.

ShopBackup rows are the index of the repository: what the owner sees and what the retention below decides on.
maintain() keeps the two in step every night.
"""

import logging
import re
from datetime import datetime, time, timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import SalesSync, Shop, ShopBackup, ShopChecklist, ShopOperation, ShopOrder
from .provisioning import get_provisioner
from .provisioning.base import NothingToBackUp, ProvisioningError

logger = logging.getLogger(__name__)

Kind = ShopBackup.Kind
Status = ShopBackup.Status

BACKUP_FAILED = "Nie udało się zrobić kopii zapasowej. Spróbuj ponownie za chwilę."
BACKUP_GONE = "Tej kopii zapasowej już nie ma."
RESTORE_FAILED = "Nie udało się przywrócić kopii zapasowej. Sklep ma z powrotem stan sprzed próby."
RESTORE_BROKEN = (
    "Nie udało się przywrócić kopii zapasowej ani wrócić do stanu sprzed próby. Już to sprawdzamy. "
    "Jeśli sklep nie zacznie działać w ciągu godziny, napisz do nas."
)
# Shops copied every night: a suspended shop keeps its data, so it is copied too.
BACKED_UP = (Shop.Status.ACTIVE, Shop.Status.SUSPENDED)
# Everything from the last day stays, whatever else the retention says.
KEEP_ALL_FOR = timedelta(days=1)
# Failed backups stay listed for the admin this long.
FAILURES_KEPT_FOR = timedelta(days=7)
# A snapshot the index doesn't know is taken in only when it is this old, so a backup that is being saved right
# now isn't counted twice.
ADOPT_AFTER = timedelta(hours=1)
SHOP_HOST = re.compile(r"^shop-(\d+)$")


def enabled():
    return get_provisioner().can_back_up()


def restorable(shop):
    """The shop's backups the owner can go back to, newest first."""
    return shop.backups.filter(status=Status.SUCCEEDED).order_by("-created_at", "-id")


def back_up(shop, kind):
    """
    Copies the shop now and returns its ShopBackup. Raises NothingToBackUp when the shop has no files, and
    ProvisioningError (for the owner) when copying failed; the failure is recorded for the admin.
    """
    started = timezone.now()
    try:
        made = get_provisioner(shop.platform).backup(shop, kind)
    except NothingToBackUp:
        raise
    except Exception as exc:
        logger.exception("Backing up shop %s failed", shop.pk)
        ShopBackup.objects.create(shop=shop, kind=kind, status=Status.FAILED, error=str(exc)[:5000], created_at=started)
        raise ProvisioningError(BACKUP_FAILED) from exc
    return ShopBackup.objects.create(
        shop=shop, kind=kind, snapshot_id=made.snapshot_id, size=made.size, created_at=started,
    )


def restore(shop, backup):
    """
    Brings the shop back to `backup`. How the shop is now is backed up first, so the owner can go back to it; when
    restoring fails part-way, the shop gets that state back. Returns the backup made first.
    """
    provisioner = get_provisioner(shop.platform)
    before = back_up(shop, Kind.BEFORE_RESTORE)
    try:
        provisioner.restore_backup(shop, backup.snapshot_id)
    except Exception as exc:
        logger.exception("Restoring backup %s of shop %s failed, going back to %s", backup.pk, shop.pk, before.pk)
        try:
            provisioner.restore_backup(shop, before.snapshot_id)
        except Exception:
            logger.exception("Going back after a failed restore of shop %s failed too: the shop needs a hand", shop.pk)
            raise ProvisioningError(RESTORE_BROKEN) from exc
        read_again(shop)
        raise ProvisioningError(RESTORE_FAILED) from exc
    read_again(shop)
    return before


def read_again(shop):
    """
    After a restore: what the platform keeps of the shop is read from it again. The shop itself works by then,
    so a failure here is only logged.
    """
    from . import tasks
    from .provisioning.operations import read_back

    read_back(shop)
    # The copy of the orders starts over; its first read announces nothing, as the orders aren't new.
    ShopOrder.objects.filter(shop=shop).delete()
    SalesSync.objects.filter(shop=shop).delete()
    # Products are counted again when the checklist is next opened.
    ShopChecklist.objects.filter(shop=shop).update(products=None, sample_products=None, counted_at=None)
    transaction.on_commit(lambda: tasks.sync_shop_orders.delay(shop.pk))


def back_up_before_delete(shop):
    """
    The last copy of a shop being deleted, kept SHOPS_BACKUP_DELETED_DAYS days so it can still be brought back.
    Deleting goes on without it; then the latest nightly backup is kept instead. Returns the backup or None.
    """
    if not enabled():
        return None
    try:
        return back_up(shop, Kind.BEFORE_DELETE)
    except (NothingToBackUp, ProvisioningError):
        return None


def forget_all(shop):
    """
    For a deleted account: the shop's backups go at once. Their data leaves the repository the next night (maintain).
    """
    snapshot_ids = list(shop.backups.exclude(snapshot_id="").values_list("snapshot_id", flat=True))
    if snapshot_ids and enabled():
        try:
            get_provisioner(shop.platform).forget_backups(snapshot_ids)
        except Exception:
            # maintain() removes snapshots of shops that are gone, so nothing stays for long.
            logger.exception("Removing the backups of shop %s failed", shop.pk)
    shop.backups.all().delete()


def back_up_all():
    """Every night: copies each running or suspended shop, then maintain(). Returns the shops left without a copy."""
    if not enabled():
        logger.warning("Shop backups are off: SHOPS_BACKUP_PASSWORD is not set")
        return []
    failed = []
    for shop in Shop.objects.filter(status__in=BACKED_UP).order_by("pk"):
        if _busy(shop):
            # E.g. a restore under way: a copy of a half-restored shop would be worse than none.
            logger.info("Shop %s is busy, its nightly backup is skipped", shop.pk)
            continue
        try:
            back_up(shop, Kind.NIGHTLY)
        except NothingToBackUp:
            logger.warning("Shop %s has no files to back up", shop.pk)
        except ProvisioningError:
            failed.append(shop)
    maintain()
    return failed


def maintain(now=None):
    """
    Makes the index match the repository, then removes the backups beyond those kept (see kept) and frees their
    space. Returns how many snapshots were removed.
    """
    now = now or timezone.now()
    provisioner = get_provisioner()
    snapshots = {snapshot.id: snapshot for snapshot in provisioner.list_backups()}

    rows = list(ShopBackup.objects.filter(status=Status.SUCCEEDED).select_related("shop"))
    missing = [row.pk for row in rows if row.snapshot_id not in snapshots]
    if missing:
        # The repository lost them (or was replaced): they can't be restored, so the owner shouldn't see them.
        logger.warning("Backups %s are not in the repository any more", missing)
        ShopBackup.objects.filter(pk__in=missing).delete()

    known = {row.snapshot_id for row in rows}
    shops = Shop.objects.in_bulk({_shop_id(snapshot) for snapshot in snapshots.values()} - {None})
    forget = []
    for snapshot in snapshots.values():
        shop_id = _shop_id(snapshot)
        if snapshot.id in known or shop_id is None:
            continue
        shop = shops.get(shop_id)
        if shop is None:
            # Its account was deleted: nothing of the shop stays.
            forget.append(snapshot.id)
        elif now - snapshot.time >= ADOPT_AFTER:
            # Made but never recorded (e.g. the worker stopped in between), or the index is older than the repository.
            ShopBackup.objects.create(
                shop=shop, kind=_kind(snapshot.tags), snapshot_id=snapshot.id, size=snapshot.size,
                created_at=snapshot.time,
            )

    removed = []
    by_shop = {}
    for row in ShopBackup.objects.filter(status=Status.SUCCEEDED).select_related("shop"):
        by_shop.setdefault(row.shop, []).append(row)
    for shop, backups in by_shop.items():
        if _busy(shop):
            # The owner may be restoring one of them right now.
            continue
        keep = kept(shop, backups, now)
        removed += [backup for backup in backups if backup.pk not in keep]

    forget += [backup.snapshot_id for backup in removed]
    if forget:
        provisioner.forget_backups(forget)
        ShopBackup.objects.filter(pk__in=[backup.pk for backup in removed]).delete()
    # Every night, also when nothing was removed now: the backups of an account deleted during the day are only
    # forgotten, and their data leaves the repository here.
    provisioner.prune_backups()
    ShopBackup.objects.filter(status=Status.FAILED, created_at__lt=now - FAILURES_KEPT_FOR).delete()
    return len(forget)


def kept(shop, backups, now):
    """
    Ids of the shop's `backups` (successful ones) that stay. For a live shop: everything from the last day, and the
    newest backup of each of the SHOPS_BACKUP_KEEP_DAILY latest days and SHOPS_BACKUP_KEEP_WEEKLY latest weeks that
    have one. For a deleted shop: its newest backup, for SHOPS_BACKUP_DELETED_DAYS days after it was made.
    """
    newest_first = sorted(backups, key=lambda backup: backup.created_at, reverse=True)
    if not newest_first:
        return set()
    if shop.status == Shop.Status.DELETED:
        newest = newest_first[0]
        return {newest.pk} if now - newest.created_at < timedelta(days=settings.SHOPS_BACKUP_DELETED_DAYS) else set()
    keep, days, weeks = set(), set(), set()
    for backup in newest_first:
        local = timezone.localtime(backup.created_at)
        day, week = local.date(), local.isocalendar()[:2]
        if now - backup.created_at < KEEP_ALL_FOR:
            keep.add(backup.pk)
        if day not in days and len(days) < settings.SHOPS_BACKUP_KEEP_DAILY:
            days.add(day)
            keep.add(backup.pk)
        if week not in weeks and len(weeks) < settings.SHOPS_BACKUP_KEEP_WEEKLY:
            weeks.add(week)
            keep.add(backup.pk)
    return keep


def manual_left(shop, now=None):
    """How many more backups the owner can make today, on top of the nightly ones."""
    today = timezone.localtime(now or timezone.now()).replace(hour=0, minute=0, second=0, microsecond=0)
    made = (
        shop.operations.filter(kind=ShopOperation.Kind.CREATE_BACKUP, created_at__gte=today)
        .exclude(status=ShopOperation.Status.FAILED)
        .count()
    )
    return max(settings.SHOPS_BACKUP_MANUAL_PER_DAY - made, 0)


def next_nightly(now=None):
    """When the next nightly backups start (SHOPS_BACKUP_HOUR, local time)."""
    local = timezone.localtime(now or timezone.now())
    day = local.date() if local.hour < settings.SHOPS_BACKUP_HOUR else local.date() + timedelta(days=1)
    return timezone.make_aware(datetime.combine(day, time(settings.SHOPS_BACKUP_HOUR)))


def overview(shop):
    """The backups section of the app."""
    return {
        "enabled": enabled(),
        "backups": list(restorable(shop)),
        "manual_left": manual_left(shop),
        "manual_per_day": settings.SHOPS_BACKUP_MANUAL_PER_DAY,
        "keep_daily": settings.SHOPS_BACKUP_KEEP_DAILY,
        "keep_weekly": settings.SHOPS_BACKUP_KEEP_WEEKLY,
        "nightly_at": next_nightly(),
    }


def _busy(shop):
    # Imported here: services imports the tasks, which import this module.
    from .services import current_operation

    return current_operation(shop) is not None


def _shop_id(snapshot):
    match = SHOP_HOST.match(snapshot.host)
    return int(match.group(1)) if match else None


def _kind(tags):
    return next((tag for tag in tags if tag in Kind.values), Kind.NIGHTLY)
