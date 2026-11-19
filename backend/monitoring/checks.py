"""
The monitor. Every MONITOR_INTERVAL_MINUTES (Celery beat) one round checks:

- the shop node's shared services: Docker, the proxy and the shops' database (without them no shop can work, so
  the shops are not judged then), OpenSearch while there are Magento shops, and the shops' mail relay;
- every running shop: its container, and its home page visited through the proxy like a customer would;
- the disk the shops keep their data on, how full each server is, and whether the nightly backups ran.

A shop that fails MONITOR_FAILURES checks in a row is down. The monitor starts its stopped container at once and
restarts a running one that doesn't answer, once per run of failures; when that doesn't help, the owner and the
staff hear about it (alerts.py), and again when the shop works.
"""

import logging
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import timedelta

import requests
from django.conf import settings
from django.db import connection, transaction
from django.db.models import Count, Q
from django.template.defaultfilters import filesizeformat
from django.utils import timezone

from shops import backups
from shops.models import Server, Shop, ShopOperation, ShopSettings
from shops.platforms import Platform
from shops.provisioning import get_provisioner
from shops.provisioning.base import PageCheck
from shops.services import OPERATION_TIMEOUT, current_operation

from . import alerts, texts
from .models import Heartbeat, Incident, ShopHealth

logger = logging.getLogger(__name__)

START, RESTART = "start", "restart"
MONITOR = "monitor"
# Nightly backups that haven't run for this long are late (they run once a day).
BACKUPS_LATE_AFTER = timedelta(hours=26)
# A repair waits up to 5 minutes for the container's healthcheck; one that takes longer was lost (e.g. the worker
# restarted), and the rounds count the failures again.
REPAIR_TIMEOUT = timedelta(minutes=10)
# One round at a time (a PostgreSQL advisory lock): a slow round must not count a shop's failures twice.
LOCK_ID = 7_204_116


@dataclass(frozen=True)
class Finding:
    """What one check of a shop found: nothing wrong (no `problem`), or what is and how the monitor can help."""

    problem: str = ""
    repair: str = ""
    response_ms: int | None = None

    @property
    def ok(self):
        return not self.problem


@dataclass
class Round:
    """What a round found, for the check_shops command."""

    checked: int = 0
    failing: list = field(default_factory=list)
    services: dict = field(default_factory=dict)
    skipped: str = ""


def run(now=None, slugs=None):
    """One round of checks (of the shops at `slugs` only, when given). Returns a Round."""
    now = now or timezone.now()
    provisioner = get_provisioner()
    if not provisioner.can_monitor():
        return Round(skipped="Provisioner sklepów nie pozwala ich sprawdzać.")
    with _one_round_at_a_time() as mine:
        if not mine:
            return Round(skipped="Poprzednia runda jeszcze trwa.")
        result = Round(services=check_services(provisioner, now))
        blocking = {"docker", settings.SHOPS_PROXY_CONTAINER, settings.SHOPS_DB_CONTAINER} & set(result.services)
        if blocking:
            # Every shop would fail for a reason of ours, which the staff already hears about.
            result.skipped = f"Sklepów nie sprawdzono: nie działa {', '.join(sorted(blocking))}."
        else:
            check_shops(provisioner, now, result, slugs)
        if slugs is None:
            forget_stopped_shops(now)
        if "docker" not in result.services:
            check_disk(provisioner, now)
        check_servers(now)
        check_backups(now)
        Heartbeat.objects.update_or_create(name=MONITOR, defaults={"beat_at": now})
    ping()
    return result


# --- the shop node ---


def check_services(provisioner, now):
    """Opens and closes incidents of the shared services; returns {name: problem} of those that don't work."""
    required = [settings.SHOPS_PROXY_CONTAINER, settings.SHOPS_DB_CONTAINER]
    if Shop.objects.filter(status=Shop.Status.ACTIVE, platform=Platform.MAGENTO).exists():
        required.append(settings.SHOPS_SEARCH_CONTAINER)
    # The mail relay is checked when it is a container on the node (locally Mailpit, shops-mail).
    optional = [settings.SHOPS_SMTP_HOST] if settings.SHOPS_SMTP_HOST else []
    problems = provisioner.service_problems(required, optional)
    if "docker" in problems:
        alerts.problem(Incident.Kind.SERVICE, "service:docker", f"docker: {problems['docker']}", now)
        return problems
    alerts.solved("service:docker", now)
    for name in [*required, *optional]:
        if name in problems:
            alerts.problem(Incident.Kind.SERVICE, f"service:{name}", f"{name}: {problems[name]}", now)
        else:
            alerts.solved(f"service:{name}", now)
    return problems


