import hashlib
import hmac
import secrets

from django.conf import settings
from django.contrib.auth import password_validation
from django.core.files.storage import default_storage
from django.db import transaction
from django.utils import timezone
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from .models import EmailVerificationCode, PasswordResetCode, User
from .tasks import (
    send_account_deleted_email,
    send_password_changed_email,
    send_password_reset_email,
    send_verification_email,
)


class VerificationError(Exception):
    pass


class AccountDeletionBlocked(Exception):
    pass


def _hash_code(code):
    return hmac.new(settings.SECRET_KEY.encode(), code.encode(), hashlib.sha256).hexdigest()


def _new_code(model, user):
    code = f"{secrets.randbelow(1_000_000):06d}"
    model.objects.filter(user=user).delete()
    model.objects.create(
        user=user, code_hash=_hash_code(code), expires_at=timezone.now() + settings.EMAIL_VERIFICATION_CODE_TTL,
    )
    return code


def _check_code(record, code):
    """Raises VerificationError unless `code` matches; a wrong guess counts as an attempt."""
    if record is None or record.expires_at < timezone.now():
        raise VerificationError("Kod wygasł. Poproś o nowy kod.")
    if record.attempts >= settings.EMAIL_VERIFICATION_MAX_ATTEMPTS:
        raise VerificationError("Przekroczono liczbę prób. Poproś o nowy kod.")
    if not hmac.compare_digest(record.code_hash, _hash_code(code)):
        record.attempts += 1
        record.save(update_fields=["attempts"])
        raise VerificationError("Nieprawidłowy kod.")


def _cooled_down(model, user):
    existing = model.objects.filter(user=user).first()
    return existing is None or timezone.now() - existing.created_at >= settings.EMAIL_VERIFICATION_RESEND_COOLDOWN


def can_resend_verification_code(user):
    return _cooled_down(EmailVerificationCode, user)


def send_verification_code(user):
    with transaction.atomic():
        code = _new_code(EmailVerificationCode, user)
        transaction.on_commit(lambda: send_verification_email.delay(user.email, code))


def verify_email(user, code):
    if user.is_email_verified:
        return
    record = EmailVerificationCode.objects.filter(user=user).first()
    _check_code(record, code)
    user.is_email_verified = True
    user.save(update_fields=["is_email_verified"])
    record.delete()


def sign_out_everywhere(user):
    """
    Blacklists all refresh tokens (other devices drop out at their next refresh) and forgets all push devices;
    the phone still signed in registers again on its next start.
    """
    from push.services import forget_all_devices

    for token in OutstandingToken.objects.filter(user=user):
        BlacklistedToken.objects.get_or_create(token=token)
    forget_all_devices(user)


def _active_user(email):
    return User.objects.filter(email=email.strip().lower(), is_active=True).first()


def request_password_reset(email):
    """Never reveals whether the address has an account: unknown ones and repeats within the cooldown get no e-mail."""
    user = _active_user(email)
    if user is None or not _cooled_down(PasswordResetCode, user):
        return
    with transaction.atomic():
        code = _new_code(PasswordResetCode, user)
        transaction.on_commit(lambda: send_password_reset_email.delay(user.pk, code))


def reset_password(email, code, new_password):
    """
    Raises VerificationError for a wrong or expired code (also for unknown addresses), or Django's ValidationError
    for a weak password, which keeps the code usable. The code proves the address, so the e-mail becomes verified.
    """
    user = _active_user(email)
    record = PasswordResetCode.objects.filter(user=user).first() if user else None
    # Outside a transaction, so a wrong guess stays counted.
    _check_code(record, code)
    password_validation.validate_password(new_password, user)
    with transaction.atomic():
        # Single use, also when two requests bring it at once.
        if not PasswordResetCode.objects.filter(pk=record.pk).delete()[0]:
            raise VerificationError("Kod wygasł. Poproś o nowy kod.")
        user.set_password(new_password)
        user.is_email_verified = True
        user.save(update_fields=["password", "is_email_verified"])
        EmailVerificationCode.objects.filter(user=user).delete()
        sign_out_everywhere(user)
        transaction.on_commit(lambda: send_password_changed_email.delay(user.pk))
    return user


def delete_account(user):
    """
    Tears down every shop, ends the plan now without a refund and forgets the card. The user row stays, anonymised
    and unable to sign in, because paid payments (kept for tax law) point at it; the address is freed.
    """
    from billing.services import close_account
    from shops.services import ShopBeingSetUp, delete_all_shops
    from push.models import PushPreferences
    from shops.models import ShopMember

    with transaction.atomic():
        # Same lock as creating a shop, so no shop appears meanwhile.
        user = User.objects.select_for_update().get(pk=user.pk)
        if user.is_staff:
            raise AccountDeletionBlocked("Konto administratora usuń w panelu administracyjnym.")
        try:
            shops = delete_all_shops(user)
        except ShopBeingSetUp as busy:
            raise AccountDeletionBlocked(
                f"Sklep „{busy.shop.name}” jest właśnie zakładany. Poczekaj, aż będzie gotowy, i spróbuj ponownie.",
            ) from None
        close_account(user)
        email, avatar = user.email, user.avatar.name
        user.email = f"deleted-{user.pk}@deleted.invalid"
        user.first_name = user.last_name = ""
        user.avatar = ""
        user.set_unusable_password()
        user.is_active = False
        user.deleted_at = timezone.now()
        user.save()
        EmailVerificationCode.objects.filter(user=user).delete()
        PasswordResetCode.objects.filter(user=user).delete()
        sign_out_everywhere(user)
        PushPreferences.objects.filter(user=user).delete()
        ShopMember.objects.filter(user=user).delete()
        if avatar:
            transaction.on_commit(lambda: default_storage.delete(avatar))
        transaction.on_commit(lambda: send_account_deleted_email.delay(email, shops))
