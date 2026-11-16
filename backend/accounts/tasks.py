from smtplib import SMTPException

from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMultiAlternatives, send_mail
from django.template.loader import render_to_string
from django.utils import formats, timezone

from .models import User


@shared_task
def send_verification_email(email, code):
    send_mail(
        subject="Twój kod weryfikacyjny",
        message=f"Twój kod weryfikacyjny to: {code}\n\nKod jest ważny przez 15 minut.",
        from_email=None,
        recipient_list=[email],
    )


@shared_task(autoretry_for=(OSError, SMTPException), retry_backoff=True, max_retries=5)
def send_password_changed_email(user_id):
    """Tells the owner their password changed, so a change they didn't make doesn't go unnoticed."""
    user = User.objects.get(pk=user_id)
    when = formats.date_format(timezone.localtime(), "j E Y, H:i")
    context = {
        "platform": settings.PLATFORM_NAME,
        "recipient": user.email,
        "heading": "Hasło zostało zmienione",
        "intro": f"Hasło do konta {user.email} zostało zmienione {when}. Na innych urządzeniach trzeba "
                 "zalogować się ponownie. Jeśli to nie Ty, napisz do nas od razu: odpowiedz na tę wiadomość.",
    }
    message = EmailMultiAlternatives(
        subject="Hasło do konta zostało zmienione",
        body=f"{context['heading']}\n\n{context['intro']}\n\n--\n{context['platform']}.",
        to=[user.email],
        reply_to=[settings.CONTACT_EMAIL],
    )
    message.attach_alternative(render_to_string("email/layout.html", context), "text/html")
    message.send()
