from django.contrib import admin

from .models import PushDevice, PushPreferences


@admin.register(PushDevice)
class PushDeviceAdmin(admin.ModelAdmin):
    list_display = ["user", "platform", "name", "created_at", "last_seen_at"]
    list_filter = ["platform"]
    search_fields = ["user__email", "name"]
    readonly_fields = ["token", "created_at", "last_seen_at"]


@admin.register(PushPreferences)
class PushPreferencesAdmin(admin.ModelAdmin):
    list_display = ["user", "new_orders", "shops", "billing"]
    search_fields = ["user__email"]
