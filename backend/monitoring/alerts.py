"""
Incidents and alerts: staff (ALERT_EMAILS) hear about lasting incidents and their end; a shop's owner hears when it
is down and back (push and e-mail).
"""

from django.db import transaction

import push.services as push

from . import texts
from .models import Heartbeat, Incident

NIGHTLY_BACKUPS = "nightly-backups"
# "w 1 sklepie", "w 3 sklepach".
SHOPS = ("sklepie", "sklepach", "sklepach")


def problem(kind, key, summary, now, alert_now=False):
    """Staff are alerted only if it still fails at the next check (blips go unnoticed), or at once with `alert_now`."""
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
    """Staff hear about it only if they were alerted and not `quietly`."""
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
    """Called once the shop counts as down and repairs didn't help."""
    health.alerted = True
    health.save(update_fields=["alerted"])
    incident.alerted_at = now
    incident.save(update_fields=["alerted_at"])
    since = health.failing_since
    push.notify(shop.owner_id, texts.shop_down_notice(shop, since))
    _email_owner(shop, "down", since)
    tell_staff(*texts.shop_down_for_staff(shop, health, incident))


def shop_back(shop, since, now):
    push.notify(shop.owner_id, texts.shop_back_notice(shop, since, now))
    _email_owner(shop, "back", since, now)
    tell_staff(*texts.shop_back_for_staff(shop, since, now))


def nightly_backups_done(failed, now):
    """`failed`: shops left without a backup."""
    Heartbeat.objects.update_or_create(name=NIGHTLY_BACKUPS, defaults={"beat_at": now})
    # Each night stands alone: last night's failures are over either way.
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
