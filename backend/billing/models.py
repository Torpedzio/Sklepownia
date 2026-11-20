from django.conf import settings
from django.db import models
from django.utils import timezone

from shops.fields import EncryptedTextField


class Plan(models.Model):
    """Prices are gross (VAT included), as customers see them."""

    code = models.SlugField(unique=True)
    name = models.CharField(max_length=60)
    description = models.CharField(max_length=200, blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, help_text="Cena brutto za okres.")
    currency = models.CharField(max_length=3, default="PLN")
    vat_rate = models.DecimalField(max_digits=4, decimal_places=2, default=23)
    interval_months = models.PositiveSmallIntegerField(default=1)
    max_shops = models.PositiveSmallIntegerField()
    # Of max_shops; Magento needs about three times the memory of the others.
    max_magento_shops = models.PositiveSmallIntegerField(default=0)
    max_staff = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="Osoby z obsługi w każdym sklepie, bez właściciela; puste: bez limitu.",
    )
    shop_memory_mb = models.PositiveIntegerField(default=512)
    is_featured = models.BooleanField(default=False)
    # Benefits shown on the pricing page, one per line.
    features = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "price"]

    def __str__(self):
        return f"{self.name} ({self.price} {self.currency})"


class BillingProfile(models.Model):
    class Kind(models.TextChoices):
        INDIVIDUAL = "individual", "Osoba prywatna"
        COMPANY = "company", "Firma"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="billing_profile")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    # The person's name, or the contact person at a company.
    full_name = models.CharField(max_length=120)
    company_name = models.CharField(max_length=200, blank=True)
    # NIP for Polish companies (10 digits), another country's VAT number for foreign ones.
    tax_id = models.CharField("NIP", max_length=20, blank=True)
    street = models.CharField(max_length=200)
    postal_code = models.CharField(max_length=10)
    city = models.CharField(max_length=100)
    country = models.CharField(max_length=2, default="PL")
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.payer_name

    @property
    def payer_name(self):
        return self.company_name if self.kind == self.Kind.COMPANY else self.full_name

    def snapshot(self):
        """Copy kept with a payment, for its invoice."""
        return {
            "kind": self.kind,
            "full_name": self.full_name,
            "company_name": self.company_name,
            "tax_id": self.tax_id,
            "street": self.street,
            "postal_code": self.postal_code,
            "city": self.city,
            "country": self.country,
        }


class Subscription(models.Model):
    """One per user; re-subscribing reuses it."""

    class Status(models.TextChoices):
        INCOMPLETE = "incomplete", "Czeka na pierwszą płatność"
        ACTIVE = "active", "Aktywny"
        PAST_DUE = "past_due", "Zaległa płatność"
        CANCELED = "canceled", "Anulowany"
        EXPIRED = "expired", "Wygasł"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="subscription")
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="subscriptions")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.INCOMPLETE)
    current_period_start = models.DateTimeField(null=True, blank=True)
    current_period_end = models.DateTimeField(null=True, blank=True)
    cancel_at_period_end = models.BooleanField(default=False)
    # Saved card, charged at each renewal; the token is encrypted at rest.
    card_token = EncryptedTextField(blank=True)
    card_brand = models.CharField(max_length=20, blank=True)
    card_tail = models.CharField(max_length=4, blank=True)
    card_expiry = models.CharField(max_length=4, blank=True, help_text="MMRR")
    # Paid but unused money (e.g. after a downgrade mid-period); renewals use it first.
    credit = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    # Failed renewal charges in a row, and when to try again.
    failed_attempts = models.PositiveSmallIntegerField(default=0)
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    terms_accepted_at = models.DateTimeField(null=True, blank=True)
    # A consumer's consent to start the service before the 14-day withdrawal period ends.
    immediate_start_consent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user} – {self.plan.name} ({self.get_status_display()})"

    @property
    def allows_new_shops(self):
        return self.status == self.Status.ACTIVE and (
            self.current_period_end is None or self.current_period_end > timezone.now()
        )


