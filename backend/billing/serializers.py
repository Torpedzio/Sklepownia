from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from shops.choices import Country

from .models import BillingProfile, Payment, Plan, Subscription
from .services import allowed_return_url
from .validators import normalize_nip, validate_nip, validate_polish_postal_code


class PlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plan
        fields = ["code", "name", "description", "price", "currency", "vat_rate", "interval_months", "max_shops",
                  "max_magento_shops", "shop_memory_mb", "is_featured", "features"]


class BillingProfileSerializer(serializers.ModelSerializer):
    country = serializers.ChoiceField(choices=Country.choices, default=Country.PL)

    class Meta:
        model = BillingProfile
        fields = ["kind", "full_name", "company_name", "tax_id", "street", "postal_code", "city", "country"]
        extra_kwargs = {
            "full_name": {"label": "Imię i nazwisko"},
            "company_name": {"label": "Nazwa firmy", "required": False},
            # Longer than stored: "PL 526-000-12-46" is cleaned up in validate().
            "tax_id": {"label": "NIP", "required": False, "max_length": 30},
            "street": {"label": "Ulica i numer"},
            "postal_code": {"label": "Kod pocztowy"},
            "city": {"label": "Miejscowość"},
        }

    def validate(self, attrs):
        errors = {}
        company = attrs["kind"] == BillingProfile.Kind.COMPANY
        if company:
            if not attrs.get("company_name", "").strip():
                errors["company_name"] = ["Podaj nazwę firmy."]
            attrs["tax_id"] = normalize_nip(attrs.get("tax_id", ""))
            if attrs["country"] == Country.PL:
                try:
                    validate_nip(attrs["tax_id"])
                except DjangoValidationError as error:
                    errors["tax_id"] = error.messages
            elif not attrs["tax_id"]:
                errors["tax_id"] = ["Podaj numer identyfikacji podatkowej firmy."]
        else:
            # A person has no company details; anything typed there earlier is dropped.
            attrs["company_name"] = ""
            attrs["tax_id"] = ""
        if attrs["country"] == Country.PL:
            try:
                validate_polish_postal_code(attrs["postal_code"])
            except DjangoValidationError as error:
                errors["postal_code"] = error.messages
        if errors:
            raise serializers.ValidationError(errors)
        return attrs


class SavedCardSerializer(serializers.Serializer):
    brand = serializers.CharField(source="card_brand")
    tail = serializers.CharField(source="card_tail")
    expiry = serializers.CharField(source="card_expiry", help_text="MMRR")


class SubscriptionSerializer(serializers.ModelSerializer):
    plan = PlanSerializer()
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    card = serializers.SerializerMethodField()
    allows_new_shops = serializers.BooleanField(read_only=True)

    class Meta:
        model = Subscription
        fields = ["plan", "status", "status_display", "current_period_start", "current_period_end",
                  "cancel_at_period_end", "next_attempt_at", "card", "credit", "allows_new_shops"]
        extra_kwargs = {"credit": {"help_text": "Nadpłata, którą pomniejszamy kolejne płatności."}}

    def get_card(self, subscription) -> SavedCardSerializer(allow_null=True):
        return SavedCardSerializer(subscription).data if subscription.card_tail else None


class PaymentSerializer(serializers.ModelSerializer):
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    plan_name = serializers.CharField(source="plan.name", read_only=True)

    class Meta:
        model = Payment
        fields = ["id", "kind", "kind_display", "status", "status_display", "plan_name", "amount", "credit_used",
                  "currency", "gateway_title", "period_start", "period_end", "error", "created_at", "paid_at"]


class BillingOverviewSerializer(serializers.Serializer):
    subscription = SubscriptionSerializer(allow_null=True)
    profile = BillingProfileSerializer(allow_null=True)
    payments = PaymentSerializer(many=True, help_text="Ostatnie płatności, od najnowszej.")


class CheckoutSerializer(serializers.Serializer):
    plan = serializers.SlugRelatedField(slug_field="code", queryset=Plan.objects.filter(is_active=True))
    return_url = serializers.CharField(
        max_length=500, help_text="Dokąd operator płatności odeśle płacącego (aplikacja w przeglądarce albo link aplikacji).",
    )
    accept_terms = serializers.BooleanField()
    immediate_start_consent = serializers.BooleanField(
        default=False, help_text="Zgoda osoby prywatnej na rozpoczęcie usługi przed upływem 14 dni na odstąpienie.",
    )

    def validate_return_url(self, value):
        if not allowed_return_url(value):
            raise serializers.ValidationError("Nieobsługiwany adres powrotu.")
        return value

    def validate_accept_terms(self, value):
        if not value:
            raise serializers.ValidationError("Zaakceptuj regulamin, żeby przejść do płatności.")
        return value


class CheckoutResponseSerializer(serializers.Serializer):
    payment = PaymentSerializer()
    redirect_url = serializers.URLField(help_text="Strona płatności operatora.")


class PlanChangeSerializer(serializers.Serializer):
    plan = serializers.SlugRelatedField(slug_field="code", queryset=Plan.objects.filter(is_active=True))
    keep_shops = serializers.ListField(
        child=serializers.IntegerField(), required=False,
        help_text="Sklepy, które zostają aktywne, gdy nowy plan ma mniejsze limity. "
                  "Domyślnie najstarsze, które się zmieszczą.",
    )
    return_url = serializers.CharField(
        max_length=500, required=False, default="",
        help_text="Dokąd wrócić po dopłacie (jak przy pierwszej płatności).",
    )


class ShopBriefSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    status = serializers.CharField()
    platform = serializers.CharField()
    platform_display = serializers.CharField(source="get_platform_display")


class PlanChangePreviewSerializer(serializers.Serializer):
    plan = PlanSerializer()
    direction = serializers.ChoiceField(choices=["upgrade", "downgrade", ""], help_text="Na wyższy albo niższy plan.")
    surcharge = serializers.DecimalField(max_digits=10, decimal_places=2,
                                         help_text="Różnica cen za resztę opłaconego okresu.")
    credit_used = serializers.DecimalField(max_digits=10, decimal_places=2)
    amount_due = serializers.DecimalField(max_digits=10, decimal_places=2, help_text="Do zapłaty teraz.")
    waived = serializers.BooleanField(help_text="Dopłata poniżej 5 zł: plan zmienia się bez niej.")
    credit_added = serializers.DecimalField(max_digits=10, decimal_places=2,
                                            help_text="Niewykorzystana kwota, która trafi na saldo.")
    credit_after = serializers.DecimalField(max_digits=10, decimal_places=2)
    keep = ShopBriefSerializer(many=True)
    suspend = ShopBriefSerializer(many=True, help_text="Sklepy, które zostaną zawieszone.")
    resume = ShopBriefSerializer(many=True, help_text="Zawieszone sklepy, które wrócą.")
    blocked = serializers.CharField(help_text="Dlaczego zmiana nie jest możliwa; puste, gdy jest.")


class PlanChangeResultSerializer(serializers.Serializer):
    change = PlanChangePreviewSerializer()
    payment = PaymentSerializer(allow_null=True, help_text="Dopłata do zapłacenia, zanim plan się zmieni.")
    redirect_url = serializers.URLField(allow_null=True)
