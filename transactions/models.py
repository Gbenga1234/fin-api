import uuid

from django.db import models

from accounts.models import Account


class Transaction(models.Model):
    class TxType(models.TextChoices):
        DEPOSIT = "deposit", "Deposit"
        WITHDRAWAL = "withdrawal", "Withdrawal"
        TRANSFER = "transfer", "Transfer"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Enforces idempotency at the database level: a duplicate request with
    # the same key can never create a second row, even under concurrency.
    idempotency_key = models.CharField(max_length=128, unique=True, db_index=True)
    tx_type = models.CharField(max_length=12, choices=TxType.choices)
    from_account = models.ForeignKey(
        Account, null=True, blank=True, related_name="debits", on_delete=models.PROTECT
    )
    to_account = models.ForeignKey(
        Account, null=True, blank=True, related_name="credits", on_delete=models.PROTECT
    )
    amount = models.DecimalField(max_digits=20, decimal_places=2)
    currency = models.CharField(max_length=3)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    failure_reason = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "transactions"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.tx_type} {self.amount} {self.currency} [{self.status}]"
