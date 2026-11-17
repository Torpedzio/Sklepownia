from django.conf import settings
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from accounts.permissions import IsEmailVerified
from billing.models import Plan

from . import services
from .choices import MAX_CATEGORY_COUNT, MIN_CATEGORY_COUNT, VAT_RATES, Country, Currency, Industry, Language, Timezone
from .models import InvalidTransition, Shop, ShopCredentials, ShopOperation, ShopTemplate
from .platforms import PLATFORMS, Platform, platform_info
from .shop_settings import SettingsUpdateSerializer
from .tasks import send_admin_access_email
from .serializers import (
    DEFAULT_CATEGORY_COUNT,
    FormOptionsSerializer,
    ShopCreateSerializer,
    ShopAdminAccessSerializer,
    ShopDetailSerializer,
    ShopOperationSerializer,
    ShopSettingsSerializer,
    ShopSerializer,
    ShopTemplateSerializer,
    SlugCheckSerializer,
)
from .slugs import normalize_slug, slug_error


# Settings and operations work on a running shop, so they share the creation's permissions.
VERIFIED_ACTIONS = (
    "create", "retry", "resume", "admin_access", "send_admin_access", "shop_settings", "refresh_settings", "reset_admin_password",
    "remove_sample_products", "operations", "operation",
)
OPERATION_HISTORY_LENGTH = 20

NOT_ACTIVE = "Ustawienia można zmieniać, gdy sklep działa."
PANEL_NOT_READY = "Panel będzie dostępny, gdy sklep zostanie założony."
PLAN_REQUIRED = "Wybierz plan, żeby zakładać sklepy."
BUSY = "Sklep jeszcze zapisuje poprzednie zmiany. Spróbuj za chwilę."


def plural_shops(count):
    if count == 1:
        return "sklep"
    return "sklepy" if count % 10 in (2, 3, 4) and count % 100 not in (12, 13, 14) else "sklepów"


def _join(names):
    """["Standard", "Biznes", "Pro"] → "Standard, Biznes i Pro"."""
    return " i ".join([", ".join(names[:-1]), names[-1]]) if len(names) > 1 else "".join(names)


def _plans_with(platform, more_than=0):
    """Names of the plans that allow more than `more_than` shops on `platform`."""
    plans = Plan.objects.filter(is_active=True).order_by("sort_order", "price")
    names = [plan.name for plan in plans if (services.platform_limit(plan, platform) or 0) > more_than]
    return list(dict.fromkeys(names))


def _in_plans(platform):
    """"W planach Standard i Biznes." when only some plans have `platform`, otherwise ""."""
    with_platform = _plans_with(platform)
    if platform not in services.PLATFORM_LIMIT_FIELDS or len(with_platform) == _active_plan_names_count():
        return ""
    if not with_platform:
        return "Niedostępne w żadnym planie."
    return f"W planie {with_platform[0]}." if len(with_platform) == 1 else f"W planach {_join(with_platform)}."


def _active_plan_names_count():
    return Plan.objects.filter(is_active=True).values("name").distinct().count()


def _platform_limit_message(plan, platform, limit, used=None, *, resuming=False):
    label = Platform(platform).label
    if limit == 0:
        plans = _plans_with(platform)
        where = f"są w planie {plans[0]}" if len(plans) == 1 else f"są w planach {_join(plans)}"
        return f"Sklepy {label} {where}. Plan {plan.name} ich nie obejmuje."
    used = limit if used is None else used
    text = f"Masz już {used} {plural_shops(used)} {label}, tyle ile pozwala plan {plan.name}."
    if resuming:
        return f"{text} Usuń inny sklep {label} albo zmień plan, żeby przywrócić ten."
    bigger = _plans_with(platform, more_than=limit)
    remove = "Usuń go" if used == 1 else "Usuń któryś z nich"
    return f"{text} {remove}" + (f" albo przejdź na plan {bigger[0]}." if bigger else ".")


