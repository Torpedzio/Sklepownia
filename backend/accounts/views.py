import re

from django.core.files.storage import default_storage
from django.db import transaction
from django.http import FileResponse, Http404
from django.views.decorators.http import require_safe
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from . import services
from .avatars import InvalidAvatar, process_avatar
from .tasks import send_password_changed_email
from .serializers import (
    AuthTokensSerializer,
    AvatarUploadSerializer,
    ChangePasswordSerializer,
    EmailTokenObtainPairSerializer,
    LogoutSerializer,
    RegisterResponseSerializer,
    RegisterSerializer,
    UserSerializer,
    VerifyEmailSerializer,
)


class RegisterView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    @extend_schema(request=RegisterSerializer, responses={201: RegisterResponseSerializer})
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            user = serializer.save()
            services.send_verification_code(user)
        refresh = RefreshToken.for_user(user)
        return Response(
            {
                "user": UserSerializer(user, context={"request": request}).data,
                "tokens": {"access": str(refresh.access_token), "refresh": str(refresh)},
            },
            status=status.HTTP_201_CREATED,
        )


class LoginView(TokenObtainPairView):
    serializer_class = EmailTokenObtainPairSerializer
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"


class LogoutView(APIView):
    @extend_schema(request=LogoutSerializer, responses={205: None})
    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            RefreshToken(serializer.validated_data["refresh"]).blacklist()
        except TokenError:
            pass
        return Response(status=status.HTTP_205_RESET_CONTENT)


def _sign_out_everywhere(user):
    """Every refresh token of the user stops working, so other devices are signed out at their next refresh."""
    for token in OutstandingToken.objects.filter(user=user):
        BlacklistedToken.objects.get_or_create(token=token)


class ChangePasswordView(APIView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    @extend_schema(request=ChangePasswordSerializer, responses={200: AuthTokensSerializer})
    def post(self, request):
        """New password; other devices are signed out, this one gets fresh tokens."""
        serializer = ChangePasswordSerializer(data=request.data, context={"user": request.user})
        serializer.is_valid(raise_exception=True)
        user = request.user
        user.set_password(serializer.validated_data["new_password"])
        user.save(update_fields=["password"])
        _sign_out_everywhere(user)
        transaction.on_commit(lambda: send_password_changed_email.delay(user.pk))
        refresh = RefreshToken.for_user(user)
        return Response({"access": str(refresh.access_token), "refresh": str(refresh)})


class LogoutEverywhereView(APIView):
    @extend_schema(request=None, responses={205: None})
    def post(self, request):
        """Signs the user out on every device, this one included."""
        _sign_out_everywhere(request.user)
        return Response(status=status.HTTP_205_RESET_CONTENT)


class MeView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer
    http_method_names = ["get", "patch"]

    def get_object(self):
        return self.request.user


class AvatarView(APIView):
    """The signed-in user's profile picture: PUT a new one (multipart, field `avatar`) or DELETE it."""

    parser_classes = [MultiPartParser, FormParser]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "avatar"

    @extend_schema(request={"multipart/form-data": AvatarUploadSerializer}, responses={200: UserSerializer})
    def put(self, request):
        serializer = AvatarUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            picture = process_avatar(serializer.validated_data["avatar"])
        except InvalidAvatar as exc:
            return Response({"avatar": [str(exc)]}, status=status.HTTP_400_BAD_REQUEST)
        user = request.user
        previous = user.avatar.name
        user.avatar.save(picture.name, picture, save=False)
        user.save(update_fields=["avatar"])
        _forget_avatar_file(previous)
        return Response(UserSerializer(user, context={"request": request}).data)

    @extend_schema(request=None, responses={200: UserSerializer})
    def delete(self, request):
        user = request.user
        previous = user.avatar.name
        user.avatar = ""
        user.save(update_fields=["avatar"])
        _forget_avatar_file(previous)
        return Response(UserSerializer(user, context={"request": request}).data)


def _forget_avatar_file(name):
    if name:
        transaction.on_commit(lambda: default_storage.delete(name))


AVATAR_NAME = re.compile(r"^[0-9a-f]{32}\.webp$")


@require_safe
def avatar_file(request, name):
    """Serves a profile picture. Every upload gets a new random name, so it can be cached for good."""
    path = f"avatars/{name}"
    if not AVATAR_NAME.match(name) or not default_storage.exists(path):
        raise Http404
    response = FileResponse(default_storage.open(path), content_type="image/webp")
    response["Cache-Control"] = "public, max-age=31536000, immutable"
    return response


class VerifyEmailView(APIView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "email_verification"

    @extend_schema(request=VerifyEmailSerializer, responses={200: UserSerializer})
    def post(self, request):
        serializer = VerifyEmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            services.verify_email(request.user, serializer.validated_data["code"])
        except services.VerificationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(UserSerializer(request.user, context={"request": request}).data)


class ResendVerificationView(APIView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "email_verification"

    @extend_schema(request=None, responses={204: None})
    def post(self, request):
        if request.user.is_email_verified:
            return Response({"detail": "Adres e-mail jest już zweryfikowany."}, status=status.HTTP_400_BAD_REQUEST)
        if not services.can_resend_verification_code(request.user):
            return Response(
                {"detail": "Odczekaj chwilę przed ponownym wysłaniem kodu."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        services.send_verification_code(request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)
