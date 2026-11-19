from django.contrib import admin

from . import texts
from .models import Heartbeat, Incident, ShopHealth


class ReadOnly(admin.ModelAdmin):
    """The monitor writes these; the admin only reads them."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class OpenFilter(admin.SimpleListFilter):
    title = "stan"
    parameter_name = "open"

    def lookups(self, request, model_admin):
        return [("yes", "Trwa"), ("no", "Zakończona")]

    def queryset(self, request, queryset):
        if self.value() == "yes":
            return queryset.filter(resolved_at__isnull=True)
        if self.value() == "no":
            return queryset.filter(resolved_at__isnull=False)
        return queryset


@admin.register(Incident)
class IncidentAdmin(ReadOnly):
    list_display = ["started_at", "kind", "summary", "shop", "how_long", "alerted_at", "repaired"]
    list_filter = [OpenFilter, "kind"]
    search_fields = ["summary", "key", "shop__slug", "shop__name"]
    date_hierarchy = "started_at"

    @admin.display(description="Trwała")
    def how_long(self, incident):
        if incident.resolved_at is None:
            return "trwa"
        return texts.duration(incident.resolved_at - incident.started_at)


@admin.register(ShopHealth)
class ShopHealthAdmin(ReadOnly):
    list_display = ["shop", "works", "problem", "failures", "failing_since", "response_ms", "checked_at"]
    list_filter = ["alerted"]
    search_fields = ["shop__slug", "shop__name"]
    list_select_related = ["shop"]

    @admin.display(description="Działa", boolean=True, ordering="failures")
    def works(self, health):
        return health.failures == 0


@admin.register(Heartbeat)
class HeartbeatAdmin(ReadOnly):
    """When the monitor's round and the nightly backups last ran."""

    list_display = ["name", "beat_at"]
