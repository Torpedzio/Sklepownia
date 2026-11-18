from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .choices import MAX_CATEGORY_COUNT, MIN_CATEGORY_COUNT, Country, Currency, Industry, Language
from .models import ProvisioningJob, ProvisioningStep, Shop, ShopConfig, ShopOperation, ShopOrder, ShopTemplate
from .platforms import Platform, platform_info
from .shop_settings import SECTIONS, describe
from .slugs import normalize_slug, slug_error

DEFAULT_CATEGORY_COUNT = 5


class ShopTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShopTemplate
        fields = ["slug", "platform", "name", "description", "preview_image_url"]


class ShopCreateSerializer(serializers.Serializer):
    name = serializers.CharField(min_length=2, max_length=100)
    slug = serializers.CharField(max_length=30)
    platform = serializers.ChoiceField(
        choices=Platform.choices, required=False, help_text="Domyślnie platforma wybranego motywu.",
    )
    industry = serializers.ChoiceField(choices=Industry.choices)
    template = serializers.SlugRelatedField(slug_field="slug", queryset=ShopTemplate.objects.filter(is_active=True))
    category_count = serializers.IntegerField(
        min_value=MIN_CATEGORY_COUNT, max_value=MAX_CATEGORY_COUNT, default=DEFAULT_CATEGORY_COUNT,
    )
    language = serializers.ChoiceField(choices=Language.choices, default=Language.PL)
    currency = serializers.ChoiceField(choices=Currency.choices, default=Currency.PLN)
    country = serializers.ChoiceField(choices=Country.choices, default=Country.PL)
    contact_email = serializers.EmailField(required=False, help_text="Domyślnie e-mail właściciela konta.")
    description = serializers.CharField(required=False, allow_blank=True, max_length=500, default="")
    include_sample_products = serializers.BooleanField(default=True)

    def validate_slug(self, value):
        value = normalize_slug(value)
        error = slug_error(value)
        if error:
            raise serializers.ValidationError(error)
        return value

    def validate(self, attrs):
        attrs.setdefault("contact_email", self.context["request"].user.email)
        platform = attrs.setdefault("platform", attrs["template"].platform)
        if attrs["template"].platform != platform:
            raise serializers.ValidationError({"template": ["Ten motyw jest dla innej platformy. Wybierz motyw ponownie."]})
        return attrs


class ShopSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    platform_display = serializers.CharField(source="get_platform_display", read_only=True)

    class Meta:
        model = Shop
        fields = [
            "id", "name", "slug", "url", "status", "status_display", "platform", "platform_display",
            "is_test", "created_at",
        ]


class ShopConfigSerializer(serializers.ModelSerializer):
    template = ShopTemplateSerializer()

    class Meta:
        model = ShopConfig
        fields = [
            "industry", "template", "category_count", "language", "currency", "country",
            "contact_email", "description", "include_sample_products",
        ]


class ProvisioningStepSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProvisioningStep
        fields = ["key", "label", "status", "error", "started_at", "finished_at"]


class ProvisioningJobSerializer(serializers.ModelSerializer):
    steps = ProvisioningStepSerializer(many=True)
    completed_steps = serializers.SerializerMethodField()
    total_steps = serializers.SerializerMethodField()

    class Meta:
        model = ProvisioningJob
        fields = [
            "id", "status", "error", "created_at", "started_at", "finished_at",
            "completed_steps", "total_steps", "steps",
        ]

    def get_completed_steps(self, job) -> int:
        return sum(step.status == ProvisioningStep.Status.DONE for step in job.steps.all())

    def get_total_steps(self, job) -> int:
        return len(job.steps.all())


class ShopDetailSerializer(ShopSerializer):
    config = ShopConfigSerializer()
    provisioning = serializers.SerializerMethodField()
    panel_name = serializers.SerializerMethodField(help_text="Jak właściciel zna panel sklepu, np. „panel WordPressa”.")
    setup_time = serializers.SerializerMethodField(help_text="Ile trwa zakładanie sklepu, np. „około dwóch minut”.")

    class Meta(ShopSerializer.Meta):
        fields = [*ShopSerializer.Meta.fields, "panel_name", "setup_time", "config", "provisioning"]

    def get_panel_name(self, shop) -> str:
        return platform_info(shop.platform).panel_name

    def get_setup_time(self, shop) -> str:
        return platform_info(shop.platform).setup_time

    @extend_schema_field(ProvisioningJobSerializer(allow_null=True))
    def get_provisioning(self, shop):
        job = shop.provisioning_jobs.prefetch_related("steps").first()
        return ProvisioningJobSerializer(job).data if job else None


class ShopAdminAccessSerializer(serializers.Serializer):
    """Where the admin panel is. The login and password are only ever sent by e-mail, to `sent_to`."""

    admin_url = serializers.URLField()
    sent_to = serializers.EmailField(help_text="Adres, na który wysyłamy dane logowania (e-mail konta).")


class SlugCheckSerializer(serializers.Serializer):
    slug = serializers.CharField()
    available = serializers.BooleanField()
    reason = serializers.CharField(allow_null=True)


class ChoiceSerializer(serializers.Serializer):
    value = serializers.CharField()
    label = serializers.CharField()


