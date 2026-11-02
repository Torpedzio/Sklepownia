import hashlib
import hmac
import secrets

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import EmailVerificationCode
from .tasks import send_verification_email


class VerificationError(Exception):
    pass


def _hash_code(code):
    return hmac.new(settings.SECRET_KEY.encode(), code.encode(), hashlib.sha256).hexdigest()


def can_resend_verification_code(user):
    existing = EmailVerificationCode.objects.filter(user=user).first()
    if existing is None:
        return True
    return timezone.now() - existing.created_at >= settings.EMAIL_VERIFICATION_RESEND_COOLDOWN


def send_verification_code(user):
    code = f"{secrets.randbelow(1_000_000):06d}"
    with transaction.atomic():
        EmailVerificationCode.objects.filter(user=user).delete()
        EmailVerificationCode.objects.create(
            user=user,
            code_hash=_hash_code(code),
            expires_at=timezone.now() + settings.EMAIL_VERIFICATION_CODE_TTL,
        )
        transaction.on_commit(lambda: send_verification_email.delay(user.email, code))


def verify_email(user, code):
    if user.is_email_verified:
        return
    record = EmailVerificationCode.objects.filter(user=user).first()
    if record is None or record.expires_at < timezone.now():
        raise VerificationError("Kod wygasł. Poproś o nowy kod.")
    if record.attempts >= settings.EMAIL_VERIFICATION_MAX_ATTEMPTS:
        raise VerificationError("Przekroczono liczbę prób. Poproś o nowy kod.")
    if not hmac.compare_digest(record.code_hash, _hash_code(code)):
        record.attempts += 1
        record.save(update_fields=["attempts"])
        raise VerificationError("Nieprawidłowy kod.")
    user.is_email_verified = True
    user.save(update_fields=["is_email_verified"])
    record.delete()
