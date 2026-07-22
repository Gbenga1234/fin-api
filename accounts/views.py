from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Account
from .serializers import AccountSerializer


class AccountViewSet(viewsets.ModelViewSet):
    """
    Accounts are created and read here. Balance is never written directly
    through this API - it only ever changes via transactions/services.py,
    so every balance change is auditable as a Transaction row.
    """

    queryset = Account.objects.all()
    serializer_class = AccountSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]

    def perform_update(self, serializer):
        # balance/status are read_only on the serializer; this just guards
        # against them ever being reintroduced as writable fields by mistake.
        serializer.save()

    @action(detail=True, methods=["get"])
    def balance(self, request, pk=None):
        account = self.get_object()
        return Response(
            {
                "account_id": account.id,
                "balance": account.balance,
                "currency": account.currency,
                "status": account.status,
            }
        )
