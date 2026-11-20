from django.contrib import admin
from django.template.defaultfilters import filesizeformat

from .models import (
    ProvisioningJob, ProvisioningStep, Server, Shop, ShopBackup, ShopConfig, ShopEvent, ShopInvitation,
    ShopMember, ShopOperation, ShopTemplate,
)


@admin.register(Server)
class ServerAdmin(admin.ModelAdmin):
    list_display = ["name", "hostname", "public_ip", "is_active", "max_shops", "created_at"]


@admin.register(ShopTemplate)
class ShopTemplateAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "platform", "theme", "is_active", "sort_order"]
    list_filter = ["platform"]
    list_editable = ["is_active", "sort_order"]


class ShopConfigInline(admin.StackedInline):
    model = ShopConfig
    can_delete = False


class ShopMemberInline(admin.TabularInline):
    model = ShopMember
    extra = 0
    raw_id_fields = ["user"]
    verbose_name = "osoba z obsługi"
    verbose_name_plural = "obsługa sklepu"


class ShopInvitationInline(admin.TabularInline):
    model = ShopInvitation
    extra = 0
    fields = ["email", "invited_by", "created_at", "expires_at"]
    readonly_fields = fields
    verbose_name = "zaproszenie"
    verbose_name_plural = "zaproszenia do obsługi"

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Shop)
class ShopAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "owner", "platform", "status", "server", "created_at"]
    list_filter = ["platform", "status", "server"]
    search_fields = ["name", "slug", "owner__email"]
    raw_id_fields = ["owner"]
    inlines = [ShopConfigInline, ShopMemberInline, ShopInvitationInline]
    # Status changes go through the state machine in services, not the admin form.
    readonly_fields = ["status", "platform", "admin_path"]


class ProvisioningStepInline(admin.TabularInline):
    model = ProvisioningStep
    extra = 0
    can_delete = False
    readonly_fields = ["order", "key", "label", "status", "error", "started_at", "finished_at"]


@admin.register(ProvisioningJob)
class ProvisioningJobAdmin(admin.ModelAdmin):
    list_display = ["id", "shop", "status", "created_at", "finished_at"]
    list_filter = ["status"]
    inlines = [ProvisioningStepInline]
    readonly_fields = ["shop", "status", "error", "created_at", "started_at", "finished_at"]


@admin.register(ShopOperation)
class ShopOperationAdmin(admin.ModelAdmin):
    list_display = ["id", "shop", "kind", "status", "requested_by", "created_at", "finished_at"]
    list_filter = ["kind", "status"]
    search_fields = ["shop__name", "shop__slug"]
    # Payment keys in transit to the shop: nobody reads them here.
    exclude = ["secrets"]
    readonly_fields = [
        "shop", "kind", "status", "changes", "result", "error", "requested_by", "created_at", "started_at", "finished_at",
    ]


@admin.register(ShopEvent)
class ShopEventAdmin(admin.ModelAdmin):
    """Read-only: the history is what happened."""

    list_display = ["created_at", "shop", "kind", "actor", "operation"]
    list_filter = ["kind"]
    search_fields = ["shop__name", "shop__slug", "actor__email"]
    readonly_fields = ["shop", "kind", "actor", "operation", "data", "created_at"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(ShopBackup)
class ShopBackupAdmin(admin.ModelAdmin):
    """Read-only index; restoring is done by the worker or manage.py restore_shop."""

    list_display = ["id", "shop", "kind", "status", "created_at", "size_display"]
    list_filter = ["status", "kind", "shop__platform"]
    search_fields = ["shop__name", "shop__slug", "snapshot_id"]
    readonly_fields = ["shop", "kind", "status", "snapshot_id", "size", "error", "created_at"]

    @admin.display(description="Rozmiar", ordering="size")
    def size_display(self, backup):
        return filesizeformat(backup.size) if backup.size is not None else "—"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        # The snapshot would stay in the repository and maintain() would adopt it again.
        return False
