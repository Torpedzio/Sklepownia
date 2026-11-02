from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .choices import MAX_CATEGORY_COUNT, MIN_CATEGORY_COUNT, Country, Currency, Industry, Language
from .models import ProvisioningJob, ProvisioningStep, Shop, ShopConfig, ShopTemplate
from .slugs import normalize_slug, slug_error

DEFAULT_CATEGORY_COUNT = 5


class ShopTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShopTemplate
        fields = ["slug", "name", "description", "preview_image_url"]


class ShopCreateSerializer(serializers.Serializer):
    name = serializers.CharField(min_length=2, max_length=100)
    slug = serializers.CharField(max_length=30)
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
        return attrs


class ShopSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Shop
        fields = ["id", "name", "slug", "url", "status", "status_display", "created_at"]


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

    class Meta(ShopSerializer.Meta):
        fields = [*ShopSerializer.Meta.fields, "config", "provisioning"]

    @extend_schema_field(ProvisioningJobSerializer(allow_null=True))
    def get_provisioning(self, shop):
        job = shop.provisioning_jobs.prefetch_related("steps").first()
        return ProvisioningJobSerializer(job).data if job else None


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


class FormOptionsSerializer(serializers.Serializer):
    industries = ChoiceSerializer(many=True)
    languages = ChoiceSerializer(many=True)
    currencies = ChoiceSerializer(many=True)
    countries = ChoiceSerializer(many=True)
    templates = ShopTemplateSerializer(many=True)
    category_count = CategoryCountRangeSerializer()
    base_domain = serializers.CharField()
