from django.contrib import admin
from django.urls import include, path
from drf_spectacular.utils import extend_schema, inline_serializer
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework import serializers
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from accounts.views import avatar_file
from shops.unavailable import shop_unavailable


@extend_schema(responses=inline_serializer("Health", {"status": serializers.CharField()}))
@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def health(request):
    return Response({"status": "OK"})


urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/health/', health),
    path('api/auth/', include('accounts.urls')),
    path('api/', include('shops.urls')),
    path('api/', include('support.urls')),
    path('api/', include('billing.urls')),
    path('api/', include('push.urls')),
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='docs'),
    path('docs/', include('handbook.urls')),
    path('media/avatars/<str:name>', avatar_file, name='avatar-file'),
    # The shops' proxy sends here addresses no shop answers (infra/shops/traefik/fallback.yml).
    path('shop-unavailable/', shop_unavailable, name='shop-unavailable'),
]