class Payment(models.Model):
    class Kind(models.TextChoices):
        INITIAL = "initial", "Pierwsza płatność"
        RENEWAL = "renewal", "Odnowienie"
        UPGRADE = "upgrade", "Dopłata do wyższego planu"

    class Status(models.TextChoices):
        PENDING = "pending", "Oczekuje"
        PAID = "paid", "Opłacona"
        FAILED = "failed", "Nieudana"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="payments")
    subscription = models.ForeignKey(Subscription, on_delete=models.CASCADE, related_name="payments")
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="+")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    # What the payer pays; the plan's price minus `credit_used` from their balance.
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    credit_used = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    currency = models.CharField(max_length=3)
    # "credit" for a renewal paid entirely from the balance, without the payment gateway.
    gateway = models.CharField(max_length=20)
    # The gateway's id for the transaction, and the title it shows (Tpay: transactionId and title / tr_id).
    gateway_id = models.CharField(max_length=100, blank=True)
    gateway_title = models.CharField(max_length=100, blank=True)
    redirect_url = models.URLField(max_length=500, blank=True)
    return_url = models.CharField(max_length=500, blank=True)
    # Period paid for; set when paid.
    period_start = models.DateTimeField(null=True, blank=True)
    period_end = models.DateTimeField(null=True, blank=True)
    billing_details = models.JSONField(default=dict, blank=True)
    error = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    checked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["gateway", "gateway_id"], condition=~models.Q(gateway_id=""), name="unique_gateway_transaction",
            ),
        ]

    def __str__(self):
        return f"{self.get_kind_display()} {self.amount} {self.currency} – {self.user} ({self.get_status_display()})"

    @property
    def reference(self):
        """Our id as the gateway carries it (Tpay: hiddenDescription / tr_crc)."""
        return f"payment-{self.pk}"


class Invoice(models.Model):
    """VAT invoice for a paid payment, issued by INVOICE_ISSUER. Kept for tax law, like the payment."""

    class Status(models.TextChoices):
        PENDING = "pending", "Do wystawienia"
        ISSUED = "issued", "Wystawiona"

    class Ksef(models.TextChoices):
        NONE = "", "Poza KSeF"
        SENDING = "sending", "Wysyłana do KSeF"
        ACCEPTED = "accepted", "Przyjęta w KSeF"
        REJECTED = "rejected", "Odrzucona przez KSeF"

    payment = models.OneToOneField(Payment, on_delete=models.PROTECT, related_name="invoice")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    # The issuer's name, and the invoice's id there.
    issuer = models.CharField(max_length=30, blank=True)
    external_id = models.CharField(max_length=60, blank=True)
    number = models.CharField(max_length=60, blank=True)
    issue_date = models.DateField(null=True, blank=True)
    sale_date = models.DateField()
    seller = models.JSONField(default=dict, blank=True)
    buyer = models.JSONField(default=dict)
    item = models.CharField(max_length=250)
    # As printed: a percentage, or "np" (not subject to Polish VAT, e.g. a company from abroad).
    vat_rate = models.CharField(max_length=4)
    net = models.DecimalField(max_digits=10, decimal_places=2)
    vat = models.DecimalField(max_digits=10, decimal_places=2)
    gross = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3)
    # Stored as issued: an issued invoice never changes.
    pdf = models.BinaryField(default=b"", blank=True, editable=False)
    ksef_status = models.CharField(max_length=20, choices=Ksef.choices, default=Ksef.NONE, blank=True)
    ksef_number = models.CharField(max_length=60, blank=True)
    # Last error, for the admin: the issuer refusing it or KSeF rejecting it.
    error = models.CharField(max_length=1000, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    checked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    issued_at = models.DateTimeField(null=True, blank=True)
    # E-mailed to the payer.
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "faktura"
        verbose_name_plural = "faktury"
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["number"], condition=~models.Q(number=""), name="unique_invoice_number"),
        ]

    def __str__(self):
        return self.number or f"Faktura do płatności {self.payment_id} (do wystawienia)"

    @property
    def is_final(self):
        """Issued and, if it goes to KSeF, accepted there: only then the payer gets it."""
        return self.status == self.Status.ISSUED and self.ksef_status in (self.Ksef.NONE, self.Ksef.ACCEPTED)

    @property
    def filename(self):
        return "Faktura-" + "".join(char if char.isalnum() else "-" for char in self.number) + ".pdf"


class InvoiceSequence(models.Model):
    """Last number used in a month, for invoices the platform numbers itself."""

    period = models.CharField(max_length=7, unique=True, help_text="RRRR-MM")
    last = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.period}: {self.last}"
