from django.contrib import admin

from .models import Transaction


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ["id", "tx_type", "from_account", "to_account", "amount", "currency", "status", "created_at"]
    list_filter = ["tx_type", "status", "currency"]
    search_fields = ["id", "idempotency_key"]
    readonly_fields = [f.name for f in Transaction._meta.fields]

    def has_add_permission(self, request):
        # Transactions are only ever created through TransferService, never
        # hand-entered - even from the admin panel.
        return False

    def has_delete_permission(self, request, obj=None):
        return False
