from decimal import Decimal

from rest_framework import serializers

from .models import Transaction


class TransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = [
            "id",
            "idempotency_key",
            "tx_type",
            "from_account",
            "to_account",
            "amount",
            "currency",
            "status",
            "failure_reason",
            "created_at",
            "completed_at",
        ]
        read_only_fields = fields


class TransferRequestSerializer(serializers.Serializer):
    idempotency_key = serializers.CharField(max_length=128)
    from_account_id = serializers.UUIDField()
    to_account_id = serializers.UUIDField()
    amount = serializers.DecimalField(max_digits=20, decimal_places=2, min_value=Decimal("0.01"))
    currency = serializers.CharField(max_length=3, required=False)


class DepositRequestSerializer(serializers.Serializer):
    idempotency_key = serializers.CharField(max_length=128)
    account_id = serializers.UUIDField()
    amount = serializers.DecimalField(max_digits=20, decimal_places=2, min_value=Decimal("0.01"))
    currency = serializers.CharField(max_length=3, required=False)


class WithdrawRequestSerializer(DepositRequestSerializer):
    pass
