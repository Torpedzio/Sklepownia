from django.conf import settings
from django.db import models
from django.utils import timezone

from shops.fields import EncryptedTextField


class Plan(models.Model):
    """What a subscription buys. Prices are gross (VAT included), as customers see them."""

    code = models.SlugField(unique=True)
    name = models.CharField(max_length=60)
    description = models.CharField(max_length=200, blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, help_text="Cena brutto za okres.")
    currency = models.CharField(max_length=3, default="PLN")
    vat_rate = models.DecimalField(max_digits=4, decimal_places=2, default=23)
    interval_months = models.PositiveSmallIntegerField(default=1)
    max_shops = models.PositiveSmallIntegerField()
    # Memory limit of each shop's container; more memory serves more visitors at once.
    shop_memory_mb = models.PositiveIntegerField(default=512)
    # Highlighted on the pricing page as the usual choice.
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
    """Who pays and invoice details: a person or a company."""

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
        """The details as they were when a payment was made, kept with the payment for invoices."""
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
    """A user's plan. One per user; re-subscribing reuses it."""

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
    # The owner cancelled: the plan works until the period ends, then is not renewed.
    cancel_at_period_end = models.BooleanField(default=False)
    # The saved card, charged at each renewal. The token is a secret, so it is encrypted at rest.
    card_token = EncryptedTextField(blank=True)
    card_brand = models.CharField(max_length=20, blank=True)
    card_tail = models.CharField(max_length=4, blank=True)
    card_expiry = models.CharField(max_length=4, blank=True, help_text="MMRR")
    # Paid but unused money, e.g. after moving to a cheaper plan mid-period; renewals use it first.
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
    """One charge: the first payment (the owner pays on the gateway's page) or a renewal of the saved card."""

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
    # What the payment pays for; set when it is paid.
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
