from django.contrib import admin

from .models import BillingProfile, Payment, Plan, Subscription


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ["name", "code", "price", "currency", "interval_months", "max_shops", "shop_memory_mb",
                    "is_featured", "is_active", "sort_order"]
    list_editable = ["is_featured", "is_active", "sort_order"]


@admin.register(BillingProfile)
class BillingProfileAdmin(admin.ModelAdmin):
    list_display = ["user", "kind", "payer_name", "tax_id", "city", "updated_at"]
    list_filter = ["kind"]
    search_fields = ["user__email", "full_name", "company_name", "tax_id"]


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0
    can_delete = False
    fields = ["created_at", "kind", "status", "amount", "gateway_title", "period_start", "period_end", "error"]
    readonly_fields = fields


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ["user", "plan", "status", "current_period_end", "cancel_at_period_end", "card_tail"]
    list_filter = ["status", "plan"]
    search_fields = ["user__email"]
    raw_id_fields = ["user"]
    # The card token is a secret: never shown or edited by hand.
    exclude = ["card_token"]
    readonly_fields = ["card_brand", "card_tail", "card_expiry", "terms_accepted_at", "immediate_start_consent_at"]
    inlines = [PaymentInline]


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ["id", "user", "plan", "kind", "status", "amount", "gateway", "gateway_title", "created_at"]
    list_filter = ["status", "kind", "gateway"]
    search_fields = ["user__email", "gateway_id", "gateway_title"]
    readonly_fields = [field.name for field in Payment._meta.fields]
