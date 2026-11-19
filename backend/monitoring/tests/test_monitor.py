from datetime import timedelta
from io import StringIO

import pytest
import requests
from django.core.management import call_command
from django.db import connection
from django.utils import timezone

from monitoring import alerts, checks
from monitoring.models import Heartbeat, Incident, ShopHealth
from push.models import PushDevice
from shops.models import Server, Shop, ShopBackup, ShopCredentials, ShopOperation, ShopSettings
from shops.provisioning.base import ContainerState, PageCheck
from shops.provisioning.fake import FakeProvisioner
from shops.tasks import back_up_all_shops

pytestmark = pytest.mark.django_db

TOKEN = "ExponentPushToken[abc123]"
DOWN = PageCheck(status=None, error="Strona nie odpowiedziała w 20 s.")


@pytest.fixture(autouse=True)
def _alerts(settings):
    settings.ALERT_EMAILS = ["dyzur@sklepownia.test"]
    settings.MONITOR_FAILURES = 2
    settings.MONITOR_PING_URL = ""
    settings.PLATFORM_NAME = "Sklepownia"


@pytest.fixture
def shop(auth_client, verified_user, django_capture_on_commit_callbacks, mailoutbox):
    payload = {"name": "Mój Sklep", "slug": "moj-sklep", "industry": "fashion", "template": "storefront"}
    with django_capture_on_commit_callbacks(execute=True):
        shop_id = auth_client.post("/api/shops/", payload, format="json").data["id"]
    # Not the e-mail with the shop's admin login.
    mailoutbox.clear()
    PushDevice.objects.create(user=verified_user, token=TOKEN, platform="android", name="Pixel 8")
    return Shop.objects.get(pk=shop_id)


@pytest.fixture
def round_(django_capture_on_commit_callbacks, mailoutbox, push_outbox):
    """Runs a round of checks, and what it queued (repairs, e-mails, notifications) as the worker would."""

    def run(**kwargs):
        with django_capture_on_commit_callbacks(execute=True):
            return checks.run(**kwargs)

    return run


def staff(mailoutbox):
    return [message.subject for message in mailoutbox if message.to == ["dyzur@sklepownia.test"]]


def owner(mailoutbox, shop):
    return [message.subject for message in mailoutbox if message.to == [shop.owner.email]]


def health(shop):
    return ShopHealth.objects.get(shop=shop)


# --- shops ---


def test_a_working_shop_is_noted(shop, round_, mailoutbox, push_outbox):
    result = round_()

    checked = health(shop)
    assert (checked.failures, checked.problem, checked.response_ms) == (0, "", 120)
    assert checked.last_ok_at is not None
    assert result.checked == 1 and result.failing == []
    assert not Incident.objects.exists()
    assert mailoutbox == [] and push_outbox == []


def test_a_stopped_container_is_started_at_once_without_bothering_anyone(shop, round_, mailoutbox, push_outbox):
    FakeProvisioner.containers[shop.pk] = ContainerState("exited")

    round_()

    assert FakeProvisioner.repairs == [(shop.pk, "start")]
    assert health(shop).failures == 0
    assert not Incident.objects.exists()
    assert mailoutbox == [] and push_outbox == []


def test_a_shop_that_doesnt_answer_twice_is_restarted(shop, round_, mailoutbox, push_outbox):
    FakeProvisioner.pages[shop.pk] = DOWN

    round_()
    # A single failed check may be a blip: nothing happens yet.
    assert health(shop).failures == 1
    assert FakeProvisioner.repairs == []

    round_()

    assert FakeProvisioner.repairs == [(shop.pk, "restart")]
    assert health(shop).failures == 0
    incident = Incident.objects.get()
    assert (incident.kind, incident.repaired, incident.alerted_at) == (Incident.Kind.SHOP, "restart", None)
    assert incident.resolved_at is not None
    # The monitor dealt with it: nobody is told.
    assert mailoutbox == [] and push_outbox == []


