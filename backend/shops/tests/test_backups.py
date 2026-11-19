from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest
from django.core.management import CommandError, call_command
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from docker.errors import NotFound

from accounts.models import User
from shops import backups
from shops.models import SalesSync, Shop, ShopBackup, ShopChecklist, ShopCredentials, ShopOperation, ShopOrder
from shops.platforms.magento import MagentoProvisioner
from shops.platforms.woocommerce import WooCommerceProvisioner
from shops.provisioning.base import Backup, NothingToBackUp, Snapshot
from shops.provisioning.container import CommandError as ContainerCommandError
from shops.provisioning.fake import FakeProvisioner
from shops.tasks import back_up_all_shops

pytestmark = pytest.mark.django_db

Kind = ShopBackup.Kind
PASSWORD = "Sekretne-haslo-123"


@pytest.fixture
def shop(auth_client, django_capture_on_commit_callbacks):
    payload = {"name": "Mój Sklep", "slug": "moj-sklep", "industry": "fashion", "template": "storefront"}
    with django_capture_on_commit_callbacks(execute=True):
        shop_id = auth_client.post("/api/shops/", payload, format="json").data["id"]
    return Shop.objects.get(pk=shop_id)


def other_shop(owner, slug, status=Shop.Status.ACTIVE):
    """A shop of `owner` with something to copy (the simulated backup needs its credentials)."""
    shop = Shop.objects.create(owner=owner, name=slug.title(), slug=slug, status=status)
    ShopCredentials.objects.create(shop=shop, admin_login="admin")
    return shop


def backup_at(shop, when, kind=Kind.NIGHTLY):
    """A backup taken at `when`, in the index and in the simulated repository."""
    snapshot_id = FakeProvisioner().backup(shop, kind).snapshot_id
    FakeProvisioner.snapshots[snapshot_id] = Snapshot(
        id=snapshot_id, host=f"shop-{shop.pk}", time=when, tags=(kind,), size=1000,
    )
    return ShopBackup.objects.create(shop=shop, kind=kind, snapshot_id=snapshot_id, size=1000, created_at=when)


def local(*args):
    return timezone.make_aware(datetime(*args))


def url(shop, suffix=""):
    return f"/api/shops/{shop.pk}/backups/{suffix}"


def run(client, captured, path, method="post"):
    """Calls the API and runs the operation it queued, as the worker would."""
    with captured(execute=True):
        response = getattr(client, method)(path)
    return response


def operation(client, shop, response):
    return client.get(f"/api/shops/{shop.pk}/operations/{response.data['id']}/").data


def restore(client, captured, shop, backup):
    """Restores `backup` through the API; returns the finished operation."""
    return operation(client, shop, run(client, captured, url(shop, f"{backup.pk}/restore/")))


# --- the owner in the app ---


def test_a_new_shop_waits_for_its_first_nightly_backup(auth_client, shop, settings):
    settings.SHOPS_BACKUP_HOUR = 3

    data = auth_client.get(url(shop)).data

    assert data["enabled"] is True
    assert data["backups"] == []
    assert data["manual_left"] == data["manual_per_day"] == 3
    assert (data["keep_daily"], data["keep_weekly"]) == (7, 4)
    nightly = timezone.localtime(parse_datetime(data["nightly_at"]))
    assert (nightly.hour, nightly.minute) == (3, 0)
    assert timezone.now() < nightly <= timezone.now() + timedelta(days=1)


def test_owner_makes_a_backup_now(auth_client, shop, django_capture_on_commit_callbacks):
    response = run(auth_client, django_capture_on_commit_callbacks, url(shop))

    assert response.status_code == 202
    assert response.data["kind"] == "create_backup"
    done = operation(auth_client, shop, response)
    assert done["status"] == "succeeded"
    listed = auth_client.get(url(shop)).data
    assert [(item["kind"], item["kind_display"]) for item in listed["backups"]] == [("manual", "Kopia na żądanie")]
    assert listed["backups"][0]["size"] == 48_000_000
    assert done["backup_created_at"] == listed["backups"][0]["created_at"]
    assert listed["manual_left"] == 2


def test_owner_makes_only_a_few_backups_a_day(auth_client, shop, settings, django_capture_on_commit_callbacks):
    settings.SHOPS_BACKUP_MANUAL_PER_DAY = 2
    for _ in range(2):
        assert run(auth_client, django_capture_on_commit_callbacks, url(shop)).status_code == 202

    response = auth_client.post(url(shop))

    assert response.status_code == 429
    assert "jutro" in response.data["detail"]
    assert auth_client.get(url(shop)).data["manual_left"] == 0


