import uuid

from django.db import models


class Account(models.Model):
    class Currency(models.TextChoices):
        NGN = "NGN", "Nigerian Naira"
        USD = "USD", "US Dollar"
        EUR = "EUR", "Euro"
        GBP = "GBP", "British Pound"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        FROZEN = "frozen", "Frozen"
        CLOSED = "closed", "Closed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner_id = models.CharField(max_length=64, db_index=True)
    owner_name = models.CharField(max_length=255)
    currency = models.CharField(max_length=3, choices=Currency.choices, default=Currency.NGN)
    balance = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "accounts"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(check=models.Q(balance__gte=0), name="account_balance_non_negative"),
        ]

    def __str__(self):
        return f"{self.owner_name} ({self.id}) - {self.balance} {self.currency}"
