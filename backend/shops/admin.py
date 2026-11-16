from django.contrib import admin

from .models import ProvisioningJob, ProvisioningStep, Server, Shop, ShopConfig, ShopOperation, ShopTemplate


@admin.register(Server)
class ServerAdmin(admin.ModelAdmin):
    list_display = ["name", "hostname", "is_active", "max_shops", "created_at"]


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
    readonly_fields = [
        "shop", "kind", "status", "changes", "result", "error", "requested_by", "created_at", "started_at", "finished_at",
    ]
