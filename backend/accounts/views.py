from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from . import services
from .serializers import (
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
                "user": UserSerializer(user).data,
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


class MeView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer
    http_method_names = ["get", "patch"]

    def get_object(self):
        return self.request.user


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
        return Response(UserSerializer(request.user).data)


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