def check_disk(provisioner, now):
    space = provisioner.disk_space()
    if not space:
        return
    free, total = space
    percent = free * 100 / total
    if percent < settings.MONITOR_DISK_MIN_FREE_PERCENT:
        alerts.problem(
            Incident.Kind.DISK, "disk",
            f"Na dysku serwera sklepów zostało {percent:.0f}% miejsca ({filesizeformat(free)} "
            f"z {filesizeformat(total)}).",
            now,
        )
    else:
        alerts.solved("disk", now)


def check_servers(now):
    servers = Server.objects.filter(is_active=True).annotate(
        live=Count("shops", filter=~Q(shops__status=Shop.Status.DELETED)),
    )
    for server in servers:
        key = f"server:{server.pk}"
        if server.max_shops and server.live * 100 >= server.max_shops * settings.MONITOR_SERVER_FULL_PERCENT:
            alerts.problem(
                Incident.Kind.SERVER, key,
                f"Serwer {server.name} ma {server.live} z {server.max_shops} sklepów. Dodaj serwer albo podnieś "
                "jego max_shops, zanim nowe sklepy przestaną się zakładać.",
                now,
            )
        else:
            alerts.solved(key, now)


def check_backups(now):
    if not backups.enabled():
        alerts.solved("backups:missing", now)
        return
    last = Heartbeat.objects.filter(name=alerts.NIGHTLY_BACKUPS).first()
    if last and now - last.beat_at > BACKUPS_LATE_AFTER:
        alerts.problem(
            Incident.Kind.BACKUPS, "backups:missing",
            f"Nocne kopie zapasowe nie zrobiły się od {texts.full_moment(last.beat_at)}. Działają beat i worker?",
            now, alert_now=True,
        )
    else:
        alerts.solved("backups:missing", now)


def ping():
    """Tells the outside watcher (MONITOR_PING_URL) the round is done; it raises the alarm when they stop."""
    if not settings.MONITOR_PING_URL:
        return
    try:
        requests.get(settings.MONITOR_PING_URL, timeout=10)
    except requests.RequestException:
        logger.warning("Pinging MONITOR_PING_URL failed", exc_info=True)


# --- shops ---


def check_shops(provisioner, now, result, slugs=None):
    shops = Shop.objects.filter(status=Shop.Status.ACTIVE).select_related("owner").order_by("pk")
    shops = list(shops.filter(slug__in=slugs) if slugs is not None else shops)
    # A restore or a settings change may stop or replace the container: those shops wait for the next round.
    busy = set(
        ShopOperation.objects.filter(
            shop__in=shops,
            status__in=[ShopOperation.Status.QUEUED, ShopOperation.Status.RUNNING],
            created_at__gte=now - OPERATION_TIMEOUT,
        ).values_list("shop_id", flat=True)
    )
    shops = [shop for shop in shops if shop.pk not in busy]
    states = provisioner.container_states()
    pages = visit([shop for shop in shops if (state := states.get(shop.pk)) and state.running])
    closed = closed_shops(shops)
    for shop in shops:
        finding = examine(states.get(shop.pk), pages.get(shop.pk), shop.pk in closed)
        record(shop, finding, now)
        result.checked += 1
        if not finding.ok:
            result.failing.append((shop, finding.problem))


def forget_stopped_shops(now):
    """
    A shop deleted or suspended while it was down: its incident is over, quietly, and when it runs again the
    monitor starts afresh (its owner doesn't hear it "works again").
    """
    stopped = Incident.objects.filter(kind=Incident.Kind.SHOP, resolved_at__isnull=True).exclude(
        shop__status=Shop.Status.ACTIVE,
    )
    for key in stopped.values_list("key", flat=True):
        alerts.solved(key, now, quietly=True)
    ShopHealth.objects.exclude(shop__status=Shop.Status.ACTIVE).delete()


def visit(shops):
    """{shop id: PageCheck} of each shop's home page, a few shops at a time."""

    def one(shop):
        try:
            return shop.pk, get_provisioner(shop.platform).check_page(shop)
        except Exception as exc:
            logger.exception("Checking the page of shop %s failed", shop.pk)
            return shop.pk, PageCheck(status=None, error=f"Sprawdzenie się nie udało ({exc.__class__.__name__}).")

    if not shops:
        return {}
    with ThreadPoolExecutor(max_workers=settings.MONITOR_WORKERS) as pool:
        return dict(pool.map(one, shops))


def closed_shops(shops):
    """Ids of the shops their owner closed for customers: their own 503 page is no fault."""
    stored = ShopSettings.objects.filter(shop__in=shops).values_list("shop_id", "values")
    return {shop_id for shop_id, values in stored if not values.get("availability", {}).get("is_open", True)}


