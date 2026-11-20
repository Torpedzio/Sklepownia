from django.conf import settings
from django.db.models import Count, Q
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from accounts.permissions import IsEmailVerified
from billing.models import Plan

from . import backups, checklist, documents, history, orders, products, sales, services, shop_settings, team
from .choices import MAX_CATEGORY_COUNT, MIN_CATEGORY_COUNT, VAT_RATES, Country, Currency, Industry, Language, Timezone
from .models import (
    InvalidTransition, Shop, ShopCredentials, ShopEvent, ShopInvitation, ShopOperation, ShopOrder, ShopOrderNote,
    ShopTemplate,
)
from .platforms import PLATFORMS, Platform, platform_info
from .remote import NotInShop, ShopApiError
from .shop_settings import DocumentsSection, SellerRegister, SettingsUpdateSerializer
from .tasks import send_admin_access_email
from .serializers import (
    DEFAULT_CATEGORY_COUNT,
    ChecklistUpdateSerializer,
    DocumentsPreviewRequestSerializer,
    DocumentsPreviewSerializer,
    FormOptionsSerializer,
    InvitationSerializer,
    InviteSerializer,
    ShopCreateSerializer,
    ShopAdminAccessSerializer,
    ShopBackupsSerializer,
    ShopChecklistSerializer,
    ShopDetailSerializer,
    ShopHistorySerializer,
    ShopOperationSerializer,
    OrderActionSerializer,
    OrderNoteCreateSerializer,
    OrderNoteSerializer,
    ProductStockSerializer,
    ShopProductDetailSerializer,
    ShopProductsSerializer,
    ShopOrderDetailSerializer,
    ShopOrdersSerializer,
    ShopSalesSerializer,
    ShopSettingsSerializer,
    ShopSerializer,
    ShopTemplateSerializer,
    SlugCheckSerializer,
    TeamInvitationSerializer,
    TeamSerializer,
)
from .slugs import normalize_slug, slug_error


# Settings and operations work on a running shop, so they share the creation's permissions.
VERIFIED_ACTIONS = (
    "create", "retry", "resume", "admin_access", "send_admin_access", "shop_settings", "refresh_settings", "reset_admin_password",
    "remove_sample_products", "operations", "operation", "shop_sales", "refresh_sales", "shop_backups",
    "restore_backup", "team", "invite", "revoke_invitation", "remove_member", "shop_history", "shop_orders",
    "shop_order", "shop_order_action", "shop_order_notes", "shop_order_note", "shop_products", "shop_product",
    "shop_product_stock",
)
# What the staff may do in a shop they serve; the rest (settings, backups, panel access, deletion…) is the owner's.
STAFF_ACTIONS = (
    "list", "retrieve", "shop_sales", "refresh_sales", "shop_orders", "shop_order", "shop_order_action",
    "shop_order_notes", "shop_order_note", "shop_products", "shop_product", "shop_product_stock", "leave",
)
OPERATION_HISTORY_LENGTH = 20
HISTORY_PAGE = 30
BACKUPS_DISABLED = "Kopie zapasowe są chwilowo wyłączone."
BACKUP_LIMIT = "Na dziś to już wszystkie kopie, które możesz zrobić sam. Kolejną zrobisz jutro, a w nocy powstanie kopia nocna."

NOT_ACTIVE = "Ustawienia można zmieniać, gdy sklep działa."
ORDER_NOT_ACTIVE = "Szczegóły zamówienia zobaczysz, gdy sklep działa."
ORDER_CHANGE_NOT_ACTIVE = "Zamówienie zmienisz, gdy sklep działa."
PRODUCTS_NOT_ACTIVE = "Produkty zobaczysz, gdy sklep działa."
PRODUCT_NOT_FOUND = "Sklep nie ma już tego produktu."
STOCK_OF_VARIANTS = "Ten produkt ma warianty: ich stany zmienisz na razie w panelu sklepu."
ORDER_ACTION_GONE = "Tego nie da się już zrobić z tym zamówieniem. Sprawdź jego obecny stan."
ORDER_NOT_FOUND = "Sklep nie ma takiego zamówienia."
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
        "payment_operators": list(platform_info(shop.platform).payment_operators),
        "server_ip": shop.server.public_ip if shop.server else None,
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
            "registers": [{"value": value, "label": label} for value, label in SellerRegister.CHOICES],
        },
    }