def _platform_options(user):
    plan = services.active_plan(user)
    options = []
    for platform, info in PLATFORMS.items():
        available, note = True, ""
        if plan is None:
            # No plan yet: say which plans have the platform.
            note = _in_plans(platform)
        else:
            usage = services.platform_usage(user, plan, platform)
            if usage and usage[0] >= usage[1]:
                available = False
                note = _platform_limit_message(plan, platform, usage[1], usage[0])
        options.append({
            "value": platform.value, "label": platform.label, "description": info.description,
            "available": available, "note": note,
        })
    return options


def _choices(choices_class):
    return [{"value": value, "label": label} for value, label in choices_class.choices]


def _settings_payload(shop):
    stored = services.get_settings(shop)
    operation = shop.operations.first()
    return {
        "values": stored.values,
        "sections": list(platform_info(shop.platform).settings_sections),
        "panel_name": platform_info(shop.platform).panel_name,
        "synced_at": stored.synced_at,
        "operation": ShopOperationSerializer(operation).data if operation else None,
        "busy": services.current_operation(shop) is not None,
        "options": {
            "languages": _choices(Language),
            "currencies": _choices(Currency),
            "countries": _choices(Country),
            "timezones": _choices(Timezone),
            "themes": [
                {"value": template.slug, "label": template.name}
                for template in ShopTemplate.objects.filter(is_active=True, platform=shop.platform)
            ],
            "vat_rates": VAT_RATES,
        },
    }


def _panel_ready(shop):
    return (
        shop.status == Shop.Status.ACTIVE
        and shop.admin_url is not None
        and ShopCredentials.objects.filter(shop=shop).exists()
    )


def _operation_conflict(exc):
    message = NOT_ACTIVE if isinstance(exc, services.ShopNotActive) else BUSY
    return Response({"detail": message}, status=status.HTTP_409_CONFLICT)


class ShopViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    queryset = Shop.objects.none()
    # Set per action (send_admin_access); without a scope ScopedRateThrottle lets everything through.
    throttle_scope = None

    def get_queryset(self):
        return (
            Shop.objects.filter(owner=self.request.user)
            .exclude(status=Shop.Status.DELETED)
            .select_related("config__template")
        )

    def get_serializer_class(self):
        if self.action == "list":
            return ShopSerializer
        if self.action == "create":
            return ShopCreateSerializer
        return ShopDetailSerializer

    def get_permissions(self):
        if self.action in VERIFIED_ACTIONS:
            return [IsAuthenticated(), IsEmailVerified()]
        return super().get_permissions()

    @extend_schema(request=ShopCreateSerializer, responses={201: ShopDetailSerializer})
    def create(self, request):
        serializer = ShopCreateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        try:
            shop = services.create_shop(request.user, **serializer.validated_data)
        except services.PlanRequired:
            return Response({"detail": PLAN_REQUIRED}, status=status.HTTP_402_PAYMENT_REQUIRED)
        except services.ShopLimitReached as limit:
            return Response(
                {"detail": f"Twój plan pozwala na {limit.limit} {plural_shops(limit.limit)}. Usuń jeden albo zmień plan."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except services.PlatformLimitReached as limit:
            return Response(
                {"platform": [_platform_limit_message(limit.plan, limit.platform, limit.limit)]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except services.SlugTaken:
            return Response({"slug": ["Ten adres jest już zajęty."]}, status=status.HTTP_400_BAD_REQUEST)
        return Response(ShopDetailSerializer(self.get_queryset().get(pk=shop.pk)).data, status=status.HTTP_201_CREATED)

    def destroy(self, request, pk=None):
        try:
            services.delete_shop(self.get_object())
        except InvalidTransition:
            return Response(
                {"detail": "Nie można usunąć sklepu w trakcie zakładania."},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(request=None, responses={202: ShopDetailSerializer})
    @action(detail=True, methods=["post"])
    def retry(self, request, pk=None):
        try:
            services.retry_shop(self.get_object())
        except services.PlanRequired:
            return Response({"detail": PLAN_REQUIRED}, status=status.HTTP_402_PAYMENT_REQUIRED)
        except InvalidTransition:
            return Response(
                {"detail": "Ponowić można tylko zakładanie, które zakończyło się błędem."},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(ShopDetailSerializer(self.get_queryset().get(pk=pk)).data, status=status.HTTP_202_ACCEPTED)

    @extend_schema(
        request=None,
        responses={
            200: ShopDetailSerializer,
            400: OpenApiResponse(description="Plan nie ma miejsca na kolejny sklep."),
            402: OpenApiResponse(description="Brak aktywnego planu."),
            409: OpenApiResponse(description="Sklep nie jest zawieszony."),
        },
    )
    @action(detail=True, methods=["post"])
    def resume(self, request, pk=None):
        """Brings back a shop suspended because it didn't fit the plan, when the plan has room now."""
        try:
            services.resume_shop(self.get_object())
        except services.PlanRequired:
            return Response({"detail": PLAN_REQUIRED}, status=status.HTTP_402_PAYMENT_REQUIRED)
        except services.ShopLimitReached as limit:
            return Response(
                {"detail": f"Twój plan pozwala na {limit.limit} {plural_shops(limit.limit)}. "
                           "Zmień plan albo usuń inny sklep, żeby przywrócić ten."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except services.PlatformLimitReached as limit:
            return Response(
                {"detail": _platform_limit_message(limit.plan, limit.platform, limit.limit, resuming=True)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except InvalidTransition:
            return Response({"detail": "Ten sklep nie jest zawieszony."}, status=status.HTTP_409_CONFLICT)
        return Response(ShopDetailSerializer(self.get_queryset().get(pk=pk)).data)

    @extend_schema(responses={200: ShopAdminAccessSerializer})
    @action(detail=True, methods=["get"], url_path="admin-access")
    def admin_access(self, request, pk=None):
        """Where the admin panel is and where its login went. Never the login itself."""
        shop = self.get_object()
        if not _panel_ready(shop):
            return Response({"detail": PANEL_NOT_READY}, status=status.HTTP_409_CONFLICT)
        return Response({"admin_url": shop.admin_url, "sent_to": shop.owner.email})

    @extend_schema(
        request=None,
        responses={202: ShopAdminAccessSerializer, 409: OpenApiResponse(description="Sklep nie jest jeszcze gotowy.")},
    )
    @action(
        detail=True, methods=["post"], url_path="send-admin-access",
        throttle_classes=[ScopedRateThrottle], throttle_scope="admin_access_email",
    )
    def send_admin_access(self, request, pk=None):
        """E-mails the shop's details and admin login to the account address again."""
        shop = self.get_object()
        if not _panel_ready(shop):
            return Response({"detail": PANEL_NOT_READY}, status=status.HTTP_409_CONFLICT)
        send_admin_access_email.delay(shop.pk, "resend")
        return Response({"admin_url": shop.admin_url, "sent_to": shop.owner.email}, status=status.HTTP_202_ACCEPTED)

    @extend_schema(
        parameters=[OpenApiParameter("slug", str, required=True)],
        responses={200: SlugCheckSerializer},
    )
    @action(detail=False, methods=["get"], url_path="check-slug")
    def check_slug(self, request):
        slug = normalize_slug(request.query_params.get("slug", ""))
        reason = slug_error(slug)
        return Response({"slug": slug, "available": reason is None, "reason": reason})

    @extend_schema(responses={200: FormOptionsSerializer})
    @action(detail=False, methods=["get"], url_path="form-options")
    def form_options(self, request):
        templates = ShopTemplate.objects.filter(is_active=True)
        return Response({
            "platforms": _platform_options(request.user),
            "industries": _choices(Industry),
            "languages": _choices(Language),
            "currencies": _choices(Currency),
            "countries": _choices(Country),
            "templates": ShopTemplateSerializer(templates, many=True).data,
            "category_count": {
                "min": MIN_CATEGORY_COUNT,
                "max": MAX_CATEGORY_COUNT,
                "default": DEFAULT_CATEGORY_COUNT,
            },
            "base_domain": settings.SHOPS_BASE_DOMAIN,
        })

    # --- settings and operations on a running shop ---

    @extend_schema(methods=["GET"], responses={200: ShopSettingsSerializer})
    @extend_schema(
        methods=["PATCH"],
        request=SettingsUpdateSerializer,
        responses={
            200: OpenApiResponse(ShopSettingsSerializer, description="Nic się nie zmieniło."),
            202: OpenApiResponse(ShopSettingsSerializer, description="Zmiana czeka na zapisanie w sklepie."),
            409: OpenApiResponse(description="Sklep nie działa albo zapisuje poprzednią zmianę."),
        },
    )
    @action(detail=True, methods=["get", "patch"], url_path="settings")
    def shop_settings(self, request, pk=None):
        shop = self.get_object()
        if request.method == "GET":
            return Response(_settings_payload(shop))
        serializer = SettingsUpdateSerializer(
            data=request.data, partial=True, context={
                "current": services.get_settings(shop).values,
                "sections": platform_info(shop.platform).settings_sections,
                "platform": shop.platform,
            },
        )
        serializer.is_valid(raise_exception=True)
        try:
            operation = services.update_settings(shop, request.user, serializer.validated_data)
        except (services.ShopNotActive, services.OperationInProgress) as exc:
            return _operation_conflict(exc)
        code = status.HTTP_200_OK if operation is None else status.HTTP_202_ACCEPTED
        return Response(_settings_payload(shop), status=code)

    @extend_schema(
        request=None,
        responses={202: ShopSettingsSerializer, 409: OpenApiResponse(description="Sklep nie działa albo jest zajęty.")},
    )
    @action(detail=True, methods=["post"], url_path="settings/refresh")
    def refresh_settings(self, request, pk=None):
        """Reads the settings from the shop again, e.g. after changes made in the admin panel."""
        shop = self.get_object()
        services.get_settings(shop)
        try:
            services.start_operation(shop, request.user, ShopOperation.Kind.SYNC_SETTINGS)
        except (services.ShopNotActive, services.OperationInProgress) as exc:
            return _operation_conflict(exc)
        return Response(_settings_payload(shop), status=status.HTTP_202_ACCEPTED)

    @extend_schema(
        request=None,
        responses={202: ShopOperationSerializer, 409: OpenApiResponse(description="Sklep nie działa albo jest zajęty.")},
    )
    @action(detail=True, methods=["post"], url_path="reset-admin-password")
    def reset_admin_password(self, request, pk=None):
        """New password for the shop administrator, e-mailed to the owner once the operation succeeds."""
        return self._start(ShopOperation.Kind.RESET_ADMIN_PASSWORD)

    @extend_schema(
        request=None,
        responses={202: ShopOperationSerializer, 409: OpenApiResponse(description="Sklep nie działa albo jest zajęty.")},
    )
    @action(detail=True, methods=["post"], url_path="remove-sample-products")
    def remove_sample_products(self, request, pk=None):
        """Deletes the sample products added when the shop was created; the result says how many."""
        return self._start(ShopOperation.Kind.REMOVE_SAMPLE_PRODUCTS)

    @extend_schema(responses={200: ShopOperationSerializer(many=True)})
    @action(detail=True, methods=["get"])
    def operations(self, request, pk=None):
        """The most recent operations on the shop, newest first."""
        shop = self.get_object()
        operations = shop.operations.all()[:OPERATION_HISTORY_LENGTH]
        return Response(ShopOperationSerializer(operations, many=True).data)

    @extend_schema(
        parameters=[OpenApiParameter("operation_id", int, OpenApiParameter.PATH)],
        responses={200: ShopOperationSerializer},
    )
    @action(detail=True, methods=["get"], url_path=r"operations/(?P<operation_id>[0-9]+)")
    def operation(self, request, pk=None, operation_id=None):
        shop = self.get_object()
        operation = shop.operations.filter(pk=operation_id).first()
        if operation is None:
            return Response({"detail": "Nie znaleziono operacji."}, status=status.HTTP_404_NOT_FOUND)
        return Response(ShopOperationSerializer(operation).data)

    def _start(self, kind):
        shop = self.get_object()
        try:
            operation = services.start_operation(shop, self.request.user, kind)
        except (services.ShopNotActive, services.OperationInProgress) as exc:
            return _operation_conflict(exc)
        return Response(ShopOperationSerializer(operation).data, status=status.HTTP_202_ACCEPTED)