def test_when_the_restart_doesnt_help_the_owner_and_the_staff_are_told(
    shop, round_, auth_client, mailoutbox, push_outbox,
):
    FakeProvisioner.pages[shop.pk] = PageCheck(status=500, seconds=0.3)
    FakeProvisioner.repairs_help = False

    round_()
    round_()

    assert FakeProvisioner.repairs == [(shop.pk, "restart")]
    assert health(shop).alerted
    assert [(m.title, m.url, m.topic) for m in push_outbox] == [
        ("Sklep „Mój Sklep” nie działa", f"/shops/{shop.pk}", "shops"),
    ]
    assert owner(mailoutbox, shop) == ["Sklep „Mój Sklep” nie działa"]
    assert "Już to sprawdzamy" in mailoutbox[0].body
    assert "HTTP 500" not in mailoutbox[0].body
    (alert,) = staff(mailoutbox)
    assert alert == "[Sklepownia] Sklep moj-sklep (nr %d) nie działa" % shop.pk
    body = mailoutbox[-1].body
    assert "Strona główna odpowiada HTTP 500." in body
    assert "Samonaprawa: zrestartował kontener sklepu, nie pomogło." in body
    down_since = auth_client.get(f"/api/shops/{shop.pk}/").data["down_since"]
    assert down_since is not None
    assert auth_client.get("/api/shops/").data[0]["down_since"] == down_since

    # Still down: no more restarts, nobody is told again.
    round_()
    assert len(FakeProvisioner.repairs) == 1
    assert len(push_outbox) == 1 and len(mailoutbox) == 2

    # The staff fixed it: everybody hears.
    del FakeProvisioner.pages[shop.pk]
    round_()

    assert [m.title for m in push_outbox][1:] == ["Sklep „Mój Sklep” znowu działa"]
    assert owner(mailoutbox, shop)[1:] == ["Sklep „Mój Sklep” znowu działa"]
    assert staff(mailoutbox)[1:] == ["[Sklepownia] Sklep moj-sklep (nr %d) znowu działa" % shop.pk]
    assert Incident.objects.get().resolved_at is not None
    assert auth_client.get(f"/api/shops/{shop.pk}/").data["down_since"] is None
    checked = health(shop)
    assert (checked.failures, checked.alerted, checked.repaired) == (0, False, "")


def test_a_stopped_shop_that_wont_start_is_reported_at_the_second_check(
    shop, round_, settings, mailoutbox, push_outbox,
):
    FakeProvisioner.containers[shop.pk] = None
    settings.FAKE_PROVISIONER_FAIL_AT_STEP = "start"

    round_()
    assert FakeProvisioner.repairs == []
    assert health(shop).problem.startswith("Nie udało się uruchomić kontenera sklepu")
    assert mailoutbox == []

    round_()

    assert len(push_outbox) == 1
    assert "Samonaprawa: uruchomił kontener sklepu, nie pomogło." in mailoutbox[-1].body
    assert Incident.objects.get().repaired == "start"


def test_a_repair_under_way_is_not_counted_as_another_failure(shop, round_, mailoutbox):
    FakeProvisioner.pages[shop.pk] = DOWN
    round_()
    ShopHealth.objects.filter(shop=shop).update(
        failures=2, repaired="restart", repaired_at=timezone.now(), repairing=True,
    )

    round_()

    assert health(shop).failures == 2
    assert mailoutbox == []

    # A repair lost for long (e.g. the worker restarted) doesn't hold the alarm back.
    ShopHealth.objects.filter(shop=shop).update(repaired_at=timezone.now() - timedelta(minutes=11))
    round_()
    assert health(shop).alerted


def test_a_closed_shop_may_show_its_own_503_page(shop, round_):
    ShopSettings.objects.update_or_create(shop=shop, defaults={"values": {"availability": {"is_open": False}}})
    FakeProvisioner.pages[shop.pk] = PageCheck(status=503, seconds=0.2)

    round_()
    assert health(shop).failures == 0

    ShopSettings.objects.update_or_create(shop=shop, defaults={"values": {"availability": {"is_open": True}}})
    round_()
    assert health(shop).problem == "Strona główna odpowiada HTTP 503."


def test_the_platforms_fallback_page_means_the_proxy_skips_the_shop(shop, round_):
    FakeProvisioner.containers[shop.pk] = ContainerState("running", "unhealthy")
    FakeProvisioner.pages[shop.pk] = PageCheck(status=503, unavailable=True)
    FakeProvisioner.repairs_help = False

    round_()
    assert health(shop).problem == "Proxy nie kieruje ruchu do kontenera (healthcheck: unhealthy)."

    # After the restart the monitor says what it sees then.
    round_()
    assert FakeProvisioner.repairs == [(shop.pk, "restart")]
    assert health(shop).problem == "Proxy nie kieruje ruchu do kontenera (healthcheck: unhealthy)."
    assert health(shop).alerted


def test_busy_suspended_and_deleted_shops_are_not_checked(shop, verified_user, round_):
    ShopOperation.objects.create(shop=shop, kind=ShopOperation.Kind.RESTORE_BACKUP, status="running")
    Shop.objects.create(owner=verified_user, name="Z", slug="zawieszony", status=Shop.Status.SUSPENDED)
    Shop.objects.create(owner=verified_user, name="U", slug="usuniety", status=Shop.Status.DELETED)
    FakeProvisioner.pages[shop.pk] = DOWN

    result = round_()

    assert result.checked == 0
    assert not ShopHealth.objects.exists()


