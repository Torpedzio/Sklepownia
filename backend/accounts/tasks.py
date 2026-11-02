from celery import shared_task
from django.core.mail import send_mail


@shared_task
def send_verification_email(email, code):
    send_mail(
        subject="Twój kod weryfikacyjny",
        message=f"Twój kod weryfikacyjny to: {code}\n\nKod jest ważny przez 15 minut.",
        from_email=None,
        recipient_list=[email],
    )
