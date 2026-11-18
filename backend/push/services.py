"""
Push notifications to the owner's phones. Other apps call `notify` with a Notice from `messages.py`; the worker
sends it to every phone of the user that wants the topic.
"""

import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .models import PushDevice, PushPreferences, PushTicket, Topic
from .senders import get_sender
from .senders.base import DEVICE_NOT_REGISTERED, Message

logger = logging.getLogger(__name__)

# Expo's advice: receipts are ready about 15 minutes after sending, and gone after a day.
RECEIPT_AFTER = timedelta(minutes=15)
RECEIPT_KEPT_FOR = timedelta(days=1)
RECEIPTS_PER_ROUND = 5000
TITLE_LENGTH = 120
BODY_LENGTH = 300


def register_device(user, token, platform, name=""):
    """Remembers the phone for `user`. A phone that changed accounts moves to the new one. Returns (device, created)."""
    return PushDevice.objects.update_or_create(
        token=token, defaults={"user": user, "platform": platform, "name": name[:100]},
    )


def forget_device(user, token):
    PushDevice.objects.filter(user=user, token=token).delete()


def forget_all_devices(user):
    """After signing out everywhere or deleting the account: no phone gets the user's notifications any more."""
    PushDevice.objects.filter(user=user).delete()


def preferences(user):
    return PushPreferences.objects.get_or_create(user=user)[0]


def notify(user_id, notice):
    """Sends `notice` to the user's phones once the current transaction commits (nothing, when there are none)."""
    from .tasks import send_push

    if not PushDevice.objects.filter(user_id=user_id).exists():
        return
    transaction.on_commit(
        lambda: send_push.delay(user_id, Topic(notice.topic).value, notice.title, notice.body, notice.url)
    )


def send(user_id, topic, title, body, url):
    """Sends to each phone of the user, if the user wants the topic. Returns how many the push service took."""
    chosen = PushPreferences.objects.filter(user_id=user_id).first()
    if chosen and not chosen.wants(topic):
        return 0
    devices = list(PushDevice.objects.filter(user_id=user_id))
    if not devices:
        return 0
    messages = [
        Message(token=device.token, title=title[:TITLE_LENGTH], body=body[:BODY_LENGTH], url=url, topic=topic)
        for device in devices
    ]
    tickets = get_sender().send(messages)
    taken, gone = [], []
    for device, ticket in zip(devices, tickets):
        if ticket.ok:
            taken.append(PushTicket(device=device, ticket_id=ticket.id))
        elif ticket.error == DEVICE_NOT_REGISTERED:
            gone.append(device.pk)
        else:
            logger.warning("Push to device %s refused: %s %s", device.pk, ticket.error, ticket.message)
    PushTicket.objects.bulk_create(taken, ignore_conflicts=True)
    PushDevice.objects.filter(pk__in=gone).delete()
    return len(taken)


def check_receipts(now=None):
    """
    Run regularly (Celery beat): reads the receipts of notifications sent a while ago. Phones that no longer take
    them are forgotten; other refusals (e.g. wrong FCM or APNs credentials) go to the log.
    """
    now = now or timezone.now()
    PushTicket.objects.filter(created_at__lt=now - RECEIPT_KEPT_FOR).delete()
    tickets = list(
        PushTicket.objects.filter(created_at__lte=now - RECEIPT_AFTER).order_by("created_at")[:RECEIPTS_PER_ROUND]
    )
    if not tickets:
        return
    receipts = get_sender().receipts([ticket.ticket_id for ticket in tickets])
    checked, gone = [], set()
    for ticket in tickets:
        receipt = receipts.get(ticket.ticket_id)
        if receipt is None:
            # Not ready yet: asked again next round, until a day passes.
            continue
        checked.append(ticket.pk)
        if receipt.ok:
            continue
        if receipt.error == DEVICE_NOT_REGISTERED:
            gone.add(ticket.device_id)
        else:
            logger.error("Push to device %s not delivered: %s %s", ticket.device_id, receipt.error, receipt.message)
    PushTicket.objects.filter(pk__in=checked).delete()
    PushDevice.objects.filter(pk__in=gone).delete()
