"""
Financial safety patterns, mirroring the Go Transactions/Payments API:

  - Idempotency: enforced by the unique DB constraint on
    Transaction.idempotency_key, not just an application-level check.
  - Pessimistic row-level locking: SELECT ... FOR UPDATE via
    select_for_update() while balances are read and mutated.
  - Deterministic lock ordering: accounts are always locked in a stable
    order (sorted by id) so two concurrent transfers touching the same
    pair of accounts can never deadlock against each other.
  - Atomicity: each operation is wrapped in a single DB transaction, so a
    transfer either fully succeeds (both legs) or fully fails - no partial
    state, and no separate compensating-reversal step is needed here since
    both accounts live in the same database (unlike the Go services, which
    call across two HTTP APIs and need a compensating debit reversal).
"""
import logging
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db import transaction as db_transaction
from django.utils import timezone

from accounts.models import Account

from .models import Transaction
from .tasks import send_transaction_notification

logger = logging.getLogger(__name__)


class TransferService:
    @staticmethod
    def _lock_accounts_in_order(account_ids):
        """Lock accounts in a deterministic order (by id) to prevent
        deadlocks when two transfers touch the same pair of accounts in
        opposite directions at the same time."""
        ordered_ids = sorted({str(a) for a in account_ids})
        locked = Account.objects.select_for_update().filter(id__in=ordered_ids)
        return {str(acc.id): acc for acc in locked}

    @staticmethod
    def _get_or_create_pending(*, idempotency_key, **fields):
        """Create the Transaction row first. If a concurrent request with
        the same idempotency_key already created it, the unique constraint
        raises IntegrityError and we just return the existing row - this is
        the race-safe version of a "check then create" idempotency check."""
        existing = Transaction.objects.filter(idempotency_key=idempotency_key).first()
        if existing:
            logger.info(
                "idempotent replay - returning existing transaction",
                extra={"idempotency_key": idempotency_key, "transaction_id": str(existing.id), "status": existing.status},
            )
            return existing, False
        try:
            with db_transaction.atomic():
                txn = Transaction.objects.create(idempotency_key=idempotency_key, **fields)
            return txn, True
        except IntegrityError:
            existing = Transaction.objects.get(idempotency_key=idempotency_key)
            logger.info(
                "idempotent replay - lost race, returning existing transaction",
                extra={"idempotency_key": idempotency_key, "transaction_id": str(existing.id), "status": existing.status},
            )
            return existing, False

    @classmethod
    def transfer(cls, *, from_account_id, to_account_id, amount, idempotency_key, currency=None):
        if amount is None or amount <= 0:
            raise ValidationError("Transfer amount must be positive")
        if str(from_account_id) == str(to_account_id):
            raise ValidationError("from_account_id and to_account_id must differ")

        txn, created = cls._get_or_create_pending(
            idempotency_key=idempotency_key,
            tx_type=Transaction.TxType.TRANSFER,
            from_account_id=from_account_id,
            to_account_id=to_account_id,
            amount=amount,
            currency=currency or "NGN",
            status=Transaction.Status.PENDING,
        )
        if not created:
            return txn

        with db_transaction.atomic():
            txn = Transaction.objects.select_for_update().get(pk=txn.pk)
            if txn.status != Transaction.Status.PENDING:
                return txn  # already processed by a concurrent worker

            accounts = cls._lock_accounts_in_order([from_account_id, to_account_id])
            from_acc = accounts.get(str(from_account_id))
            to_acc = accounts.get(str(to_account_id))

            if from_acc is None or to_acc is None:
                return cls._fail(txn, "Account not found")
            if from_acc.status != Account.Status.ACTIVE or to_acc.status != Account.Status.ACTIVE:
                return cls._fail(txn, "One or both accounts are not active")
            if from_acc.balance < amount:
                return cls._fail(txn, "Insufficient funds")

            from_acc.balance -= Decimal(amount)
            to_acc.balance += Decimal(amount)
            from_acc.save(update_fields=["balance", "updated_at"])
            to_acc.save(update_fields=["balance", "updated_at"])

            return cls._complete(txn)

    @classmethod
    def deposit(cls, *, account_id, amount, idempotency_key, currency=None):
        if amount is None or amount <= 0:
            raise ValidationError("Deposit amount must be positive")

        txn, created = cls._get_or_create_pending(
            idempotency_key=idempotency_key,
            tx_type=Transaction.TxType.DEPOSIT,
            to_account_id=account_id,
            amount=amount,
            currency=currency or "NGN",
            status=Transaction.Status.PENDING,
        )
        if not created:
            return txn

        with db_transaction.atomic():
            txn = Transaction.objects.select_for_update().get(pk=txn.pk)
            if txn.status != Transaction.Status.PENDING:
                return txn

            try:
                account = Account.objects.select_for_update().get(id=account_id)
            except Account.DoesNotExist:
                return cls._fail(txn, "Account not found")

            account.balance += Decimal(amount)
            account.save(update_fields=["balance", "updated_at"])
            return cls._complete(txn)

    @classmethod
    def withdraw(cls, *, account_id, amount, idempotency_key, currency=None):
        if amount is None or amount <= 0:
            raise ValidationError("Withdrawal amount must be positive")

        txn, created = cls._get_or_create_pending(
            idempotency_key=idempotency_key,
            tx_type=Transaction.TxType.WITHDRAWAL,
            from_account_id=account_id,
            amount=amount,
            currency=currency or "NGN",
            status=Transaction.Status.PENDING,
        )
        if not created:
            return txn

        with db_transaction.atomic():
            txn = Transaction.objects.select_for_update().get(pk=txn.pk)
            if txn.status != Transaction.Status.PENDING:
                return txn

            try:
                account = Account.objects.select_for_update().get(id=account_id)
            except Account.DoesNotExist:
                return cls._fail(txn, "Account not found")

            if account.balance < amount:
                return cls._fail(txn, "Insufficient funds")

            account.balance -= Decimal(amount)
            account.save(update_fields=["balance", "updated_at"])
            return cls._complete(txn)

    @staticmethod
    def _complete(txn):
        txn.status = Transaction.Status.COMPLETED
        txn.completed_at = timezone.now()
        txn.save(update_fields=["status", "completed_at"])
        logger.info(
            "transaction completed",
            extra={
                "transaction_id": str(txn.id),
                "idempotency_key": txn.idempotency_key,
                "tx_type": txn.tx_type,
                "from_account_id": str(txn.from_account_id) if txn.from_account_id else None,
                "to_account_id": str(txn.to_account_id) if txn.to_account_id else None,
                "amount": str(txn.amount),
                "currency": txn.currency,
            },
        )
        # Only dispatch once the outer atomic() block has actually
        # committed - otherwise the worker could pick up the task and read
        # the transaction row before it exists / before balances are
        # updated.
        db_transaction.on_commit(lambda: send_transaction_notification.delay(str(txn.id)))
        return txn

    @staticmethod
    def _fail(txn, reason):
        txn.status = Transaction.Status.FAILED
        txn.failure_reason = reason
        txn.save(update_fields=["status", "failure_reason"])
        logger.warning(
            "transaction failed",
            extra={
                "transaction_id": str(txn.id),
                "idempotency_key": txn.idempotency_key,
                "tx_type": txn.tx_type,
                "from_account_id": str(txn.from_account_id) if txn.from_account_id else None,
                "to_account_id": str(txn.to_account_id) if txn.to_account_id else None,
                "amount": str(txn.amount),
                "currency": txn.currency,
                "failure_reason": reason,
            },
        )
        db_transaction.on_commit(lambda: send_transaction_notification.delay(str(txn.id)))
        return txn