def test_a_shop_deleted_while_down_is_forgotten_quietly(shop, round_, mailoutbox, push_outbox):
    FakeProvisioner.pages[shop.pk] = DOWN
    FakeProvisioner.repairs_help = False
    round_()
    round_()
    assert health(shop).alerted
    sent = len(mailoutbox), len(push_outbox)

    Shop.objects.filter(pk=shop.pk).update(status=Shop.Status.DELETED)
    round_()

    assert Incident.objects.get().resolved_at is not None
    assert not ShopHealth.objects.exists()
    assert (len(mailoutbox), len(push_outbox)) == sent


def test_only_the_shops_asked_for(shop, verified_user, round_):
    other = Shop.objects.create(owner=verified_user, name="Drugi", slug="drugi", status=Shop.Status.ACTIVE)

    round_(slugs=["drugi"])

    assert list(ShopHealth.objects.values_list("shop", flat=True)) == [other.pk]


# --- the shop node ---


def test_without_the_proxy_shops_are_not_judged_and_the_staff_hears_at_the_second_check(
    shop, round_, settings, mailoutbox, push_outbox,
):
    FakeProvisioner.services[settings.SHOPS_PROXY_CONTAINER] = "Kontener nie działa (exited)."
    FakeProvisioner.pages[shop.pk] = DOWN

    result = round_()
    assert result.skipped == f"Sklepów nie sprawdzono: nie działa {settings.SHOPS_PROXY_CONTAINER}."
    assert not ShopHealth.objects.exists()
    assert mailoutbox == []

    round_()
    assert staff(mailoutbox) == [
        "[Sklepownia] Usługa serwera sklepów nie działa: shops-proxy: Kontener nie działa (exited).",
    ]
    assert push_outbox == []

    del FakeProvisioner.services[settings.SHOPS_PROXY_CONTAINER]
    del FakeProvisioner.pages[shop.pk]
    round_()
    assert staff(mailoutbox)[1:] == ["[Sklepownia] Naprawione: shops-proxy: Kontener nie działa (exited)."]


def test_without_docker_nothing_else_is_checked(shop, round_, mailoutbox):
    FakeProvisioner.services["docker"] = "Docker nie odpowiada."
    FakeProvisioner.disk = (1, 100)

    round_()
    round_()

    assert staff(mailoutbox) == ["[Sklepownia] Usługa serwera sklepów nie działa: docker: Docker nie odpowiada."]
    assert set(Incident.objects.values_list("key", flat=True)) == {"service:docker"}


def test_opensearch_matters_only_while_there_are_magento_shops(verified_user, round_, settings):
    FakeProvisioner.services[settings.SHOPS_SEARCH_CONTAINER] = "Nie ma takiego kontenera."

    round_()
    assert not Incident.objects.exists()

    Shop.objects.create(owner=verified_user, name="M", slug="mage", platform="magento", status=Shop.Status.ACTIVE)
    round_()
    assert Incident.objects.get().key == f"service:{settings.SHOPS_SEARCH_CONTAINER}"


def test_little_disk_space_is_reported(round_, mailoutbox):
    FakeProvisioner.disk = (5 * 1024**3, 100 * 1024**3)

    round_()
    round_()

    assert staff(mailoutbox) == [
        "[Sklepownia] Mało miejsca na dysku: Na dysku serwera sklepów zostało 5% miejsca (5,0\xa0GB z 100,0\xa0GB).",
    ]


def test_a_nearly_full_server_is_reported(verified_user, round_, mailoutbox, settings):
    settings.MONITOR_SERVER_FULL_PERCENT = 90
    server = Server.objects.create(name="node-1", hostname="node-1", max_shops=10)
    for number in range(9):
        Shop.objects.create(owner=verified_user, name=f"S{number}", slug=f"s{number}", server=server)
    Shop.objects.create(owner=verified_user, name="U", slug="u", server=server, status=Shop.Status.DELETED)

    round_()
    round_()

    assert len(staff(mailoutbox)) == 1
    assert "Serwer node-1 ma 9 z 10 sklepów" in mailoutbox[0].subject


# --- nightly backups ---


