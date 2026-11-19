from celery import shared_task

from . import services
from .senders.base import PushUnavailable


@shared_task(autoretry_for=(PushUnavailable,), retry_backoff=30, max_retries=5)
def send_push(user_id, topic, title, body, url):
    services.send(user_id, topic, title, body, url)


@shared_task
def check_push_receipts():
    services.check_receipts()