def test_a_failed_backup_says_so_and_does_not_use_up_the_day(
    auth_client, shop, settings, django_capture_on_commit_callbacks,
):
    settings.FAKE_PROVISIONER_FAIL_AT_STEP = "backup"

    done = operation(auth_client, shop, run(auth_client, django_capture_on_commit_callbacks, url(shop)))

    assert done["status"] == "failed"
    assert done["error"] == backups.BACKUP_FAILED
    listed = auth_client.get(url(shop)).data
    assert listed["backups"] == []
    assert listed["manual_left"] == 3
    # The admin sees what went wrong.
    assert ShopBackup.objects.get(shop=shop).status == ShopBackup.Status.FAILED


def test_restoring_brings_the_shop_back_and_keeps_how_it_was_before(
    auth_client, shop, django_capture_on_commit_callbacks,
):
    old = backup_at(shop, timezone.now() - timedelta(days=2))
    # Things the platform keeps about the shop as it is now.
    SalesSync.objects.create(shop=shop, synced_at=timezone.now())
    ShopOrder.objects.create(
        shop=shop, external_id="9999", number="9999", status="new", total=10, currency="PLN",
        placed_at=timezone.now(), changed_at=timezone.now(),
    )
    ShopChecklist.objects.update_or_create(
        shop=shop, defaults={"products": 12, "sample_products": 0, "counted_at": timezone.now()},
    )

    response = run(auth_client, django_capture_on_commit_callbacks, url(shop, f"{old.pk}/restore/"))

    assert response.status_code == 202
    done = operation(auth_client, shop, response)
    assert done["status"] == "succeeded"
    assert done["kind_display"] == "Przywrócenie kopii zapasowej"
    assert parse_datetime(done["backup_created_at"]) == old.created_at
    assert FakeProvisioner.restored == [old.snapshot_id]
    # The state from before is the newest backup, so the owner can go back to it.
    before = ShopBackup.objects.get(pk=done["result"]["before"])
    assert before.kind == Kind.BEFORE_RESTORE
    assert [item["id"] for item in auth_client.get(url(shop)).data["backups"]] == [before.pk, old.pk]
    # The copy of the orders is read again from the restored shop; products are counted again.
    assert not ShopOrder.objects.filter(shop=shop, external_id="9999").exists()
    assert ShopOrder.objects.filter(shop=shop).exists()
    checklist = ShopChecklist.objects.get(shop=shop)
    assert (checklist.products, checklist.sample_products, checklist.counted_at) == (None, None, None)


def test_after_a_restore_the_app_has_the_name_and_language_of_the_backup(
    auth_client, shop, monkeypatch, django_capture_on_commit_callbacks,
):
    old = backup_at(shop, timezone.now() - timedelta(days=2))
    read_settings = FakeProvisioner.read_settings

    def as_in_the_backup(self, shop):
        # The shop had another name and language when the backup was made; they were changed after it.
        values = read_settings(self, shop)
        values["general"]["name"] = "Sklep z kopii"
        values["region"]["language"] = "en_US"
        values["appearance"]["theme"] = "classic"  # a PrestaShop theme: not for this WooCommerce shop
        return values

    monkeypatch.setattr(FakeProvisioner, "read_settings", as_in_the_backup)

    assert restore(auth_client, django_capture_on_commit_callbacks, shop, old)["status"] == "succeeded"

    shop.refresh_from_db()
    assert shop.name == "Sklep z kopii"
    assert shop.config.language == "en_US"
    assert shop.config.template.slug == "storefront"
    assert auth_client.get(f"/api/shops/{shop.pk}/").data["name"] == "Sklep z kopii"


def test_failed_restore_gives_the_shop_its_state_back(
    auth_client, shop, monkeypatch, django_capture_on_commit_callbacks,
):
    old = backup_at(shop, timezone.now() - timedelta(days=1))
    attempts = []

    def restore_backup(self, restored_shop, snapshot_id):
        attempts.append(snapshot_id)
        if snapshot_id == old.snapshot_id:
            raise RuntimeError("restic: unexpected EOF")

    monkeypatch.setattr(FakeProvisioner, "restore_backup", restore_backup)

    done = restore(auth_client, django_capture_on_commit_callbacks, shop, old)

    assert done["status"] == "failed"
    assert done["error"] == backups.RESTORE_FAILED
    before = ShopBackup.objects.get(shop=shop, kind=Kind.BEFORE_RESTORE)
    assert attempts == [old.snapshot_id, before.snapshot_id]