def test_backups_that_didnt_run_last_night_are_reported_at_once(round_, mailoutbox, django_capture_on_commit_callbacks):
    Heartbeat.objects.update_or_create(
        name=alerts.NIGHTLY_BACKUPS, defaults={"beat_at": timezone.now() - timedelta(hours=27)},
    )

    round_()
    (alert,) = staff(mailoutbox)
    assert alert.startswith("[Sklepownia] Kopie zapasowe: Nocne kopie zapasowe nie zrobiły się od ")

    with django_capture_on_commit_callbacks(execute=True):
        back_up_all_shops()
    round_()
    assert staff(mailoutbox)[1:] == [f"[Sklepownia] Naprawione: {Incident.objects.get().summary}"]


def test_failed_nightly_backups_are_reported(shop, verified_user, mailoutbox, monkeypatch,
                                             django_capture_on_commit_callbacks):
    other = Shop.objects.create(owner=verified_user, name="Drugi", slug="drugi", status=Shop.Status.ACTIVE)
    ShopCredentials.objects.create(shop=other, admin_login="admin")
    real = FakeProvisioner.backup

    def backup(self, copied, tag):
        raise RuntimeError("restic: repository is locked")

    monkeypatch.setattr(FakeProvisioner, "backup", backup)

    with django_capture_on_commit_callbacks(execute=True):
        back_up_all_shops()

    assert staff(mailoutbox) == [
        "[Sklepownia] Kopie zapasowe: Nocne kopie zapasowe nie udały się w 2 sklepach: moj-sklep, drugi.",
    ]
    assert ShopBackup.objects.filter(status=ShopBackup.Status.FAILED).count() == 2
    assert timezone.now() - Heartbeat.objects.get(name=alerts.NIGHTLY_BACKUPS).beat_at < timedelta(minutes=1)

    # The next night works: the incident is over, quietly.
    monkeypatch.setattr(FakeProvisioner, "backup", real)
    with django_capture_on_commit_callbacks(execute=True):
        back_up_all_shops()
    assert Incident.objects.get().resolved_at is not None


# --- the monitor itself ---


def test_each_round_pings_the_outside_watcher(round_, settings, monkeypatch):
    settings.MONITOR_PING_URL = "https://ping.example.com/abc"
    pinged = []
    monkeypatch.setattr(requests, "get", lambda url, timeout: pinged.append(url))

    round_()

    assert pinged == ["https://ping.example.com/abc"]
    assert Heartbeat.objects.filter(name=checks.MONITOR).exists()

    def unreachable(url, timeout):
        raise requests.ConnectionError("no route")

    monkeypatch.setattr(requests, "get", unreachable)
    round_()


def test_one_round_at_a_time(shop, round_):
    other = connection.copy()
    try:
        with other.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_lock(%s)", [checks.LOCK_ID])
        result = round_()
    finally:
        other.close()

    assert result.skipped == "Poprzednia runda jeszcze trwa."
    assert not ShopHealth.objects.exists()


def test_the_command_says_what_it_found(shop, verified_user, mailoutbox):
    other = Shop.objects.create(owner=verified_user, name="Drugi", slug="drugi", status=Shop.Status.ACTIVE)
    FakeProvisioner.pages[other.pk] = PageCheck(status=502, seconds=0.1)
    out, err = StringIO(), StringIO()

    call_command("check_shops", stdout=out, stderr=err)

    assert out.getvalue() == "Sprawdzone sklepy: 2, działa 1.\n"
    assert err.getvalue() == "drugi: Strona główna odpowiada HTTP 502.\n"


def test_outdated_containers_are_replaced_on_request(shop, monkeypatch):
    monkeypatch.setattr(FakeProvisioner, "container_outdated", lambda self, shop: True)
    out = StringIO()

    call_command("update_shop_containers", "moj-sklep", "nie-ma", "--dry-run", stdout=out, stderr=StringIO())
    assert out.getvalue() == "moj-sklep: do zastąpienia\n"
    assert FakeProvisioner.repairs == []

    call_command("update_shop_containers", stdout=out)
    assert out.getvalue().endswith("moj-sklep: kontener zastąpiony\n")
    assert FakeProvisioner.repairs == [(shop.pk, "start")]


def test_the_admin_shows_incidents_and_health(shop, round_, admin_client):
    FakeProvisioner.pages[shop.pk] = DOWN
    FakeProvisioner.repairs_help = False
    round_()
    round_()

    incidents = admin_client.get("/admin/monitoring/incident/?open=yes")
    assert incidents.status_code == 200
    assert "Strona główna nie odpowiada" in incidents.content.decode()
    assert admin_client.get(f"/admin/monitoring/incident/{Incident.objects.get().pk}/change/").status_code == 200
    assert admin_client.get("/admin/monitoring/shophealth/").status_code == 200
    assert admin_client.get("/admin/monitoring/heartbeat/").status_code == 200
