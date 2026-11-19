"""
Incidents and who hears about them. The staff (ALERT_EMAILS) hears about every incident that lasts, and when it is
over; the owner of a shop hears when the shop is down and when it works again (push notification and e-mail).
"""

from django.db import transaction

import push.services as push

from . import texts
from .models import Heartbeat, Incident

NIGHTLY_BACKUPS = "nightly-backups"
# "w 1 sklepie", "w 3 sklepach".
SHOPS = ("sklepie", "sklepach", "sklepach")


def problem(kind, key, summary, now, alert_now=False):
    """
    Records that `key` doesn't work. The staff hears about it when it still doesn't at the next check, so a blip
    (e.g. a service restarted by hand) goes unnoticed; with `alert_now` at once.
    """
    incident = open_incident(key)
    if incident is None:
        incident = Incident.objects.create(kind=kind, key=key, summary=summary[:500], started_at=now)
        if not alert_now:
            return incident
    elif incident.summary != summary[:500]:
        incident.summary = summary[:500]
        incident.save(update_fields=["summary"])
    if incident.alerted_at is None:
        incident.alerted_at = now
        incident.save(update_fields=["alerted_at"])
        tell_staff(*texts.incident_for_staff(incident))
    return incident


def solved(key, now, quietly=False):
    """`key` works again; the staff hears about it if it heard about the problem (and not `quietly`)."""
    incident = open_incident(key)
    if incident is None:
        return
    incident.resolved_at = now
    incident.save(update_fields=["resolved_at"])
    if incident.alerted_at and not quietly:
        tell_staff(*texts.solved_for_staff(incident))


def open_incident(key):
    return Incident.objects.filter(key=key, resolved_at__isnull=True).first()


def shop_down(shop, health, incident, now):
    """The shop counts as down and the monitor can do no more: its owner and the staff are told."""
    health.alerted = True
    health.save(update_fields=["alerted"])
    incident.alerted_at = now
    incident.save(update_fields=["alerted_at"])
    since = health.failing_since
    push.notify(shop.owner_id, texts.shop_down_notice(shop, since))
    _email_owner(shop, "down", since)
    tell_staff(*texts.shop_down_for_staff(shop, health, incident))


def shop_back(shop, since, now):
    """A shop whose owner was told it is down works again."""
    push.notify(shop.owner_id, texts.shop_back_notice(shop, since, now))
    _email_owner(shop, "back", since, now)
    tell_staff(*texts.shop_back_for_staff(shop, since, now))


def nightly_backups_done(failed, now):
    """After the nightly backups (shops.tasks.back_up_all_shops): `failed` are the shops left without one."""
    Heartbeat.objects.update_or_create(name=NIGHTLY_BACKUPS, defaults={"beat_at": now})
    # Each night is told on its own: last night's failures are over either way.
    solved("backups:failed", now, quietly=bool(failed))
    if failed:
        names = ", ".join(shop.slug for shop in failed[:20]) + (" i inne" if len(failed) > 20 else "")
        problem(
            Incident.Kind.BACKUPS, "backups:failed",
            f"Nocne kopie zapasowe nie udały się w {len(failed)} {texts.plural(len(failed), SHOPS)}: {names}.",
            now, alert_now=True,
        )


def tell_staff(subject, body):
    from .tasks import send_staff_alert

    transaction.on_commit(lambda: send_staff_alert.delay(subject, body))


def _email_owner(shop, reason, since, until=None):
    from .tasks import send_shop_email

    transaction.on_commit(
        lambda: send_shop_email.delay(shop.pk, reason, since.isoformat(), until.isoformat() if until else None)
    )
