from django.db import models
from django.utils import timezone

from shops.models import Shop


class ShopHealth(models.Model):
    """The monitor's last finding for a running shop (monitoring/checks.py)."""

    shop = models.OneToOneField(Shop, on_delete=models.CASCADE, related_name="health")
    # Failed checks in a row and when the first one was; down_since dates from it.
    failures = models.PositiveIntegerField(default=0)
    failing_since = models.DateTimeField(null=True, blank=True)
    # Staff only; the owner just hears the shop doesn't work.
    problem = models.CharField(max_length=300, blank=True)
    # Owner and staff were told it's down, so they'll hear when it works again.
    alerted = models.BooleanField(default=False)
    # "start" or "restart": at most one repair per run of failures.
    repaired = models.CharField(max_length=10, blank=True)
    repaired_at = models.DateTimeField(null=True, blank=True)
    # Waiting for the container's healthcheck; the repair records the outcome.
    repairing = models.BooleanField(default=False)
    checked_at = models.DateTimeField(null=True, blank=True)
    last_ok_at = models.DateTimeField(null=True, blank=True)
    # Home page time at the last successful check.
    response_ms = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        verbose_name = "stan sklepu"
        verbose_name_plural = "stan sklepów"

    def __str__(self):
        return f"{self.shop}: {self.problem or 'działa'}"

    @property
    def down_since(self):
        """None until the owner has been told the shop is down."""
        return self.failing_since if self.alerted else None


class Incident(models.Model):
    """Staff hear when it starts and ends, unless it ended before the next check (for a shop: before the alert)."""

    class Kind(models.TextChoices):
        SHOP = "shop", "Sklep nie działa"
        SERVICE = "service", "Usługa serwera sklepów nie działa"
        DISK = "disk", "Mało miejsca na dysku"
        SERVER = "server", "Serwer sklepów prawie pełny"
        BACKUPS = "backups", "Kopie zapasowe"

    kind = models.CharField(max_length=20, choices=Kind.choices)
    # One open incident per key: "shop:24", "service:shops-db", "disk", "server:1", "backups:failed".
    key = models.CharField(max_length=100)
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, null=True, blank=True, related_name="incidents")
    summary = models.CharField(max_length=500)
    started_at = models.DateTimeField(default=timezone.now)
    resolved_at = models.DateTimeField(null=True, blank=True)
    alerted_at = models.DateTimeField(null=True, blank=True)
    # Automatic repair done, e.g. "restart".
    repaired = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ["-started_at", "-id"]
        verbose_name = "awaria"
        verbose_name_plural = "awarie"
        constraints = [
            models.UniqueConstraint(
                fields=["key"], condition=models.Q(resolved_at__isnull=True), name="one_open_incident",
            ),
        ]
        indexes = [models.Index(fields=["shop", "started_at"])]

    def __str__(self):
        return f"{self.get_kind_display()}: {self.summary}"


class Heartbeat(models.Model):
    """Last run of scheduled jobs: the monitor itself and the nightly backups."""

    name = models.CharField(max_length=50, unique=True)
    beat_at = models.DateTimeField()

    class Meta:
        verbose_name = "ostatnie uruchomienie"
        verbose_name_plural = "ostatnie uruchomienia"

    def __str__(self):
        return f"{self.name}: {self.beat_at:%Y-%m-%d %H:%M}"
