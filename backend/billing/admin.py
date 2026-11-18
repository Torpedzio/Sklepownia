from django.contrib import admin, messages
from django.shortcuts import get_object_or_404
from django.urls import path, reverse
from django.utils.html import format_html

from . import invoices
from .models import BillingProfile, Invoice, Payment, Plan, Subscription


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ["name", "code", "price", "currency", "interval_months", "max_shops", "max_magento_shops",
                    "shop_memory_mb", "is_featured", "is_active", "sort_order"]
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


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ["__str__", "payment", "gross", "currency", "status", "ksef_status", "issue_date", "sent_at",
                    "error"]
    list_filter = ["status", "ksef_status", "issuer"]
    search_fields = ["number", "ksef_number", "external_id", "payment__user__email"]
    raw_id_fields = ["payment"]
    list_select_related = ["payment__user"]
    readonly_fields = ["document"] + [field.name for field in Invoice._meta.fields if field.name != "pdf"]
    actions = ["issue_now", "check_in_ksef"]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        # Issued invoices are kept for tax law; a wrong one is corrected with a correcting invoice.
        return False

    @admin.display(description="PDF")
    def document(self, invoice):
        if not invoice.pdf:
            return "—"
        return format_html('<a href="{}" target="_blank">{}</a>',
                           reverse("admin:billing_invoice_pdf", args=[invoice.pk]), invoice.filename)

    def get_urls(self):
        return [
            path("<int:invoice_id>/pdf/", self.admin_site.admin_view(self.pdf_view), name="billing_invoice_pdf"),
            *super().get_urls(),
        ]

    def pdf_view(self, request, invoice_id):
        from .views import _pdf_response

        return _pdf_response(get_object_or_404(Invoice.objects.exclude(pdf=b""), pk=invoice_id))

    @admin.action(description="Wystaw teraz (faktury do wystawienia)")
    def issue_now(self, request, queryset):
        for invoice in queryset.filter(status=Invoice.Status.PENDING):
            invoice = invoices.issue(invoice.pk)
            if invoice.status == Invoice.Status.ISSUED:
                self.message_user(request, f"Wystawiona: {invoice.number}.")
            else:
                self.message_user(request, f"Nie wystawiona: {invoice.error}", messages.ERROR)

    @admin.action(description="Sprawdź ponownie w KSeF")
    def check_in_ksef(self, request, queryset):
        for invoice in queryset.filter(status=Invoice.Status.ISSUED).exclude(ksef_status=Invoice.Ksef.NONE):
            invoice = invoices.check_ksef(invoice.pk)
            self.message_user(request, f"{invoice.number}: {invoice.get_ksef_status_display()}.")
