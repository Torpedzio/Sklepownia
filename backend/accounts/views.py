import re

from django.core.exceptions import ValidationError as DjangoValidationError
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
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from . import services
from .avatars import InvalidAvatar, process_avatar
from .tasks import send_password_changed_email
from .serializers import (
    AuthTokensSerializer,
    AvatarUploadSerializer,
    ChangePasswordSerializer,
    DeleteAccountSerializer,
    EmailTokenObtainPairSerializer,
    LogoutSerializer,
    PasswordResetRequestSerializer,
    PasswordResetSerializer,
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
        return Response(
            {"user": UserSerializer(user, context={"request": request}).data, "tokens": _tokens(user)},
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


def _tokens(user):
    refresh = RefreshToken.for_user(user)
    return {"access": str(refresh.access_token), "refresh": str(refresh)}


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
        services.sign_out_everywhere(user)
        transaction.on_commit(lambda: send_password_changed_email.delay(user.pk))
        return Response(_tokens(user))


class DeleteAccountView(APIView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    @extend_schema(request=DeleteAccountSerializer, responses={204: None})
    def post(self, request):
        """Deletes the account, its shops and plan for good; needs the password."""
        serializer = DeleteAccountSerializer(data=request.data, context={"user": request.user})
        serializer.is_valid(raise_exception=True)
        try:
            services.delete_account(request.user)
        except services.AccountDeletionBlocked as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(status=status.HTTP_204_NO_CONTENT)


class LogoutEverywhereView(APIView):
    @extend_schema(request=None, responses={205: None})
    def post(self, request):
        """Signs the user out on every device, this one included."""
        services.sign_out_everywhere(request.user)
        return Response(status=status.HTTP_205_RESET_CONTENT)


class PasswordResetRequestView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "password_reset"

    @extend_schema(request=PasswordResetRequestSerializer, responses={204: None})
    def post(self, request):
        """E-mails a reset code; the answer is the same whether the address has an account or not."""
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.request_password_reset(serializer.validated_data["email"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class PasswordResetView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    @extend_schema(request=PasswordResetSerializer, responses={200: AuthTokensSerializer})
    def post(self, request):
        """Sets the new password with the e-mailed code and signs in; other devices are signed out."""
        serializer = PasswordResetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            user = services.reset_password(data["email"], data["code"], data["new_password"])
        except services.VerificationError as exc:
            return Response({"code": [str(exc)]}, status=status.HTTP_400_BAD_REQUEST)
        except DjangoValidationError as exc:
            return Response({"new_password": list(exc.messages)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_tokens(user))


class MeView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer
    http_method_names = ["get", "patch"]

    def get_object(self):
        return self.request.user


class AvatarView(APIView):
    """PUT a new profile picture (multipart, field `avatar`) or DELETE it."""

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
    """Every upload gets a new random name, so it can be cached forever."""
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
