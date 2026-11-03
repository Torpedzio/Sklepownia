from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMessage

from .models import ContactMessage


@shared_task
def notify_about_contact_message(message_id):
    message = ContactMessage.objects.get(pk=message_id)
    EmailMessage(
        subject=f"[Kontakt] {message.get_topic_display()} od {message.name}",
        body=f"Od: {message.name} <{message.email}>\n\n{message.message}",
        to=[settings.CONTACT_EMAIL],
        # Replying goes straight to the sender.
        reply_to=[message.email],
    ).send()
