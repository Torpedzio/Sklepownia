from django.db import models
from django.utils import timezone

from shops.models import Shop


class ShopHealth(models.Model):
    """How the monitor last found a running shop (monitoring/checks.py)."""

    shop = models.OneToOneField(Shop, on_delete=models.CASCADE, related_name="health")
    # Failed checks in a row, and when the first of them was: from then on the shop counts as down.
    failures = models.PositiveIntegerField(default=0)
    failing_since = models.DateTimeField(null=True, blank=True)
    # What the last failed check found, for the staff (the owner only hears that the shop doesn't work).
    problem = models.CharField(max_length=300, blank=True)
    # The owner and the staff were told the shop is down; they hear when it works again.
    alerted = models.BooleanField(default=False)
    # What the monitor did in this run of failures (once per run): "start" or "restart" of the shop's container.
    repaired = models.CharField(max_length=10, blank=True)
    repaired_at = models.DateTimeField(null=True, blank=True)
    # The repair is under way (it waits for the container's healthcheck); it says how it went.
    repairing = models.BooleanField(default=False)
    checked_at = models.DateTimeField(null=True, blank=True)
    last_ok_at = models.DateTimeField(null=True, blank=True)
    # How long the home page took at the last successful check.
    response_ms = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        verbose_name = "stan sklepu"
        verbose_name_plural = "stan sklepów"

    def __str__(self):
        return f"{self.shop}: {self.problem or 'działa'}"

    @property
    def down_since(self):
        """Since when the shop doesn't work, as its owner was told; None while it works (or nobody was told yet)."""
        return self.failing_since if self.alerted else None


class Incident(models.Model):
    """
    Something that didn't work, from when it was noticed until it worked again. The staff hears about both,
    unless it was over before the next check (or, for a shop, before the owner had to be told).
    """

    class Kind(models.TextChoices):
        SHOP = "shop", "Sklep nie działa"
        SERVICE = "service", "Usługa serwera sklepów nie działa"
        DISK = "disk", "Mało miejsca na dysku"
        SERVER = "server", "Serwer sklepów prawie pełny"
        BACKUPS = "backups", "Kopie zapasowe"

    kind = models.CharField(max_length=20, choices=Kind.choices)
    # What it is about, one open incident each: "shop:24", "service:shops-db", "disk", "server:1", "backups:failed".
    key = models.CharField(max_length=100)
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, null=True, blank=True, related_name="incidents")
    summary = models.CharField(max_length=500)
    started_at = models.DateTimeField(default=timezone.now)
    resolved_at = models.DateTimeField(null=True, blank=True)
    alerted_at = models.DateTimeField(null=True, blank=True)
    # What the monitor did about it by itself, e.g. restarted the shop's container.
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
    """When something that runs on a schedule last ran: the monitor itself and the nightly backups."""

    name = models.CharField(max_length=50, unique=True)
    beat_at = models.DateTimeField()

    class Meta:
        verbose_name = "ostatnie uruchomienie"
        verbose_name_plural = "ostatnie uruchomienia"

    def __str__(self):
        return f"{self.name}: {self.beat_at:%Y-%m-%d %H:%M}"
