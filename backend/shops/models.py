import json

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone

from .choices import MAX_CATEGORY_COUNT, MIN_CATEGORY_COUNT, Country, Currency, Industry, Language
from .fields import EncryptedTextField
from .platforms import Platform, platform_info


class InvalidTransition(Exception):
    pass


class Server(models.Model):
    name = models.CharField(max_length=100, unique=True)
    hostname = models.CharField(max_length=255)
    # Outgoing address of the shops; Przelewy24 only answers whitelisted IPs.
    public_ip = models.GenericIPAddressField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    max_shops = models.PositiveIntegerField(default=50)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class ShopTemplate(models.Model):
    slug = models.SlugField(unique=True)
    platform = models.CharField(max_length=20, choices=Platform.choices, default=Platform.WOOCOMMERCE)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    # WordPress theme slug, PrestaShop theme directory or Magento theme path (Magento/luma).
    theme = models.CharField(max_length=100)
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
        SUSPENDED = "suspended", "Niedostępny w obecnym planie"
        DELETED = "deleted", "Usunięty"

    ALLOWED_TRANSITIONS = {
        Status.PENDING: {Status.PROVISIONING, Status.FAILED, Status.DELETED},
        Status.PROVISIONING: {Status.ACTIVE, Status.FAILED},
        Status.ACTIVE: {Status.SUSPENDED, Status.DELETED},
        Status.FAILED: {Status.PENDING, Status.SUSPENDED, Status.DELETED},
        Status.SUSPENDED: {Status.ACTIVE, Status.FAILED, Status.DELETED},
        Status.DELETED: set(),
    }

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="shops")
    name = models.CharField(max_length=100)
    slug = models.CharField(max_length=30)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    platform = models.CharField(max_length=20, choices=Platform.choices, default=Platform.WOOCOMMERCE)
    # Relative to the shop URL; PrestaShop picks a random one at installation.
    admin_path = models.CharField(max_length=64, blank=True)
    server = models.ForeignKey(Server, on_delete=models.PROTECT, null=True, blank=True, related_name="shops")
    # From before paid plans: need no plan and don't count towards its limit.
    is_test = models.BooleanField(default=False)
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
    def mail_sender(self) -> str:
        """Replies go to the shop's contact address."""
        return f"{self.slug}@{settings.SHOPS_MAIL_DOMAIN}"

    @property
    def admin_url(self) -> str | None:
        path = self.admin_path or platform_info(self.platform).admin_path
        return f"{self.url}/{path}/" if path else None

    def can_transition_to(self, new_status):
        return new_status in self.ALLOWED_TRANSITIONS[self.status]

    def transition_to(self, new_status):
        if not self.can_transition_to(new_status):
            raise InvalidTransition(f"{self.status} -> {new_status}")
        self.status = new_status
        self.save(update_fields=["status", "updated_at"])


class ShopMember(models.Model):
    """Runs the shop with its owner (the staff role). The owner is Shop.owner, never a member."""

    class Role(models.TextChoices):
        OWNER = "owner", "Właściciel"
        STAFF = "staff", "Obsługa"

    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name="members")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="shop_memberships")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["shop", "user"], name="unique_shop_member")]

    def __str__(self):
        return f"{self.user} w {self.shop}"


class ShopInvitation(models.Model):
    """An address invited to the staff; whoever signs in with it verified can join (shops/team.py)."""

    VALID_DAYS = 7

    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name="invitations")
    # Lowercase, like account e-mails.
    email = models.EmailField()
    invited_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["shop", "email"], name="unique_shop_invitation")]

    def __str__(self):
        return f"{self.email} do {self.shop}"

    @property
    def expired(self):
        return self.expires_at <= timezone.now()


class ShopConfig(models.Model):
    """Creation form input for provisioning; settings changed in the app are written back here."""

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
    """Each secret is saved before it's used, so a retried provisioning reuses it."""

    shop = models.OneToOneField(Shop, on_delete=models.CASCADE, related_name="credentials")
    db_password = EncryptedTextField(blank=True)
    # A username (WordPress) or an e-mail (PrestaShop).
    admin_login = models.CharField(max_length=254)
    admin_password = EncryptedTextField(blank=True)
    # For the shop's REST API: WooCommerce application password, PrestaShop webservice key, Magento integration token.
    api_key = EncryptedTextField(blank=True)
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


class ShopSettings(models.Model):
    """Cache of the shop's settings; the shop is the source of truth, re-read on opening and after every change."""

    shop = models.OneToOneField(Shop, on_delete=models.CASCADE, related_name="store_settings")
    values = models.JSONField(default=dict)
    synced_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "shop settings"