def examine(state, page, closed=False):
    """A Finding from the shop's container and the visit to its home page (None when it wasn't visited)."""
    if state is None:
        return Finding("Nie ma kontenera sklepu.", START)
    if not state.running:
        return Finding(f"Kontener sklepu nie działa ({state.status}).", START)
    if page is None or page.status is None:
        return Finding(f"Strona główna nie odpowiada: {page.error if page else 'brak wyniku'}", RESTART)
    if page.unavailable:
        health = f" (healthcheck: {state.health})" if state.health else ""
        return Finding(f"Proxy nie kieruje ruchu do kontenera{health}.", RESTART)
    milliseconds = round(page.seconds * 1000) if page.seconds is not None else None
    if 200 <= page.status < 400 or (page.status == 503 and closed):
        return Finding(response_ms=milliseconds)
    return Finding(f"Strona główna odpowiada HTTP {page.status}.", RESTART)


def record(shop, finding, now):
    with transaction.atomic():
        health = _health(shop)
        health.checked_at = now
        if finding.ok:
            _works(shop, health, now, finding.response_ms)
        else:
            _fails(shop, health, now, finding)


def repair(shop_id, action):
    """
    Starts (START) or restarts (RESTART) the shop's container and checks it again (monitoring.tasks.repair_shop).
    When the shop still doesn't work and counts as down, its owner and the staff are told.
    """
    shop = Shop.objects.filter(pk=shop_id, status=Shop.Status.ACTIVE).select_related("owner").first()
    if shop is None or current_operation(shop) is not None:
        return
    provisioner = get_provisioner(shop.platform)
    try:
        if action == START:
            provisioner.start_shop(shop)
        else:
            provisioner.restart_shop(shop)
        state = provisioner.container_states().get(shop.pk)
        finding = examine(state, provisioner.check_page(shop), shop.pk in closed_shops([shop]))
    except Exception as exc:
        logger.exception("Repairing shop %s (%s) failed", shop.pk, action)
        finding = Finding(f"{texts.REPAIR_FAILED[action]}: {exc}"[:300], action)
    now = timezone.now()
    with transaction.atomic():
        health = _health(shop)
        incident = alerts.open_incident(f"shop:{shop.pk}")
        if incident is not None:
            incident.repaired = action
            incident.save(update_fields=["repaired"])
        if finding.ok:
            _works(shop, health, now, finding.response_ms)
            return
        health.problem = finding.problem[:300]
        health.repairing = False
        health.save(update_fields=["problem", "repairing"])
        if health.failures >= settings.MONITOR_FAILURES and not health.alerted:
            incident = incident or _shop_incident(shop, health)
            incident.repaired = action
            incident.save(update_fields=["repaired"])
            alerts.shop_down(shop, health, incident, now)


def _works(shop, health, now, response_ms):
    if health.failures or health.alerted:
        alerts.solved(f"shop:{shop.pk}", now, quietly=True)
        if health.alerted:
            alerts.shop_back(shop, health.failing_since, now)
    health.failures = 0
    health.failing_since = None
    health.problem = ""
    health.alerted = False
    health.repaired = ""
    health.repaired_at = None
    health.repairing = False
    health.last_ok_at = now
    health.response_ms = response_ms
    health.save()


def _fails(shop, health, now, finding):
    if health.repairing and now - health.repaired_at < REPAIR_TIMEOUT:
        # The monitor is starting or restarting the container right now; the repair tells how it went.
        health.save(update_fields=["checked_at"])
        return
    health.failures += 1
    health.failing_since = health.failing_since or now
    health.problem = finding.problem[:300]
    down = health.failures >= settings.MONITOR_FAILURES
    incident = _shop_incident(shop, health) if down else None
    # Once per run of failures: a stopped container at once, a running one when the shop counts as down.
    if finding.repair and not health.repaired and (finding.repair == START or down):
        health.repaired = finding.repair
        health.repaired_at = now
        health.repairing = True
        health.save()
        transaction.on_commit(lambda: _repair_later(shop.pk, finding.repair))
        return
    health.save()
    if down and not health.alerted:
        alerts.shop_down(shop, health, incident, now)


def _shop_incident(shop, health):
    """The shop's open incident, opened when the shop started failing."""
    incident = alerts.open_incident(f"shop:{shop.pk}")
    if incident is None:
        return Incident.objects.create(
            kind=Incident.Kind.SHOP, key=f"shop:{shop.pk}", shop=shop, summary=health.problem,
            started_at=health.failing_since, repaired=health.repaired,
        )
    if incident.summary != health.problem:
        incident.summary = health.problem
        incident.save(update_fields=["summary"])
    return incident


def _health(shop):
    ShopHealth.objects.get_or_create(shop=shop)
    return ShopHealth.objects.select_for_update().get(shop=shop)


def _repair_later(shop_id, action):
    from .tasks import repair_shop

    repair_shop.delay(shop_id, action)


@contextmanager
def _one_round_at_a_time():
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s)", [LOCK_ID])
        mine = cursor.fetchone()[0]
    try:
        yield mine
    finally:
        if mine:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(%s)", [LOCK_ID])
