import re

from rest_framework import serializers

from .models import PushDevice, PushPreferences

# What expo-notifications gives: ExponentPushToken[…] (older apps) or ExpoPushToken[…].
TOKEN = re.compile(r"^Expo(nent)?PushToken\[[A-Za-z0-9_\-:.]+\]$")


class PushDeviceSerializer(serializers.ModelSerializer):
    class Meta:
        model = PushDevice
        fields = ["token", "platform", "name"]
        extra_kwargs = {"token": {"validators": []}, "name": {"required": False}}

    def validate_token(self, value):
        if not TOKEN.match(value):
            raise serializers.ValidationError("To nie jest token powiadomień Expo.")
        return value


class ForgetDeviceSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=200)


class PushDeviceInfoSerializer(serializers.ModelSerializer):
    platform_display = serializers.CharField(source="get_platform_display", read_only=True)

    class Meta:
        model = PushDevice
        fields = ["name", "platform", "platform_display", "last_seen_at"]


class PushPreferencesSerializer(serializers.ModelSerializer):
    devices = serializers.SerializerMethodField(help_text="Telefony, na które przychodzą powiadomienia.")

    class Meta:
        model = PushPreferences
        fields = ["new_orders", "shops", "billing", "devices"]
        extra_kwargs = {
            "new_orders": {"help_text": "Nowe zamówienia w sklepach."},
            "shops": {"help_text": "Sklep gotowy albo błąd zakładania."},
            "billing": {"help_text": "Nieudana opłata za plan, koniec planu."},
        }

    def get_devices(self, preferences) -> list[dict]:
        return PushDeviceInfoSerializer(preferences.user.push_devices.all(), many=True).data