class ShopOperation(models.Model):
    """Owner-requested work on a running shop, one at a time per shop."""

    class Kind(models.TextChoices):
        UPDATE_SETTINGS = "update_settings", "Zmiana ustawień"
        SYNC_SETTINGS = "sync_settings", "Odczyt ustawień ze sklepu"
        RESET_ADMIN_PASSWORD = "reset_admin_password", "Nowe hasło administratora"
        REMOVE_SAMPLE_PRODUCTS = "remove_sample_products", "Usunięcie przykładowych produktów"
        PUBLISH_DOCUMENTS = "publish_documents", "Nowa wersja regulaminu i polityki prywatności"
        CREATE_BACKUP = "create_backup", "Kopia zapasowa"
        RESTORE_BACKUP = "restore_backup", "Przywrócenie kopii zapasowej"

    class Status(models.TextChoices):
        QUEUED = "queued", "W kolejce"
        RUNNING = "running", "W trakcie"
        SUCCEEDED = "succeeded", "Zakończone"
        FAILED = "failed", "Błąd"

    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name="operations")
    kind = models.CharField(max_length=30, choices=Kind.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.QUEUED)
    # Settings changes: {section: {field: new value}}, keys as SECRET_PLACEHOLDER.
    changes = models.JSONField(default=dict, blank=True)
    # Keys of a settings change (JSON like `changes`), cleared when the operation ends; only the shop keeps them.
    secrets = EncryptedTextField(blank=True)
    # E.g. {"removed": 6} for removed sample products.
    result = models.JSONField(default=dict, blank=True)
    # Made (create_backup) or restored (restore_backup).
    backup = models.ForeignKey("ShopBackup", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    error = models.TextField(blank=True)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.get_kind_display()} – {self.shop}"

    @property
    def secret_values(self):
        return json.loads(self.secrets) if self.secrets else {}


class ShopEvent(models.Model):
    """One line of a shop's history: who did what and when (shops/history.py)."""

    class Kind(models.TextChoices):
        SHOP_CREATED = "shop_created", "Założenie sklepu"
        SETUP_RETRIED = "setup_retried", "Ponowienie zakładania"
        SUSPENDED = "suspended", "Zawieszenie sklepu"
        RESUMED = "resumed", "Przywrócenie sklepu"
        OPERATION = "operation", "Zmiana w sklepie"
        ADMIN_ACCESS_SENT = "admin_access_sent", "Wysłanie danych logowania do panelu"
        INVITATION_SENT = "invitation_sent", "Zaproszenie do zespołu"
        INVITATION_REVOKED = "invitation_revoked", "Cofnięcie zaproszenia"
        INVITATION_DECLINED = "invitation_declined", "Odrzucenie zaproszenia"
        MEMBER_JOINED = "member_joined", "Dołączenie do zespołu"
        MEMBER_REMOVED = "member_removed", "Usunięcie z zespołu"
        MEMBER_LEFT = "member_left", "Odejście z zespołu"
        # data: {"number"}, and {"tracking_number", "carrier"} when shipped.
        ORDER_PAID = "order_paid", "Opłacenie zamówienia"
        ORDER_SHIPPED = "order_shipped", "Wysłanie zamówienia"
        ORDER_CANCELLED = "order_cancelled", "Anulowanie zamówienia"
        # data: {"name", "before", "after"}; a count is null when the shop didn't count the pieces.
        PRODUCT_STOCK = "product_stock", "Zmiana stanu produktu"
        # data: {"name"}, and {"fields"} (the changed fields' names) when edited.
        PRODUCT_CREATED = "product_created", "Dodanie produktu"
        PRODUCT_UPDATED = "product_updated", "Zmiana produktu"
        PRODUCT_DELETED = "product_deleted", "Usunięcie produktu"

    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name="events")
    kind = models.CharField(max_length=30, choices=Kind.choices)
    # Null: the platform itself (e.g. a plan change suspended the shop).
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    # OPERATION: its kind, changes and outcome.
    operation = models.ForeignKey(ShopOperation, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    # E.g. {"email": ...} for invitations, {"email", "name"} of a removed member.
    data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["shop", "-created_at"], name="shop_event_history")]

    def __str__(self):
        return f"{self.get_kind_display()} – {self.shop}"


class ShopOrderNote(models.Model):
    """A note the shop's team keeps on an order, in the platform's database: the shop's own notes differ by platform."""

    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name="order_notes")
    # Not a ShopOrder: the copy keeps 90 days, notes stay as long as the shop.
    external_id = models.CharField(max_length=40)
    # Null: a deleted account.
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    text = models.TextField()
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [models.Index(fields=["shop", "external_id"], name="shop_order_notes")]

    def __str__(self):
        return f"{self.shop} #{self.external_id}"


