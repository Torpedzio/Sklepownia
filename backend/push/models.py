from django.conf import settings
from django.db import models


class Topic(models.TextChoices):
    """The owner turns each topic on or off; Android shows each as its own channel."""

    NEW_ORDERS = "new_orders", "Nowe zamówienia"
    SHOPS = "shops", "Sklepy"
    BILLING = "billing", "Plan i płatności"


class PushDevice(models.Model):
    class Platform(models.TextChoices):
        IOS = "ios", "iOS"
        ANDROID = "android", "Android"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="push_devices")
    token = models.CharField(max_length=200, unique=True)
    platform = models.CharField(max_length=10, choices=Platform.choices)
    name = models.CharField(max_length=100, blank=True, help_text="Model telefonu, np. „Pixel 8”.")
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True, help_text="Ostatnie zgłoszenie z aplikacji.")

    class Meta:
        ordering = ["-last_seen_at"]
        verbose_name = "telefon z powiadomieniami"
        verbose_name_plural = "telefony z powiadomieniami"

    def __str__(self):
        return f"{self.name or self.get_platform_display()} ({self.user})"


class PushPreferences(models.Model):
    """No row means every topic is on."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="push_preferences")
    new_orders = models.BooleanField(default=True)
    shops = models.BooleanField(default=True)
    billing = models.BooleanField(default=True)

    class Meta:
        verbose_name = "ustawienia powiadomień"
        verbose_name_plural = "ustawienia powiadomień"

    def wants(self, topic):
        return getattr(self, Topic(topic).value)


class PushTicket(models.Model):
    """Taken by the push service; its receipt, checked later, says whether APNs/FCM took it too."""

    device = models.ForeignKey(PushDevice, on_delete=models.CASCADE, related_name="tickets")
    ticket_id = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["created_at"])]
