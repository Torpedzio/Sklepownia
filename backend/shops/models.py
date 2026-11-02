from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q

from .choices import MAX_CATEGORY_COUNT, MIN_CATEGORY_COUNT, Country, Currency, Industry, Language
from .fields import EncryptedTextField


class InvalidTransition(Exception):
    pass


class Server(models.Model):
    """Host that runs shop containers."""

    name = models.CharField(max_length=100, unique=True)
    hostname = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    max_shops = models.PositiveIntegerField(default=50)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class ShopTemplate(models.Model):
    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    # WordPress theme slug from wordpress.org, installed with `wp theme install`.
    wp_theme = models.CharField(max_length=100)
    preview_image_url = models.URLField(blank=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name


class Shop(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Oczekuje"
        PROVISIONING = "provisioning", "Zakładanie"
        ACTIVE = "active", "Aktywny"
        FAILED = "failed", "Błąd"
        SUSPENDED = "suspended", "Zawieszony"
        DELETED = "deleted", "Usunięty"

    ALLOWED_TRANSITIONS = {
        Status.PENDING: {Status.PROVISIONING, Status.FAILED, Status.DELETED},
        Status.PROVISIONING: {Status.ACTIVE, Status.FAILED},
        Status.ACTIVE: {Status.SUSPENDED, Status.DELETED},
        Status.FAILED: {Status.PENDING, Status.DELETED},
        Status.SUSPENDED: {Status.ACTIVE, Status.DELETED},
        Status.DELETED: set(),
    }

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="shops")
    name = models.CharField(max_length=100)
    slug = models.CharField(max_length=30)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    server = models.ForeignKey(Server, on_delete=models.PROTECT, null=True, blank=True, related_name="shops")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["slug"],
                condition=~Q(status="deleted"),
                name="unique_slug_for_live_shops",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.slug})"

    @property
    def domain(self) -> str:
        return f"{self.slug}.{settings.SHOPS_BASE_DOMAIN}"

    @property
    def url(self) -> str:
        scheme, port = settings.SHOPS_URL_SCHEME, settings.SHOPS_HTTP_PORT
        default_port = {"http": 80, "https": 443}.get(scheme)
        return f"{scheme}://{self.domain}" + ("" if port == default_port else f":{port}")

    @property
    def admin_url(self) -> str:
        return f"{self.url}/wp-admin/"

    def can_transition_to(self, new_status):
        return new_status in self.ALLOWED_TRANSITIONS[self.status]

    def transition_to(self, new_status):
        if not self.can_transition_to(new_status):
            raise InvalidTransition(f"{self.status} -> {new_status}")
        self.status = new_status
        self.save(update_fields=["status", "updated_at"])


class ShopConfig(models.Model):
    """What the user chose in the creation form; input for provisioning."""

    shop = models.OneToOneField(Shop, on_delete=models.CASCADE, related_name="config")
    industry = models.CharField(max_length=30, choices=Industry.choices)
    template = models.ForeignKey(ShopTemplate, on_delete=models.PROTECT, related_name="+")
    category_count = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(MIN_CATEGORY_COUNT), MaxValueValidator(MAX_CATEGORY_COUNT)],
    )
    language = models.CharField(max_length=10, choices=Language.choices, default=Language.PL)
    currency = models.CharField(max_length=3, choices=Currency.choices, default=Currency.PLN)
    country = models.CharField(max_length=2, choices=Country.choices, default=Country.PL)
    contact_email = models.EmailField()
    description = models.TextField(blank=True, max_length=500)
    include_sample_products = models.BooleanField(default=True)


class ShopCredentials(models.Model):
    """Secrets of one shop. Each is saved before it's used, so a retried provisioning reuses it."""

    shop = models.OneToOneField(Shop, on_delete=models.CASCADE, related_name="credentials")
    db_password = EncryptedTextField(blank=True)
    wp_admin_username = models.CharField(max_length=60)
    wp_admin_password = EncryptedTextField(blank=True)
    # Used by the platform for the WordPress/WooCommerce REST API (Basic Auth).
    wp_application_password = EncryptedTextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "shop credentials"


class ProvisioningJob(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "W kolejce"
        RUNNING = "running", "W trakcie"
        SUCCEEDED = "succeeded", "Zakończone"
        FAILED = "failed", "Błąd"

    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name="provisioning_jobs")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.QUEUED)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]


class ProvisioningStep(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Oczekuje"
        RUNNING = "running", "W trakcie"
        DONE = "done", "Gotowe"
        FAILED = "failed", "Błąd"

    job = models.ForeignKey(ProvisioningJob, on_delete=models.CASCADE, related_name="steps")
    key = models.CharField(max_length=50)
    label = models.CharField(max_length=100)
    order = models.PositiveSmallIntegerField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    error = models.TextField(blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["order"]
        constraints = [
            models.UniqueConstraint(fields=["job", "key"], name="unique_step_per_job"),
        ]
