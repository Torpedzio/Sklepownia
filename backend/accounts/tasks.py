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
def send_password_reset_email(user_id, code):
    """The code for setting a new password. Ignoring the message leaves the old password working."""
    user = User.objects.get(pk=user_id)
    minutes = int(settings.EMAIL_VERIFICATION_CODE_TTL.total_seconds() // 60)
    context = {
        "platform": settings.PLATFORM_NAME,
        "recipient": user.email,
        "heading": "Ustaw nowe hasło",
        "intro": f"Ktoś poprosił o nowe hasło do konta {user.email}. Wpisz ten kod w aplikacji:",
        "code": code,
        "note": f"Kod działa przez {minutes} minut. Jeśli to nie Ty, zignoruj tę wiadomość: hasło się nie zmieni.",
    }
    message = EmailMultiAlternatives(
        subject="Kod do ustawienia nowego hasła",
        body=f"{context['heading']}\n\n{context['intro']} {code}\n\n{context['note']}\n\n--\n{context['platform']}.",
        to=[user.email],
        reply_to=[settings.CONTACT_EMAIL],
    )
    message.attach_alternative(render_to_string("accounts/email/code.html", context), "text/html")
    message.send()


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
