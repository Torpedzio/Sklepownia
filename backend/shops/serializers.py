from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .choices import MAX_CATEGORY_COUNT, MIN_CATEGORY_COUNT, Country, Currency, Industry, Language
from .models import (
    ProvisioningJob, ProvisioningStep, Shop, ShopBackup, ShopChecklist, ShopConfig, ShopInvitation, ShopMember,
    ShopOperation, ShopOrder, ShopTemplate,
)
from .platforms import Platform, platform_info
from .shop_settings import OPERATORS, SECTIONS, describe
from .slugs import normalize_slug, slug_error

DEFAULT_CATEGORY_COUNT = 5


class PersonSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField(source="get_full_name", help_text="Imię i nazwisko; puste, gdy nie podane.")
    email = serializers.EmailField()


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
    down_since = serializers.SerializerMethodField(
        help_text="Od kiedy działający sklep nie odpowiada klientom (monitor powiadomił już właściciela); null, gdy "
        "działa.",
    )

    role = serializers.ChoiceField(
        choices=ShopMember.Role.choices, read_only=True,
        help_text="Rola zalogowanej osoby w sklepie: owner (właściciel, płaci za plan) albo staff (obsługa).",
    )

    class Meta:
        model = Shop
        fields = [
            "id", "name", "slug", "url", "status", "status_display", "platform", "platform_display",
            "is_test", "created_at", "down_since", "role",
        ]

    @extend_schema_field(serializers.DateTimeField(allow_null=True))
    def get_down_since(self, shop):
        # Shops without a check yet have no health; the monitor only checks running ones.
        health = getattr(shop, "health", None)
        if shop.status != Shop.Status.ACTIVE or health is None or health.down_since is None:
            return None
        return serializers.DateTimeField().to_representation(health.down_since)


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
    owner = PersonSerializer(help_text="Właściciel sklepu (dla obsługi: kto ją zaprosił do zespołu).")

    class Meta(ShopSerializer.Meta):
        fields = [*ShopSerializer.Meta.fields, "panel_name", "setup_time", "owner", "config", "provisioning"]

    def get_panel_name(self, shop) -> str:
        return platform_info(shop.platform).panel_name

    def get_setup_time(self, shop) -> str:
        return platform_info(shop.platform).setup_time

    @extend_schema_field(ProvisioningJobSerializer(allow_null=True))
    def get_provisioning(self, shop):
        job = shop.provisioning_jobs.prefetch_related("steps").first()
        return ProvisioningJobSerializer(job).data if job else None


class ShopAdminAccessSerializer(serializers.Serializer):
    """The login and password are only ever sent by e-mail, to `sent_to`."""

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
    backup_created_at = serializers.DateTimeField(
        source="backup.created_at", read_only=True, allow_null=True,
        help_text="Chwila, z której jest kopia zapasowa zrobiona (create_backup) albo przywrócona (restore_backup).",
    )

    class Meta:
        model = ShopOperation
        fields = [
            "id", "kind", "kind_display", "status", "status_display", "changes", "changed_fields",
            "result", "backup_created_at", "error", "created_at", "started_at", "finished_at",
        ]

    def get_changed_fields(self, operation) -> list[str]:
        return describe(operation.changes)


class ShopSettingsValuesSerializer(serializers.Serializer):
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
    registers = ChoiceSerializer(many=True, help_text="Formy działalności sprzedawcy do regulaminu.")


class ShopSettingsSerializer(serializers.Serializer):
    values = ShopSettingsValuesSerializer(help_text="Ostatnio odczytane albo zapisane ustawienia.")
    sections = serializers.ListField(
        child=serializers.CharField(),
        help_text="Sekcje, które aplikacja może zmieniać na platformie sklepu; pozostałe ustawia się w panelu.",
    )
    payment_operators = serializers.ListField(
        child=serializers.ChoiceField(choices=list(OPERATORS)),
        help_text="Operatorzy płatności online, których aplikacja ustawia na platformie sklepu.",
    )
    server_ip = serializers.IPAddressField(
        allow_null=True,
        help_text="Adres IP, z którego sklep łączy się z operatorami; Przelewy24 wymaga dodania go w swoim panelu.",
    )
    panel_name = serializers.CharField(help_text="Jak właściciel zna panel sklepu, np. „panel WordPressa”.")
    synced_at = serializers.DateTimeField(allow_null=True, help_text="Kiedy ustawienia odczytano ze sklepu.")
    operation = ShopOperationSerializer(allow_null=True, help_text="Ostatnia operacja na sklepie.")
    busy = serializers.BooleanField(help_text="Sklep wykonuje operację; kolejną można zlecić po jej zakończeniu.")
    options = ShopSettingsOptionsSerializer()


class DocumentsPreviewRequestSerializer(serializers.Serializer):
    documents = serializers.DictField(
        required=False, help_text="Pola sekcji `documents` do podglądu; pozostałe jak w zapisanych ustawieniach.",
    )


