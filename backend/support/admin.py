from django.contrib import admin

from .models import ContactMessage


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ["name", "email", "topic", "created_at", "is_handled"]
    list_filter = ["is_handled", "topic"]
    list_editable = ["is_handled"]
    search_fields = ["name", "email", "message"]
    readonly_fields = ["name", "email", "topic", "message", "user", "created_at"]
