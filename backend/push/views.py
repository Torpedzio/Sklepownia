from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from accounts.permissions import IsEmailVerified

from . import services
from .serializers import ForgetDeviceSerializer, PushDeviceSerializer, PushPreferencesSerializer


@extend_schema(request=PushDeviceSerializer, responses={200: PushDeviceSerializer, 201: PushDeviceSerializer})
@api_view(["POST"])
@permission_classes([IsEmailVerified])
def register_device(request):
    """The app sends its push token after the user agrees to notifications, and again on each start."""
    serializer = PushDeviceSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    device, created = services.register_device(request.user, **serializer.validated_data)
    return Response(PushDeviceSerializer(device).data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


@extend_schema(request=ForgetDeviceSerializer, responses={204: None})
@api_view(["POST"])
@permission_classes([IsEmailVerified])
def forget_device(request):
    """On signing out: the phone stops getting the user's notifications."""
    serializer = ForgetDeviceSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    services.forget_device(request.user, serializer.validated_data["token"])
    return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(methods=["GET"], responses=PushPreferencesSerializer)
@extend_schema(methods=["PATCH"], request=PushPreferencesSerializer, responses=PushPreferencesSerializer)
@api_view(["GET", "PATCH"])
@permission_classes([IsEmailVerified])
def preferences(request):
    """What the notifications are about, and the phones that get them."""
    chosen = services.preferences(request.user)
    if request.method == "PATCH":
        serializer = PushPreferencesSerializer(chosen, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
    return Response(PushPreferencesSerializer(chosen).data)