def test_restore_that_cannot_be_undone_asks_for_a_hand(auth_client, shop, settings, django_capture_on_commit_callbacks):
    old = backup_at(shop, timezone.now() - timedelta(days=1))
    settings.FAKE_PROVISIONER_FAIL_AT_STEP = "restore_backup"

    done = restore(auth_client, django_capture_on_commit_callbacks, shop, old)

    assert done["status"] == "failed"
    assert done["error"] == backups.RESTORE_BROKEN


def test_without_a_backup_of_how_it_is_now_nothing_is_restored(
    auth_client, shop, monkeypatch, django_capture_on_commit_callbacks,
):
    old = backup_at(shop, timezone.now() - timedelta(days=1))

    def backup(self, copied, tag):
        raise RuntimeError("no space left on device")

    monkeypatch.setattr(FakeProvisioner, "backup", backup)

    done = restore(auth_client, django_capture_on_commit_callbacks, shop, old)

    assert done["error"] == backups.BACKUP_FAILED
    assert FakeProvisioner.restored == []


def test_a_backup_removed_after_it_was_picked_is_not_restored(auth_client, shop, django_capture_on_commit_callbacks):
    old = backup_at(shop, timezone.now() - timedelta(days=1))
    with django_capture_on_commit_callbacks(execute=False) as queued:
        response = auth_client.post(url(shop, f"{old.pk}/restore/"))
    old.delete()
    for callback in queued:
        callback()

    done = operation(auth_client, shop, response)

    assert done["error"] == backups.BACKUP_GONE
    assert FakeProvisioner.restored == []


def test_only_the_shops_own_successful_backups_can_be_restored(auth_client, shop, verified_user):
    other = other_shop(verified_user, "drugi")
    foreign = backup_at(other, timezone.now())
    failed = ShopBackup.objects.create(shop=shop, kind=Kind.NIGHTLY, status=ShopBackup.Status.FAILED)

    for backup in (foreign, failed):
        assert auth_client.post(url(shop, f"{backup.pk}/restore/")).status_code == 404


def test_restoring_waits_for_a_running_operation(auth_client, shop, verified_user):
    old = backup_at(shop, timezone.now())
    ShopOperation.objects.create(shop=shop, kind=ShopOperation.Kind.UPDATE_SETTINGS, status="running")

    assert auth_client.post(url(shop, f"{old.pk}/restore/")).status_code == 409
    assert auth_client.post(url(shop)).status_code == 409


def test_without_a_password_backups_are_off(auth_client, shop, monkeypatch):
    monkeypatch.setattr(FakeProvisioner, "can_back_up", lambda self: False)

    assert backups.back_up_all() == 0
    assert not ShopBackup.objects.exists()
    assert auth_client.get(url(shop)).data["enabled"] is False
    assert auth_client.post(url(shop)).status_code == 409


def test_other_owners_backups_are_hidden(api_client, shop):
    stranger = User.objects.create_user(email="obcy@example.com", password=PASSWORD, is_email_verified=True)
    api_client.force_authenticate(stranger)

    assert api_client.get(url(shop)).status_code == 404


# --- every night ---


def test_every_night_running_and_suspended_shops_are_copied(shop, verified_user):
    other_shop(verified_user, "zawieszony", Shop.Status.SUSPENDED)
    other_shop(verified_user, "nieudany", Shop.Status.FAILED)
    other_shop(verified_user, "usuniety", Shop.Status.DELETED)

    back_up_all_shops()

    copied = set(ShopBackup.objects.values_list("shop__slug", "kind", "status"))
    assert copied == {("moj-sklep", "nightly", "succeeded"), ("zawieszony", "nightly", "succeeded")}


def test_a_failed_backup_is_recorded_for_the_admin_and_the_night_goes_on(shop, verified_user, monkeypatch):
    other = other_shop(verified_user, "drugi")
    real = FakeProvisioner.backup

    def backup(self, copied, tag):
        if copied.pk == shop.pk:
            raise RuntimeError("restic: repository is locked")
        return real(self, copied, tag)

    monkeypatch.setattr(FakeProvisioner, "backup", backup)

    assert backups.back_up_all() == 1

    failed = ShopBackup.objects.get(shop=shop)
    assert failed.status == ShopBackup.Status.FAILED
    assert "locked" in failed.error
    assert list(backups.restorable(shop)) == []
    assert ShopBackup.objects.get(shop=other).status == ShopBackup.Status.SUCCEEDED