def _sales_payload(shop, state):
    return ShopSalesSerializer({
        "available": shop.status == Shop.Status.ACTIVE,
        "synced_at": state.synced_at,
        "refreshing": sales.is_refreshing(state),
        "error": state.error,
        **sales.overview(shop),
    }).data


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
    # Set per action; without a scope ScopedRateThrottle lets everything through.
    throttle_scope = None
    STAFF_ACTIONS = STAFF_ACTIONS

    def get_queryset(self):
        return (
            team.visible_shops(self.request.user)
            .exclude(status=Shop.Status.DELETED)
            .select_related("owner", "config__template", "health")
        )

    def get_serializer_class(self):
        if self.action == "list":
            return ShopSerializer
        if self.action == "create":
            return ShopCreateSerializer
        return ShopDetailSerializer

    def get_permissions(self):
        if self.action in VERIFIED_ACTIONS:
            permissions = [IsAuthenticated(), IsEmailVerified()]
        else:
            permissions = super().get_permissions()
        return [*permissions, team.StaffActions()]

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
            services.retry_shop(self.get_object(), request.user)
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
        """Brings back a shop suspended for not fitting the plan."""
        try:
            services.resume_shop(self.get_object(), request.user)
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
        """Never returns the login itself, only where it was sent."""
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
        """Re-sends the admin login to the account e-mail."""
        shop = self.get_object()
        if not _panel_ready(shop):
            return Response({"detail": PANEL_NOT_READY}, status=status.HTTP_409_CONFLICT)
        send_admin_access_email.delay(shop.pk, "resend")
        history.record(shop, history.Kind.ADMIN_ACCESS_SENT, request.user)
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
                "operators": platform_info(shop.platform).payment_operators,
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
        request=DocumentsPreviewRequestSerializer,
        responses={
            200: DocumentsPreviewSerializer,
            400: OpenApiResponse(description="Brakuje danych sprzedawcy albo są błędne: {documents: {pole: [...]}}."),
        },
    )
    @action(detail=True, methods=["post"], url_path="documents/preview")
    def preview_documents(self, request, pk=None):
        """Renders the documents with the given seller's details; saves nothing."""
        shop = self.get_object()
        section = DocumentsSection(data=request.data.get("documents") or {}, partial=True)
        if not section.is_valid():
            return Response({"documents": section.errors}, status=status.HTTP_400_BAD_REQUEST)
        values = shop_settings.merge(
            services.get_settings(shop).values, shop_settings.normalize({"documents": section.validated_data}),
        )
        errors = shop_settings.documents_errors(values)
        if errors:
            return Response(errors, status=status.HTTP_400_BAD_REQUEST)
        rendered = documents.render(values, shop.url)
        return Response({"documents": [
            {"key": document.key, "title": document.title, "blocks": document.blocks} for document in rendered
        ]})

    @extend_schema(
        request=None,
        responses={202: ShopSettingsSerializer, 409: OpenApiResponse(description="Sklep nie działa albo jest zajęty.")},
    )
    @action(detail=True, methods=["post"], url_path="settings/refresh")
    def refresh_settings(self, request, pk=None):
        """Re-reads the settings from the shop, e.g. after changes in its admin panel."""
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
        """E-mailed to the owner once the operation succeeds."""
        return self._start(ShopOperation.Kind.RESET_ADMIN_PASSWORD)

    @extend_schema(
        request=None,
        responses={202: ShopOperationSerializer, 409: OpenApiResponse(description="Sklep nie działa albo jest zajęty.")},
    )
    @action(detail=True, methods=["post"], url_path="remove-sample-products")
    def remove_sample_products(self, request, pk=None):
        """The operation result says how many were removed."""
        return self._start(ShopOperation.Kind.REMOVE_SAMPLE_PRODUCTS)

    @extend_schema(responses={200: ShopOperationSerializer(many=True)})
    @action(detail=True, methods=["get"])
    def operations(self, request, pk=None):
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

    @extend_schema(responses={200: ShopSalesSerializer})
    @action(detail=True, methods=["get"], url_path="sales")
    def shop_sales(self, request, pk=None):
        """Counted from the local order copy; when it's a few minutes old, a background read sets `refreshing`."""
        shop = self.get_object()
        return Response(_sales_payload(shop, sales.request_refresh(shop)))

    @extend_schema(request=None, responses={202: ShopSalesSerializer})
    @action(detail=True, methods=["post"], url_path="sales/refresh")
    def refresh_sales(self, request, pk=None):
        """No-op if the orders were read in the last half minute."""
        shop = self.get_object()
        return Response(_sales_payload(shop, sales.request_refresh(shop, force=True)), status=status.HTTP_202_ACCEPTED)

    @extend_schema(
        parameters=[
            OpenApiParameter(
                "status", str, enum=ShopOrder.Status.values, description="Tylko zamówienia w tym statusie.",
            ),
            OpenApiParameter("q", str, description="Numer zamówienia albo imię klienta."),
            OpenApiParameter("before", str, description="external_id ostatniego zamówienia z poprzedniej strony."),
        ],
        responses={200: ShopOrdersSerializer},
        operation_id="shops_orders_list",
    )
    @action(detail=True, methods=["get"], url_path="orders")
    def shop_orders(self, request, pk=None):
        """From the local copy (90 days), like the sales; a stale copy is read again in the background."""
        shop = self.get_object()
        status_filter = request.query_params.get("status", "")
        if status_filter and status_filter not in ShopOrder.Status.values:
            return Response({"status": ["Nie ma takiego statusu."]}, status=status.HTTP_400_BAD_REQUEST)
        before = None
        if request.query_params.get("before"):
            before = shop.orders.filter(external_id=request.query_params["before"]).first()
            if before is None:
                return Response({"before": ["Nie ma takiego zamówienia."]}, status=status.HTTP_400_BAD_REQUEST)
        page, has_more = orders.listing(
            shop, status=status_filter, query=request.query_params.get("q", "")[:80], before=before,
        )
        state = sales.request_refresh(shop)
        counts = dict.fromkeys(ShopOrder.Status.values, 0)
        for row in shop.orders.values("status").annotate(count=Count("id")):
            counts[row["status"]] = row["count"]
        return Response(ShopOrdersSerializer({
            "available": shop.status == Shop.Status.ACTIVE,
            "synced_at": state.synced_at,
            "refreshing": sales.is_refreshing(state),
            "error": state.error,
            "counts": counts,
            "orders": page,
            "has_more": has_more,
        }).data)

    @extend_schema(
        parameters=[OpenApiParameter("order_id", str, OpenApiParameter.PATH, description="external_id zamówienia.")],
        responses={
            200: ShopOrderDetailSerializer,
            404: OpenApiResponse(description="Sklep nie ma takiego zamówienia."),
            409: OpenApiResponse(description="Sklep nie działa."),
            503: OpenApiResponse(description="Sklep nie odpowiada albo nie przyjął klucza aplikacji."),
        },
        operation_id="shops_order_retrieve",
    )
    @action(detail=True, methods=["get"], url_path=r"orders/(?P<order_id>[0-9]{1,20})")
    def shop_order(self, request, pk=None, order_id=None):
        """Read from the shop now, with the customer's contact data and addresses, which the platform doesn't keep."""
        shop = self.get_object()
        if shop.status != Shop.Status.ACTIVE:
            return Response({"detail": ORDER_NOT_ACTIVE}, status=status.HTTP_409_CONFLICT)
        try:
            order = orders.read(shop, order_id)
        except NotInShop:
            return Response({"detail": ORDER_NOT_FOUND}, status=status.HTTP_404_NOT_FOUND)
        except ShopApiError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response(self._order_payload(shop, order))

    @extend_schema(
        parameters=[OpenApiParameter("order_id", str, OpenApiParameter.PATH, description="external_id zamówienia.")],
        request=OrderActionSerializer,
        responses={
            200: ShopOrderDetailSerializer,
            404: OpenApiResponse(description="Sklep nie ma takiego zamówienia."),
            409: OpenApiResponse(description="Sklep nie działa albo zamówienie nie pozwala już na tę zmianę."),
            503: OpenApiResponse(description="Sklep nie odpowiada albo odrzucił zmianę."),
        },
        operation_id="shops_order_action",
    )
    @action(detail=True, methods=["post"], url_path=r"orders/(?P<order_id>[0-9]{1,20})/actions")
    def shop_order_action(self, request, pk=None, order_id=None):
        """Done in the shop now; the shop e-mails the customer. Answers with the order read again afterwards."""
        shop = self.get_object()
        serializer = OrderActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if shop.status != Shop.Status.ACTIVE:
            return Response({"detail": ORDER_CHANGE_NOT_ACTIVE}, status=status.HTTP_409_CONFLICT)
        try:
            order = orders.change(shop, order_id, actor=request.user, **serializer.validated_data)
        except orders.ActionNotAllowed:
            return Response({"detail": ORDER_ACTION_GONE}, status=status.HTTP_409_CONFLICT)
        except NotInShop:
            return Response({"detail": ORDER_NOT_FOUND}, status=status.HTTP_404_NOT_FOUND)
        except ShopApiError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response(self._order_payload(shop, order))

    @extend_schema(
        parameters=[OpenApiParameter("order_id", str, OpenApiParameter.PATH, description="external_id zamówienia.")],
        request=OrderNoteCreateSerializer,
        responses={201: OrderNoteSerializer},
        operation_id="shops_order_notes_create",
    )
    @action(detail=True, methods=["post"], url_path=r"orders/(?P<order_id>[0-9]{1,20})/notes")
    def shop_order_notes(self, request, pk=None, order_id=None):
        """Kept by the platform, not the shop, so it works for every platform and even when the shop is down."""
        shop = self.get_object()
        serializer = OrderNoteCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        note = ShopOrderNote.objects.create(
            shop=shop, external_id=order_id, author=request.user, text=serializer.validated_data["text"].strip(),
        )
        return Response(OrderNoteSerializer(note, context={"request": request}).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        parameters=[
            OpenApiParameter("order_id", str, OpenApiParameter.PATH, description="external_id zamówienia."),
            OpenApiParameter("note_id", int, OpenApiParameter.PATH),
        ],
        request=None,
        responses={204: None, 403: OpenApiResponse(description="Notatka innej osoby z obsługi.")},
        operation_id="shops_order_notes_destroy",
    )
    @action(
        detail=True, methods=["delete"], url_path=r"orders/(?P<order_id>[0-9]{1,20})/notes/(?P<note_id>[0-9]+)",
    )
    def shop_order_note(self, request, pk=None, order_id=None, note_id=None):
        """The author or the shop's owner."""
        shop = self.get_object()
        note = orders.notes(shop, order_id).filter(pk=note_id).first()
        if note is None:
            return Response({"detail": "Nie ma takiej notatki."}, status=status.HTTP_404_NOT_FOUND)
        if note.author_id != request.user.pk and shop.owner_id != request.user.pk:
            return Response(
                {"detail": "Notatkę może usunąć jej autor albo właściciel sklepu."}, status=status.HTTP_403_FORBIDDEN,
            )
        note.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        parameters=[
            OpenApiParameter("q", str, description="Fragment nazwy (w Magento także SKU)."),
            OpenApiParameter("stock", str, enum=["out_of_stock"], description="Tylko produkty, których brakuje."),
            OpenApiParameter("page", int, description="Strona listy, od 1."),
        ],
        responses={
            200: ShopProductsSerializer,
            409: OpenApiResponse(description="Sklep nie działa."),
            503: OpenApiResponse(description="Sklep nie odpowiada albo nie przyjął klucza aplikacji."),
        },
        operation_id="shops_products_list",
    )
    @action(detail=True, methods=["get"], url_path="products")
    def shop_products(self, request, pk=None):
        """Read from the shop now, newest first; products live only in the shop."""
        shop = self.get_object()
        params = request.query_params
        stock_filter = params.get("stock", "")
        if stock_filter not in products.Filter.VALUES:
            return Response({"stock": ["Nie ma takiego filtra."]}, status=status.HTTP_400_BAD_REQUEST)
        page = params.get("page", "1")
        if not page.isdigit() or not 1 <= int(page) <= 1000:
            return Response({"page": ["Podaj numer strony od 1."]}, status=status.HTTP_400_BAD_REQUEST)
        if shop.status != Shop.Status.ACTIVE:
            return Response({"detail": PRODUCTS_NOT_ACTIVE}, status=status.HTTP_409_CONFLICT)
        try:
            result = products.listing(shop, query=params.get("q", "")[:80], stock_filter=stock_filter, page=int(page))
        except ShopApiError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response(ShopProductsSerializer({
            "currency": shop.config.currency, "products": result.products, "has_more": result.has_more,
        }).data)

    @extend_schema(
        parameters=[OpenApiParameter("product_id", str, OpenApiParameter.PATH, description="external_id produktu.")],
        responses={
            200: ShopProductDetailSerializer,
            404: OpenApiResponse(description="Sklep nie ma takiego produktu."),
            409: OpenApiResponse(description="Sklep nie działa."),
            503: OpenApiResponse(description="Sklep nie odpowiada albo nie przyjął klucza aplikacji."),
        },
        operation_id="shops_product_retrieve",
    )
    @action(detail=True, methods=["get"], url_path=r"products/(?P<product_id>[0-9]{1,20})")
    def shop_product(self, request, pk=None, product_id=None):
        shop = self.get_object()
        if shop.status != Shop.Status.ACTIVE:
            return Response({"detail": PRODUCTS_NOT_ACTIVE}, status=status.HTTP_409_CONFLICT)
        try:
            product = products.read(shop, product_id)
        except NotInShop:
            return Response({"detail": PRODUCT_NOT_FOUND}, status=status.HTTP_404_NOT_FOUND)
        except ShopApiError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response(self._product_payload(shop, product))

    @extend_schema(
        parameters=[OpenApiParameter("product_id", str, OpenApiParameter.PATH, description="external_id produktu.")],
        request=ProductStockSerializer,
        responses={
            200: ShopProductDetailSerializer,
            404: OpenApiResponse(description="Sklep nie ma takiego produktu."),
            409: OpenApiResponse(description="Sklep nie działa albo produkt ma warianty."),
            503: OpenApiResponse(description="Sklep nie odpowiada albo odrzucił zmianę."),
        },
        operation_id="shops_product_stock",
    )
    @action(detail=True, methods=["post"], url_path=r"products/(?P<product_id>[0-9]{1,20})/stock")
    def shop_product_stock(self, request, pk=None, product_id=None):
        """Done in the shop now; answers with the product read again afterwards."""
        shop = self.get_object()
        serializer = ProductStockSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if shop.status != Shop.Status.ACTIVE:
            return Response({"detail": PRODUCTS_NOT_ACTIVE}, status=status.HTTP_409_CONFLICT)
        try:
            product = products.set_stock(shop, product_id, serializer.validated_data["quantity"], request.user)
        except products.StockNotEditable:
            return Response({"detail": STOCK_OF_VARIANTS}, status=status.HTTP_409_CONFLICT)
        except NotInShop:
            return Response({"detail": PRODUCT_NOT_FOUND}, status=status.HTTP_404_NOT_FOUND)
        except ShopApiError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response(self._product_payload(shop, product))

    def _product_payload(self, shop, product):
        return ShopProductDetailSerializer(product, context={"currency": shop.config.currency}).data

    def _order_payload(self, shop, order):
        context = {"request": self.request, "notes": orders.notes(shop, order.external_id)}
        return ShopOrderDetailSerializer(order, context=context).data

    @extend_schema(methods=["GET"], responses={200: ShopChecklistSerializer})
    @extend_schema(methods=["PATCH"], request=ChecklistUpdateSerializer, responses={200: ShopChecklistSerializer})
    @action(detail=True, methods=["get", "patch"], url_path="checklist")
    def shop_checklist(self, request, pk=None):
        """Opening it counts the products in the background when needed; then `refreshing` is true."""
        shop = self.get_object()
        if request.method == "PATCH":
            serializer = ChecklistUpdateSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            checklist.hide(shop, serializer.validated_data["hidden"])
        return Response(ShopChecklistSerializer(checklist.overview(shop)).data)

    @extend_schema(methods=["GET"], responses={200: ShopBackupsSerializer})
    @extend_schema(
        methods=["POST"], request=None,
        responses={
            202: ShopOperationSerializer,
            409: OpenApiResponse(description="Sklep nie działa, jest zajęty albo kopie są wyłączone."),
            429: OpenApiResponse(description="Właściciel zrobił już dziś tyle kopii, ile wolno."),
        },
    )
    @action(detail=True, methods=["get", "post"], url_path="backups")
    def shop_backups(self, request, pk=None):
        """POST queues a manual backup as an operation (a few per day)."""
        shop = self.get_object()
        if request.method == "POST":
            try:
                operation = services.start_backup(shop, request.user)
            except services.BackupsDisabled:
                return Response({"detail": BACKUPS_DISABLED}, status=status.HTTP_409_CONFLICT)
            except services.BackupLimitReached:
                return Response({"detail": BACKUP_LIMIT}, status=status.HTTP_429_TOO_MANY_REQUESTS)
            except (services.ShopNotActive, services.OperationInProgress) as exc:
                return _operation_conflict(exc)
            return Response(ShopOperationSerializer(operation).data, status=status.HTTP_202_ACCEPTED)
        return Response(ShopBackupsSerializer(backups.overview(shop)).data)

    @extend_schema(
        request=None,
        parameters=[OpenApiParameter("backup_id", int, OpenApiParameter.PATH)],
        responses={
            202: ShopOperationSerializer,
            404: OpenApiResponse(description="Nie ma takiej kopii."),
            409: OpenApiResponse(description="Sklep nie działa, jest zajęty albo kopie są wyłączone."),
        },
    )
    @action(detail=True, methods=["post"], url_path=r"backups/(?P<backup_id>[0-9]+)/restore")
    def restore_backup(self, request, pk=None, backup_id=None):
        """The current state is backed up first, so this can be undone. The shop is closed for a few minutes."""
        shop = self.get_object()
        backup = backups.restorable(shop).filter(pk=backup_id).first()
        if backup is None:
            return Response({"detail": "Nie znaleziono kopii zapasowej."}, status=status.HTTP_404_NOT_FOUND)
        try:
            operation = services.start_restore(shop, request.user, backup)
        except services.BackupsDisabled:
            return Response({"detail": BACKUPS_DISABLED}, status=status.HTTP_409_CONFLICT)
        except (services.ShopNotActive, services.OperationInProgress) as exc:
            return _operation_conflict(exc)
        return Response(ShopOperationSerializer(operation).data, status=status.HTTP_202_ACCEPTED)

    @extend_schema(
        parameters=[OpenApiParameter("before", int, description="Id wpisu: starsze od niego (następna strona).")],
        responses={200: ShopHistorySerializer},
    )
    @action(detail=True, methods=["get"], url_path="history")
    def shop_history(self, request, pk=None):
        """Who did what in the shop, newest first, a page at a time."""
        shop = self.get_object()
        events = history.events(shop)
        before = request.query_params.get("before", "")
        if before.isdigit():
            cursor = shop.events.filter(pk=before).first()
            if cursor is not None:
                events = events.filter(
                    Q(created_at__lt=cursor.created_at) | Q(created_at=cursor.created_at, pk__lt=cursor.pk),
                )
        page = list(events[: HISTORY_PAGE + 1])
        return Response(ShopHistorySerializer(
            {"events": page[:HISTORY_PAGE], "has_more": len(page) > HISTORY_PAGE}, context={"shop": shop},
        ).data)

    @extend_schema(responses={200: TeamSerializer})
    @action(detail=True, methods=["get"])
    def team(self, request, pk=None):
        return Response(TeamSerializer(team.overview(self.get_object())).data)

    @extend_schema(
        request=InviteSerializer,
        responses={
            201: TeamInvitationSerializer,
            400: OpenApiResponse(description="Adres właściciela albo osoby, która już jest w zespole."),
            409: OpenApiResponse(description="Plan nie ma miejsca na kolejną osobę."),
        },
    )
    @action(
        detail=True, methods=["post"], url_path="team/invitations",
        throttle_classes=[ScopedRateThrottle], throttle_scope="shop_invitations",
    )
    def invite(self, request, pk=None):
        """Sends the invitation e-mail; inviting the same address again renews the term and sends it again."""
        shop = self.get_object()
        serializer = InviteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            invitation = team.invite(shop, serializer.validated_data["email"], request.user)
        except team.TeamError as exc:
            if exc.conflict:
                return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
            return Response({"email": [str(exc)]}, status=status.HTTP_400_BAD_REQUEST)
        return Response(TeamInvitationSerializer(invitation).data, status=status.HTTP_201_CREATED)

    @extend_schema(parameters=[OpenApiParameter("invitation_id", int, OpenApiParameter.PATH)], responses={204: None})
    @action(detail=True, methods=["delete"], url_path=r"team/invitations/(?P<invitation_id>[0-9]+)")
    def revoke_invitation(self, request, pk=None, invitation_id=None):
        """The link in the e-mail stops working."""
        if not team.revoke(self.get_object(), invitation_id, request.user):
            return Response({"detail": "Nie znaleziono zaproszenia."}, status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(parameters=[OpenApiParameter("user_id", int, OpenApiParameter.PATH)], responses={204: None})
    @action(detail=True, methods=["delete"], url_path=r"team/members/(?P<user_id>[0-9]+)")
    def remove_member(self, request, pk=None, user_id=None):
        if not team.remove_member(self.get_object(), user_id, request.user):
            return Response({"detail": "Tej osoby nie ma w zespole sklepu."}, status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        request=None,
        responses={204: None, 409: OpenApiResponse(description="Właściciel nie może opuścić swojego sklepu.")},
    )
    @action(detail=True, methods=["post"])
    def leave(self, request, pk=None):
        """For the staff: leaves the shop's team."""
        try:
            team.leave(self.get_object(), request.user)
        except team.TeamError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(status=status.HTTP_204_NO_CONTENT)

    def _start(self, kind):
        shop = self.get_object()
        try:
            operation = services.start_operation(shop, self.request.user, kind)
        except (services.ShopNotActive, services.OperationInProgress) as exc:
            return _operation_conflict(exc)
        return Response(ShopOperationSerializer(operation).data, status=status.HTTP_202_ACCEPTED)


class InvitationViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """Invitations waiting for the signed-in person (to their verified e-mail)."""

    serializer_class = InvitationSerializer

    def get_queryset(self):
        # The schema generator asks without a signed-in user.
        if getattr(self, "swagger_fake_view", False):
            return ShopInvitation.objects.none()
        return team.invitations_for(self.request.user)

    @extend_schema(
        request=None,
        responses={200: ShopSerializer, 409: OpenApiResponse(description="Zespół sklepu jest już pełny.")},
    )
    @action(detail=True, methods=["post"])
    def accept(self, request, pk=None):
        """Joins the shop's team; returns the shop as it appears on the list."""
        try:
            shop = team.accept(self.get_object(), request.user)
        except team.TeamError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(ShopSerializer(team.visible_shops(request.user).select_related("health").get(pk=shop.pk)).data)

    @extend_schema(request=None, responses={204: None})
    @action(detail=True, methods=["post"])
    def decline(self, request, pk=None):
        team.decline(self.get_object(), request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)
