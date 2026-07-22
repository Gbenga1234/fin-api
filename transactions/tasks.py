import logging

from celery import shared_task
from django.db.models import Sum

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=10)
def send_transaction_notification(self, transaction_id):
    """
    Fire-and-forget side effect after a transaction resolves - in a real
    deployment this would call a webhook, push a notification, or send an
    email/SMS. Kept out of the synchronous request path so a slow or
    flaky downstream notifier can never block or fail a money-moving
    request; TransferService schedules this via transaction.on_commit()
    so it only fires once the DB transaction has actually committed.
    """
    from .models import Transaction

    try:
        txn = Transaction.objects.get(id=transaction_id)
    except Transaction.DoesNotExist:
        logger.warning("notification task: transaction not found", extra={"transaction_id": transaction_id})
        return

    logger.info(
        "transaction notification dispatched",
        extra={
            "transaction_id": str(txn.id),
            "tx_type": txn.tx_type,
            "status": txn.status,
            "amount": str(txn.amount),
            "currency": txn.currency,
        },
    )
    # e.g.:
    # try:
    #     requests.post(WEBHOOK_URL, json={...}, timeout=5).raise_for_status()
    # except requests.RequestException as exc:
    #     raise self.retry(exc=exc)


@shared_task
def reconcile_account_balances():
    """
    Periodic (daily, see CELERY_BEAT_SCHEDULE) reconciliation job:
    recomputes each account's balance from its completed transaction
    ledger and compares it against the stored Account.balance.

    This is read-only and deliberately does NOT auto-correct anything -
    it only logs mismatches as ERROR so they surface in monitoring/audit
    logging, the same way discrepancies would be flagged in the Go
    services' audit trail.
    """
    from accounts.models import Account
    from .models import Transaction

    mismatches = []
    for account in Account.objects.all():
        credits = (
            Transaction.objects.filter(to_account=account, status=Transaction.Status.COMPLETED).aggregate(
                total=Sum("amount")
            )["total"]
            or 0
        )
        debits = (
            Transaction.objects.filter(from_account=account, status=Transaction.Status.COMPLETED).aggregate(
                total=Sum("amount")
            )["total"]
            or 0
        )
        expected_balance = credits - debits

        if expected_balance != account.balance:
            mismatches.append(
                {
                    "account_id": str(account.id),
                    "stored_balance": str(account.balance),
                    "expected_balance": str(expected_balance),
                }
            )
            logger.error(
                "balance reconciliation mismatch",
                extra={
                    "account_id": str(account.id),
                    "stored_balance": str(account.balance),
                    "expected_balance": str(expected_balance),
                },
            )

    logger.info(
        "balance reconciliation completed",
        extra={"accounts_checked": Account.objects.count(), "mismatches_found": len(mismatches)},
    )
    return {"mismatches": mismatches}