class DocumentPreviewSerializer(serializers.Serializer):
    key = serializers.ChoiceField(choices=["terms", "privacy"])
    title = serializers.CharField()
    blocks = serializers.JSONField(
        help_text="Treść jako bloki: {type: heading, level, text}, {type: paragraph, text} albo "
                  "{type: list, ordered, items: [{text, items?}]}.",
    )


class DocumentsPreviewSerializer(serializers.Serializer):
    documents = DocumentPreviewSerializer(many=True)


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


class ChecklistStepSerializer(serializers.Serializer):
    key = serializers.ChoiceField(choices=ShopChecklist.Step.choices)
    done = serializers.BooleanField()


class ShopChecklistSerializer(serializers.Serializer):
    available = serializers.BooleanField(help_text="Lista jest do pokazania: sklep działa i właściciel jej nie ukrył.")
    hidden = serializers.BooleanField(help_text="Właściciel ukrył listę.")
    steps = ChecklistStepSerializer(many=True, help_text="Kroki, które dotyczą sklepu, w kolejności do pokazania.")
    products = serializers.IntegerField(
        allow_null=True, help_text="Własne produkty w sklepie, także szkice; null, dopóki ich nie policzono.",
    )
    sample_products = serializers.IntegerField(
        allow_null=True, help_text="Przykładowe produkty, które zostały w sklepie; null, dopóki ich nie policzono.",
    )
    counted_at = serializers.DateTimeField(allow_null=True, help_text="Ostatnie liczenie produktów w sklepie.")
    refreshing = serializers.BooleanField(
        help_text="Trwa liczenie produktów, odczyt zamówień albo zmiana w sklepie: zapytaj ponownie za kilka sekund.",
    )


class ChecklistUpdateSerializer(serializers.Serializer):
    hidden = serializers.BooleanField(help_text="Ukrywa listę albo pokazuje ją z powrotem.")


class ShopBackupSerializer(serializers.ModelSerializer):
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)

    class Meta:
        model = ShopBackup
        fields = ["id", "kind", "kind_display", "created_at", "size"]
        extra_kwargs = {
            "created_at": {"help_text": "Chwila, do której przywrócenie cofa sklep."},
            "size": {"help_text": "Bajty plików i bazy sklepu w kopii."},
        }


class ShopBackupsSerializer(serializers.Serializer):
    enabled = serializers.BooleanField(help_text="Kopie zapasowe działają na tym serwerze.")
    backups = ShopBackupSerializer(many=True, help_text="Kopie, do których można wrócić, od najnowszej.")
    manual_left = serializers.IntegerField(help_text="Ile kopii właściciel może jeszcze dziś zrobić sam.")
    manual_per_day = serializers.IntegerField(help_text="Ile kopii dziennie właściciel może zrobić sam.")
    keep_daily = serializers.IntegerField(help_text="Z ilu ostatnich dni zostaje najnowsza kopia.")
    keep_weekly = serializers.IntegerField(help_text="Z ilu ostatnich tygodni zostaje najnowsza kopia.")
    nightly_at = serializers.DateTimeField(help_text="Kiedy powstaną następne kopie nocne.")



class TeamMemberSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source="user.id", help_text="Id osoby (do usunięcia z zespołu).")
    name = serializers.CharField(source="user.get_full_name")
    email = serializers.EmailField(source="user.email")
    joined_at = serializers.DateTimeField(source="created_at")

    class Meta:
        model = ShopMember
        fields = ["id", "name", "email", "joined_at"]


class TeamInvitationSerializer(serializers.ModelSerializer):
    expired = serializers.BooleanField(read_only=True, help_text="Termin minął; zaproś ponownie, żeby wysłać nowe.")

    class Meta:
        model = ShopInvitation
        fields = ["id", "email", "created_at", "expires_at", "expired"]


class TeamSerializer(serializers.Serializer):
    owner = PersonSerializer()
    members = TeamMemberSerializer(many=True)
    invitations = TeamInvitationSerializer(many=True)
    limit = serializers.IntegerField(
        allow_null=True, help_text="Ile osób z obsługi pozwala plan właściciela (bez niego); null: bez limitu.",
    )
    used = serializers.IntegerField(help_text="Osoby z obsługi i ważne zaproszenia, liczone do limitu.")


class InviteSerializer(serializers.Serializer):
    email = serializers.EmailField()


class InvitationShopSerializer(serializers.ModelSerializer):
    platform_display = serializers.CharField(source="get_platform_display", read_only=True)

    class Meta:
        model = Shop
        fields = ["id", "name", "url", "platform", "platform_display"]


class InvitationSerializer(serializers.ModelSerializer):
    shop = InvitationShopSerializer()
    invited_by = PersonSerializer(allow_null=True)

    class Meta:
        model = ShopInvitation
        fields = ["id", "shop", "invited_by", "created_at", "expires_at"]