def test_a_shop_being_restored_is_not_copied_that_night(shop):
    ShopOperation.objects.create(shop=shop, kind=ShopOperation.Kind.RESTORE_BACKUP, status="running")

    backups.back_up_all()

    assert not ShopBackup.objects.filter(shop=shop).exists()


def test_the_last_week_and_month_are_kept(shop):
    now = local(2026, 11, 19, 3, 30)  # a Thursday, just after the nightly backups
    for days_ago in range(60):
        day = now - timedelta(days=days_ago)
        backup_at(shop, day.replace(hour=3, minute=0))
    backup_at(shop, local(2026, 11, 18, 15, 0), Kind.BEFORE_RESTORE)
    backup_at(shop, local(2026, 11, 17, 14, 0), Kind.MANUAL)

    removed = backups.maintain(now)

    kept = sorted(timezone.localtime(backup.created_at).strftime("%m-%d %H:%M") for backup in shop.backups.all())
    assert kept == [
        "11-01 03:00",  # the newest of the week before that, and of the one before
        "11-08 03:00",
        "11-13 03:00",  # the newest of each of the last 7 days
        "11-14 03:00",
        "11-15 03:00",
        "11-16 03:00",
        "11-17 14:00",
        "11-18 15:00",
        "11-19 03:00",
    ]
    assert removed == 62 - 9
    assert set(FakeProvisioner.snapshots) == set(shop.backups.values_list("snapshot_id", flat=True))


def test_everything_from_the_last_day_is_kept(shop):
    now = local(2026, 11, 19, 16, 0)
    for hour in (3, 9, 12, 15):
        backup_at(shop, local(2026, 11, 19, hour, 0), Kind.MANUAL)

    assert backups.maintain(now) == 0
    assert shop.backups.count() == 4


def test_a_deleted_shop_keeps_its_last_backup_for_two_weeks(shop, settings):
    settings.SHOPS_BACKUP_DELETED_DAYS = 14
    now = timezone.now()
    backup_at(shop, now - timedelta(days=4))
    last = backup_at(shop, now - timedelta(days=3), Kind.BEFORE_DELETE)
    shop.status = Shop.Status.DELETED
    shop.save()

    backups.maintain(now)
    assert list(shop.backups.all()) == [last]

    backups.maintain(now + timedelta(days=11))
    assert not shop.backups.exists()
    assert FakeProvisioner.snapshots == {}


def test_the_index_follows_the_repository(shop):
    now = timezone.now()
    listed = backup_at(shop, now - timedelta(days=1))
    lost = backup_at(shop, now - timedelta(hours=5))
    del FakeProvisioner.snapshots[lost.snapshot_id]
    unrecorded = Snapshot(id="a" * 64, host=f"shop-{shop.pk}", time=now - timedelta(hours=2), tags=("manual",), size=7)
    being_saved = Snapshot(id="b" * 64, host=f"shop-{shop.pk}", time=now - timedelta(minutes=1), tags=("manual",))
    of_a_shop_gone = Snapshot(id="c" * 64, host="shop-999999", time=now - timedelta(days=1))
    not_a_shop = Snapshot(id="d" * 64, host="something-else", time=now - timedelta(days=30))
    for snapshot in (unrecorded, being_saved, of_a_shop_gone, not_a_shop):
        FakeProvisioner.snapshots[snapshot.id] = snapshot

    backups.maintain(now)

    assert set(shop.backups.values_list("snapshot_id", "kind")) == {
        (listed.snapshot_id, "nightly"), (unrecorded.id, "manual"),
    }
    assert set(FakeProvisioner.snapshots) == {listed.snapshot_id, unrecorded.id, being_saved.id, not_a_shop.id}


def test_old_failures_are_cleared(shop):
    now = timezone.now()
    ShopBackup.objects.create(shop=shop, kind=Kind.NIGHTLY, status="failed", created_at=now - timedelta(days=8))
    recent = ShopBackup.objects.create(
        shop=shop, kind=Kind.NIGHTLY, status="failed", created_at=now - timedelta(days=2),
    )

    backups.maintain(now)

    assert list(ShopBackup.objects.all()) == [recent]