class CategoryCountRangeSerializer(serializers.Serializer):
    min = serializers.IntegerField()
    max = serializers.IntegerField()
    default = serializers.IntegerField()


class PlatformOptionSerializer(serializers.Serializer):
    value = serializers.CharField()
    label = serializers.CharField()
    description = serializers.CharField()
    available = serializers.BooleanField(help_text="Czy plan pozwala teraz założyć sklep na tym systemie.")
    note = serializers.CharField(help_text="Ograniczenie planu, np. w których planach jest Magento; puste bez niego.")


class FormOptionsSerializer(serializers.Serializer):
    platforms = PlatformOptionSerializer(many=True)
    industries = ChoiceSerializer(many=True)
    languages = ChoiceSerializer(many=True)
    currencies = ChoiceSerializer(many=True)
    countries = ChoiceSerializer(many=True)
    templates = ShopTemplateSerializer(many=True)
    category_count = CategoryCountRangeSerializer()
    base_domain = serializers.CharField()


class ShopOperationSerializer(serializers.ModelSerializer):
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    changed_fields = serializers.SerializerMethodField(help_text="Etykiety zmienionych pól, np. „Waluta”.")

    class Meta:
        model = ShopOperation
        fields = [
            "id", "kind", "kind_display", "status", "status_display", "changes", "changed_fields",
            "result", "error", "created_at", "started_at", "finished_at",
        ]

    def get_changed_fields(self, operation) -> list[str]:
        return describe(operation.changes)


class ShopSettingsValuesSerializer(serializers.Serializer):
    """The full settings, every section and field present."""

    def get_fields(self):
        return {name: section() for name, section in SECTIONS.items()}


class ThemeOptionSerializer(serializers.Serializer):
    value = serializers.CharField()
    label = serializers.CharField()


class ShopSettingsOptionsSerializer(serializers.Serializer):
    languages = ChoiceSerializer(many=True)
    currencies = ChoiceSerializer(many=True)
    countries = ChoiceSerializer(many=True)
    timezones = ChoiceSerializer(many=True)
    themes = ThemeOptionSerializer(many=True)
    vat_rates = serializers.DictField(
        child=serializers.ListField(child=serializers.CharField()),
        help_text="Typowe stawki VAT według kraju, stawka podstawowa pierwsza.",
    )


class ShopSettingsSerializer(serializers.Serializer):
    values = ShopSettingsValuesSerializer(help_text="Ostatnio odczytane albo zapisane ustawienia.")
    sections = serializers.ListField(
        child=serializers.CharField(),
        help_text="Sekcje, które aplikacja może zmieniać na platformie sklepu; pozostałe ustawia się w panelu.",
    )
    panel_name = serializers.CharField(help_text="Jak właściciel zna panel sklepu, np. „panel WordPressa”.")
    synced_at = serializers.DateTimeField(allow_null=True, help_text="Kiedy ustawienia odczytano ze sklepu.")
    operation = ShopOperationSerializer(allow_null=True, help_text="Ostatnia operacja na sklepie.")
    busy = serializers.BooleanField(help_text="Sklep wykonuje operację; kolejną można zlecić po jej zakończeniu.")
    options = ShopSettingsOptionsSerializer()


class SalesPeriodSerializer(serializers.Serializer):
    orders = serializers.IntegerField()
    revenue = serializers.DecimalField(max_digits=14, decimal_places=2, help_text="Suma zamówień brutto.")
    average = serializers.DecimalField(max_digits=14, decimal_places=2, help_text="Średnia wartość zamówienia.")


class SalesDaySerializer(serializers.Serializer):
    date = serializers.DateField()
    orders = serializers.IntegerField()
    revenue = serializers.DecimalField(max_digits=14, decimal_places=2)


class SalesToHandleSerializer(serializers.Serializer):
    new = serializers.IntegerField(help_text="Złożone, jeszcze nieopłacone albo niepotwierdzone.")
    processing = serializers.IntegerField(help_text="Opłacone, do wysłania.")


class ShopOrderSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = ShopOrder
        fields = ["number", "status", "status_display", "total", "currency", "items", "customer", "placed_at"]
        extra_kwargs = {"customer": {"help_text": "Imię i inicjał nazwiska."}}


class ShopSalesSerializer(serializers.Serializer):
    available = serializers.BooleanField(help_text="Sklep działa, więc jego zamówienia są odczytywane.")
    synced_at = serializers.DateTimeField(allow_null=True, help_text="Ostatni odczyt zamówień ze sklepu.")
    refreshing = serializers.BooleanField(help_text="Trwa odczyt: zapytaj ponownie za kilka sekund.")
    error = serializers.CharField(help_text="Dlaczego ostatni odczyt się nie udał; puste, gdy się udał.")
    currency = serializers.CharField(help_text="Waluta sklepu; sumy obejmują zamówienia w tej walucie.")
    today = SalesPeriodSerializer()
    last_7_days = SalesPeriodSerializer()
    last_30_days = SalesPeriodSerializer()
    previous_30_days = SalesPeriodSerializer(help_text="30 dni przed ostatnimi 30, do porównania.")
    daily = SalesDaySerializer(many=True, help_text="Ostatnie 30 dni, od najstarszego.")
    to_handle = SalesToHandleSerializer()
    recent = ShopOrderSerializer(many=True, help_text="Ostatnie zamówienia, od najnowszego.")
