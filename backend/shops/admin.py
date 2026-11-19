from django.contrib import admin
from django.template.defaultfilters import filesizeformat

from .models import (
    ProvisioningJob, ProvisioningStep, Server, Shop, ShopBackup, ShopConfig, ShopOperation, ShopTemplate,
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


@admin.register(Shop)
class ShopAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "owner", "platform", "status", "server", "created_at"]
    list_filter = ["platform", "status", "server"]
    search_fields = ["name", "slug", "owner__email"]
    raw_id_fields = ["owner"]
    inlines = [ShopConfigInline]
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
