from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ["email"]
    list_display = [
        "email", "first_name", "last_name", "purpose", "is_email_verified", "is_staff", "date_joined", "deleted_at",
    ]
    list_filter = [
        "purpose", "is_email_verified", "is_staff", "is_superuser", "is_active", ("deleted_at", admin.EmptyFieldListFilter),
    ]
    readonly_fields = ["deleted_at"]
    search_fields = ["email", "first_name", "last_name"]
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Dane osobowe", {"fields": ("first_name", "last_name", "purpose")}),
        ("Status", {"fields": (
            "is_active", "is_email_verified", "is_staff", "is_superuser", "groups", "user_permissions",
        )}),
        ("Daty", {"fields": ("last_login", "date_joined", "deleted_at")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("email", "password1", "password2")}),
    )
