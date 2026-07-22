from django.core.exceptions import ValidationError
from rest_framework import mixins, status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Transaction
from .serializers import (
    DepositRequestSerializer,
    TransactionSerializer,
    TransferRequestSerializer,
    WithdrawRequestSerializer,
)
from .services import TransferService


class TransactionViewSet(mixins.RetrieveModelMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    """Transactions are an append-only ledger - read-only via the API.
    They are only ever created through TransferService."""

    queryset = Transaction.objects.all()
    serializer_class = TransactionSerializer


def _respond(txn):
    body = TransactionSerializer(txn).data
    http_status = (
        status.HTTP_201_CREATED
        if txn.status == Transaction.Status.COMPLETED
        else status.HTTP_422_UNPROCESSABLE_ENTITY
    )
    return Response(body, status=http_status)


class TransferView(APIView):
    def post(self, request):
        serializer = TransferRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            txn = TransferService.transfer(
                from_account_id=data["from_account_id"],
                to_account_id=data["to_account_id"],
                amount=data["amount"],
                idempotency_key=data["idempotency_key"],
                currency=data.get("currency"),
            )
        except ValidationError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return _respond(txn)


class DepositView(APIView):
    def post(self, request):
        serializer = DepositRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            txn = TransferService.deposit(
                account_id=data["account_id"],
                amount=data["amount"],
                idempotency_key=data["idempotency_key"],
                currency=data.get("currency"),
            )
        except ValidationError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return _respond(txn)


class WithdrawView(APIView):
    def post(self, request):
        serializer = WithdrawRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            txn = TransferService.withdraw(
                account_id=data["account_id"],
                amount=data["amount"],
                idempotency_key=data["idempotency_key"],
                currency=data.get("currency"),
            )
        except ValidationError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return _respond(txn)
