from django.contrib import admin

from .models import Account


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ["id", "owner_name", "owner_id", "balance", "currency", "status", "created_at"]
    list_filter = ["status", "currency"]
    search_fields = ["owner_name", "owner_id", "id"]
    readonly_fields = ["id", "balance", "created_at", "updated_at"]
