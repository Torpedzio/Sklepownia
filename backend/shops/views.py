from django.conf import settings
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.permissions import IsEmailVerified

from . import services
from .choices import MAX_CATEGORY_COUNT, MIN_CATEGORY_COUNT, Country, Currency, Industry, Language
from .models import InvalidTransition, Shop, ShopCredentials, ShopTemplate
from .serializers import (
    DEFAULT_CATEGORY_COUNT,
    FormOptionsSerializer,
    ShopCreateSerializer,
    ShopAdminAccessSerializer,
    ShopDetailSerializer,
    ShopSerializer,
    ShopTemplateSerializer,
    SlugCheckSerializer,
)
from .slugs import normalize_slug, slug_error


def _choices(choices_class):
    return [{"value": value, "label": label} for value, label in choices_class.choices]


class ShopViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    queryset = Shop.objects.none()

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
        if self.action in ("create", "retry"):
            return [IsAuthenticated(), IsEmailVerified()]
        return super().get_permissions()

    @extend_schema(request=ShopCreateSerializer, responses={201: ShopDetailSerializer})
    def create(self, request):
        serializer = ShopCreateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        try:
            shop = services.create_shop(request.user, **serializer.validated_data)
        except services.ShopLimitReached:
            return Response(
                {"detail": f"Możesz mieć maksymalnie {settings.SHOPS_MAX_PER_USER} sklepy."},
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
        except InvalidTransition:
            return Response(
                {"detail": "Ponowić można tylko zakładanie, które zakończyło się błędem."},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(ShopDetailSerializer(self.get_queryset().get(pk=pk)).data, status=status.HTTP_202_ACCEPTED)

    @extend_schema(responses={200: ShopAdminAccessSerializer})
    @action(detail=True, methods=["get"], url_path="admin-access")
    def admin_access(self, request, pk=None):
        shop = self.get_object()
        credentials = ShopCredentials.objects.filter(shop=shop).first()
        if shop.status != Shop.Status.ACTIVE or credentials is None:
            return Response(
                {"detail": "Panel będzie dostępny, gdy sklep zostanie założony."},
                status=status.HTTP_409_CONFLICT,
            )
        return Response({
            "admin_url": shop.admin_url,
            "username": credentials.wp_admin_username,
            "password": credentials.wp_admin_password,
        })

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