# --- deleting ---


def test_a_deleted_shop_is_copied_once_more(auth_client, shop, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        assert auth_client.delete(f"/api/shops/{shop.pk}/").status_code == 204

    last = ShopBackup.objects.get(shop=shop)
    assert last.kind == Kind.BEFORE_DELETE
    assert last.snapshot_id in FakeProvisioner.snapshots


def test_a_deleted_account_leaves_no_backups(auth_client, shop, django_capture_on_commit_callbacks):
    backup_at(shop, timezone.now() - timedelta(days=1))

    with django_capture_on_commit_callbacks(execute=True):
        response = auth_client.post("/api/auth/delete-account/", {"password": PASSWORD}, format="json")

    assert response.status_code == 204
    assert not ShopBackup.objects.exists()
    assert FakeProvisioner.snapshots == {}


def test_the_data_of_forgotten_backups_leaves_the_repository_the_next_night(monkeypatch):
    # Nothing to remove tonight, but the backups of an account deleted during the day are only forgotten so far.
    pruned = []
    monkeypatch.setattr(FakeProvisioner, "prune_backups", lambda self: pruned.append(True))

    assert backups.maintain() == 0

    assert pruned == [True]


# --- support ---


def test_backup_shops_copies_shops_now(shop, verified_user, capsys):
    other_shop(verified_user, "drugi")

    call_command("backup_shops", "moj-sklep", "nie-ma")

    out, err = capsys.readouterr()
    assert "moj-sklep: kopia" in out
    assert "nie-ma: nie ma takiego" in err
    assert list(ShopBackup.objects.values_list("shop__slug", "kind")) == [("moj-sklep", "manual")]


def test_restore_shop_lists_the_backups_and_restores_one(shop, capsys):
    old = backup_at(shop, local(2026, 11, 10, 3, 0))

    call_command("restore_shop", "moj-sklep")
    assert "10 listopada 2026, 03:00  Kopia nocna" in capsys.readouterr().out

    call_command("restore_shop", "moj-sklep", "--backup", str(old.pk))
    assert "przywrócony z kopii" in capsys.readouterr().out
    assert FakeProvisioner.restored == [old.snapshot_id]


def test_restore_shop_brings_back_a_deleted_shop(auth_client, shop, django_capture_on_commit_callbacks, capsys):
    with django_capture_on_commit_callbacks(execute=True):
        auth_client.delete(f"/api/shops/{shop.pk}/")
    last = ShopBackup.objects.get(shop=shop)

    with django_capture_on_commit_callbacks(execute=True):
        call_command("restore_shop", str(shop.pk), "--backup", str(last.pk))

    shop.refresh_from_db()
    assert shop.status == Shop.Status.ACTIVE
    assert FakeProvisioner.restored == [last.snapshot_id]
    assert "działa pod" in capsys.readouterr().out


def test_a_deleted_shop_whose_address_is_taken_stays_deleted(
    auth_client, shop, verified_user, django_capture_on_commit_callbacks,
):
    with django_capture_on_commit_callbacks(execute=True):
        auth_client.delete(f"/api/shops/{shop.pk}/")
    last = ShopBackup.objects.get(shop=shop)
    other_shop(verified_user, "moj-sklep")

    with pytest.raises(CommandError, match="ma już inny sklep"):
        call_command("restore_shop", str(shop.pk), "--backup", str(last.pk))
    assert FakeProvisioner.restored == []


# --- on the shop node ---


@pytest.fixture
def docker_client(settings):
    settings.SHOPS_BACKUP_PASSWORD = "backup-secret"
    settings.SHOPS_DB_ROOT_PASSWORD = "root-secret"
    client = MagicMock()
    helper = client.containers.run.return_value
    helper.wait.return_value = {"StatusCode": 0}
    return client


def provisioner_with(cls, client):
    provisioner = cls()
    # cached_property: an instance attribute replaces the real Docker client.
    provisioner.__dict__["client"] = client
    return provisioner


def test_a_backup_copies_the_shops_volume_read_only(shop, docker_client, settings):
    helper = docker_client.containers.run.return_value
    helper.logs.return_value = (
        b'{"message_type":"status","percent_done":0.5}\n'
        b'{"message_type":"summary","snapshot_id":"abc123","total_bytes_processed":215000000}\n'
    )

    made = provisioner_with(WooCommerceProvisioner, docker_client).backup(shop, "nightly")

    assert made == Backup(snapshot_id="abc123", size=215000000)
    (image, command), options = docker_client.containers.run.call_args
    assert image == settings.SHOPS_BACKUP_IMAGE
    assert command == ["backup", "nightly", "wp-content/cache", "wp-content/upgrade"]
    assert options["volumes"] == {
        "shops-backups": {"bind": "/repository", "mode": "rw"},
        "shops-backup-cache": {"bind": "/cache", "mode": "rw"},
        f"shop-{shop.pk}": {"bind": "/shop/files", "mode": "ro"},
    }
    assert options["environment"] == {
        "RESTIC_REPOSITORY": "/repository", "RESTIC_PASSWORD": "backup-secret", "RESTIC_CACHE_DIR": "/cache",
        "SHOP": f"shop-{shop.pk}", "SHOP_DB": f"shop_{shop.pk}", "DB_HOST": "shops-db", "MYSQL_PWD": "root-secret",
    }
    assert options["network"] == "shops"
    helper.remove.assert_called_once_with(force=True)


def test_a_shop_without_a_volume_has_nothing_to_back_up(shop, docker_client):
    docker_client.volumes.get.side_effect = NotFound("no such volume")

    with pytest.raises(NothingToBackUp):
        provisioner_with(WooCommerceProvisioner, docker_client).backup(shop, "before_delete")
    docker_client.containers.run.assert_not_called()


def test_a_failed_backup_container_reports_its_errors_and_goes(shop, docker_client):
    helper = docker_client.containers.run.return_value
    helper.wait.return_value = {"StatusCode": 12}
    helper.logs.return_value = b"Fatal: wrong password or no key found"

    with pytest.raises(ContainerCommandError, match="exited with 12: Fatal: wrong password"):
        provisioner_with(WooCommerceProvisioner, docker_client).backup(shop, "nightly")
    helper.remove.assert_called_once_with(force=True)


def test_restoring_puts_files_and_database_back_and_starts_the_shop_again(shop, docker_client, monkeypatch):
    provisioner = provisioner_with(WooCommerceProvisioner, docker_client)
    container = MagicMock()
    steps = []
    monkeypatch.setattr(provisioner, "_find_container", lambda shop: container)
    container.stop.side_effect = lambda: steps.append("stop")
    for name in ("step_create_database", "step_start_container", "after_restore", "update_address", "configure_mail"):
        monkeypatch.setattr(provisioner, name, lambda shop, name=name: steps.append(name))
    monkeypatch.setattr(provisioner, "set_admin_password", lambda shop, password: steps.append(("password", password)))
    monkeypatch.setattr(
        provisioner, "_backup_tool", lambda command, shop=None, files=None: steps.append((*command, files)),
    )
    ShopCredentials.objects.filter(shop=shop).update(admin_password="obecne-haslo")

    provisioner.restore_backup(shop, "abc123")

    assert steps == [
        "stop", "step_create_database", ("restore", "abc123", "rw"), "step_start_container", "after_restore",
        "update_address", "configure_mail", ("password", "obecne-haslo"),
    ]


def test_magento_rebuilds_its_search_index_after_a_restore(shop, monkeypatch):
    provisioner = MagentoProvisioner()
    commands = []
    monkeypatch.setattr(provisioner, "_magento", lambda shop, arguments, environment=None: commands.append(arguments))

    provisioner.after_restore(shop)

    assert commands == [["indexer:reindex"], ["cache:flush"]]


def test_the_repository_is_listed_and_leftover_containers_go(docker_client):
    leftover = MagicMock()
    docker_client.containers.list.return_value = [leftover]
    docker_client.containers.run.return_value.logs.return_value = (
        b'[{"id":"abc","short_id":"abc","time":"2026-11-19T03:00:08.253156951+01:00","hostname":"shop-7",'
        b'"tags":["nightly"],"paths":["/shop"],"summary":{"total_bytes_processed":2156}}]'
    )

    listed = provisioner_with(WooCommerceProvisioner, docker_client).list_backups()

    taken = local(2026, 11, 19, 3, 0, 8, 253156)
    assert listed == [Snapshot(id="abc", host="shop-7", time=taken, tags=("nightly",), size=2156)]
    leftover.remove.assert_called_once_with(force=True)
    (_, command), _ = docker_client.containers.run.call_args
    assert command == ["snapshots"]
