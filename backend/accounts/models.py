from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("Email is required")
        user = self.model(email=self.normalize_email(email).lower(), **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_email_verified", True)
        return self._create_user(email, password, **extra_fields)


class User(AbstractUser):
    username = None
    email = models.EmailField("adres e-mail", unique=True)
    is_email_verified = models.BooleanField(default=False)
    avatar = models.FileField("zdjęcie profilowe", upload_to="avatars/", blank=True)
    # The row of a deleted account stays, without personal data, because payments point at it.
    deleted_at = models.DateTimeField("usunięte", null=True, blank=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    def __str__(self):
        return self.email


class OneTimeCode(models.Model):
    """A 6-digit code sent by e-mail; only its hash is stored."""

    code_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)

    class Meta:
        abstract = True


class EmailVerificationCode(OneTimeCode):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="email_verification_code")


class PasswordResetCode(OneTimeCode):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="password_reset_code")