class ShopBackup(models.Model):
    """Index entry for a restic snapshot of the shop's files and database (see shops/backups.py)."""

    class Kind(models.TextChoices):
        NIGHTLY = "nightly", "Kopia nocna"
        MANUAL = "manual", "Kopia na żądanie"
        BEFORE_RESTORE = "before_restore", "Stan sprzed przywrócenia kopii"
        BEFORE_DELETE = "before_delete", "Stan sprzed usunięcia sklepu"

    class Status(models.TextChoices):
        SUCCEEDED = "succeeded", "Gotowa"
        FAILED = "failed", "Błąd"

    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name="backups")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SUCCEEDED)
    snapshot_id = models.CharField(max_length=64, blank=True)
    # Bytes, before deduplication and compression.
    size = models.PositiveBigIntegerField(null=True, blank=True)
    # Admin only: may name internals.
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["snapshot_id"], condition=~Q(snapshot_id=""), name="unique_backup_snapshot"),
        ]
        indexes = [models.Index(fields=["shop", "created_at"])]

    def __str__(self):
        return f"{self.shop} – {self.get_kind_display()} {self.created_at:%Y-%m-%d %H:%M}"


class ShopOrder(models.Model):
    """Recent orders copied for shops/sales.py; of the customer only the first name and last-name initial."""

    class Status(models.TextChoices):
        NEW = "new", "Nowe"
        PROCESSING = "processing", "W realizacji"
        COMPLETED = "completed", "Zrealizowane"
        CANCELLED = "cancelled", "Anulowane"
        # Checkout started but not paid (e.g. abandoned online payment); not a sale.
        UNFINISHED = "unfinished", "Nieopłacone"

    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name="orders")
    # The platform's id, and the number shown to customers.
    external_id = models.CharField(max_length=40)
    number = models.CharField(max_length=40)
    status = models.CharField(max_length=20, choices=Status.choices)
    total = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3)
    items = models.PositiveIntegerField(default=0)
    customer = models.CharField(max_length=80, blank=True)
    placed_at = models.DateTimeField()
    changed_at = models.DateTimeField()

    class Meta:
        ordering = ["-placed_at", "-id"]
        constraints = [models.UniqueConstraint(fields=["shop", "external_id"], name="unique_shop_order")]
        indexes = [models.Index(fields=["shop", "placed_at"])]

    def __str__(self):
        return f"{self.shop} #{self.number}"


class SalesSync(models.Model):
    shop = models.OneToOneField(Shop, on_delete=models.CASCADE, related_name="sales_sync")
    # Newest order change read; the next read starts a little before it.
    cursor = models.DateTimeField(null=True, blank=True)
    # Last successful read, and last attempt (also failed).
    synced_at = models.DateTimeField(null=True, blank=True)
    attempted_at = models.DateTimeField(null=True, blank=True)
    # When opening the overview with stale data queued a read.
    requested_at = models.DateTimeField(null=True, blank=True)
    error = models.CharField(max_length=300, blank=True)

    def __str__(self):
        return f"{self.shop}: {self.synced_at}"


class ShopChecklist(models.Model):
    """Start checklist state (shops/checklist.py): product counts and hiding; other steps are derived."""

    class Step(models.TextChoices):
        """Order matters: the app shows them in this order."""

        PAYMENTS = "payments", "Płatności"
        SHIPPING = "shipping", "Wysyłka"
        DOCUMENTS = "documents", "Regulamin i polityka prywatności"
        PRODUCTS = "products", "Własne produkty"
        SAMPLE_PRODUCTS = "sample_products", "Bez przykładowych produktów"
        NOTIFICATIONS = "notifications", "Powiadomienia na telefonie"
        TEST_ORDER = "test_order", "Próbne zamówienie"

    shop = models.OneToOneField(Shop, on_delete=models.CASCADE, related_name="checklist")
    # The owner's own products and the samples from setup; None until counted.
    products = models.PositiveIntegerField(null=True, blank=True)
    sample_products = models.PositiveIntegerField(null=True, blank=True)
    # Last successful count, and last attempt (also failed).
    counted_at = models.DateTimeField(null=True, blank=True)
    attempted_at = models.DateTimeField(null=True, blank=True)
    requested_at = models.DateTimeField(null=True, blank=True)
    hidden_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.shop}: {self.products} + {self.sample_products}"
