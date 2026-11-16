from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import User


class UserSerializer(serializers.ModelSerializer):
    shop_limit = serializers.SerializerMethodField(help_text="Ile sklepów pozwala plan; 0 bez aktywnego planu.")
    plan = serializers.SerializerMethodField(help_text="Nazwa aktywnego planu albo null.")
    can_create_shops = serializers.SerializerMethodField()
    avatar_url = serializers.SerializerMethodField(help_text="Adres zdjęcia profilowego albo null.")

    class Meta:
        model = User
        fields = ["id", "email", "first_name", "last_name", "is_email_verified", "date_joined", "shop_limit",
                  "plan", "can_create_shops", "avatar_url"]
        read_only_fields = ["id", "email", "is_email_verified", "date_joined"]

    def _plan(self, user):
        from shops.services import active_plan

        if not hasattr(self, "_plan_cache"):
            self._plan_cache = {}
        if user.pk not in self._plan_cache:
            self._plan_cache[user.pk] = active_plan(user)
        return self._plan_cache[user.pk]

    def get_shop_limit(self, user) -> int:
        plan = self._plan(user)
        return plan.max_shops if plan else 0

    def get_plan(self, user) -> str | None:
        plan = self._plan(user)
        return plan.name if plan else None

    def get_avatar_url(self, user) -> str | None:
        if not user.avatar:
            return None
        request = self.context.get("request")
        return request.build_absolute_uri(user.avatar.url) if request else user.avatar.url

    def get_can_create_shops(self, user) -> bool:
        from shops.services import paid_shop_count

        plan = self._plan(user)
        return bool(plan) and user.is_email_verified and paid_shop_count(user) < plan.max_shops


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, style={"input_type": "password"})

    class Meta:
        model = User
        fields = ["email", "password", "first_name", "last_name"]

    def validate_email(self, value):
        value = value.lower()
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Konto z tym adresem e-mail już istnieje.")
        return value

    def validate(self, attrs):
        candidate = User(**{k: v for k, v in attrs.items() if k != "password"})
        try:
            password_validation.validate_password(attrs["password"], candidate)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": list(exc.messages)})
        return attrs

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class VerifyEmailSerializer(serializers.Serializer):
    code = serializers.RegexField(r"^\d{6}$", error_messages={"invalid": "Kod musi składać się z 6 cyfr."})


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True, style={"input_type": "password"})
    new_password = serializers.CharField(write_only=True, style={"input_type": "password"})

    def validate_current_password(self, value):
        if not self.context["user"].check_password(value):
            raise serializers.ValidationError("Obecne hasło jest nieprawidłowe.")
        return value

    def validate(self, attrs):
        user = self.context["user"]
        if attrs["new_password"] == attrs["current_password"]:
            raise serializers.ValidationError({"new_password": ["Nowe hasło musi różnić się od obecnego."]})
        try:
            password_validation.validate_password(attrs["new_password"], user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"new_password": list(exc.messages)})
        return attrs


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class AuthTokensSerializer(serializers.Serializer):
    access = serializers.CharField()
    refresh = serializers.CharField()


class RegisterResponseSerializer(serializers.Serializer):
    user = UserSerializer()
    tokens = AuthTokensSerializer()


class EmailTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        attrs[self.username_field] = attrs[self.username_field].lower()
        return super().validate(attrs)


class AvatarUploadSerializer(serializers.Serializer):
    avatar = serializers.FileField(help_text="JPG, PNG, WebP albo GIF do 10 MB; zapisany jako kwadrat 512×512.")
