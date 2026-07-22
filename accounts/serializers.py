from rest_framework import serializers

from .models import Account


class AccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = Account
        fields = [
            "id",
            "owner_id",
            "owner_name",
            "currency",
            "balance",
            "status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "balance", "status", "created_at", "updated_at"]
