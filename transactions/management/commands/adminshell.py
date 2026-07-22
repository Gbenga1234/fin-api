"""
Interactive admin shell: `python manage.py adminshell`

Every money-moving command goes through TransferService, so operators get
the exact same idempotency / locking / atomicity guarantees as the HTTP
API - there is no separate "admin backdoor" code path that could skip a
safety check.
"""
import cmd
import uuid
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand

from accounts.models import Account
from transactions.models import Transaction
from transactions.services import TransferService


class AdminShell(cmd.Cmd):
    intro = (
        "Gowobo fintech admin shell. Type 'help' for commands, 'exit' to quit.\n"
        "Money-moving commands (credit/debit/transfer) use the same\n"
        "TransferService as the HTTP API - same idempotency, locking, and\n"
        "atomicity guarantees.\n"
    )
    prompt = "gowobo> "

    # ---------------------------------------------------------------- accounts

    def do_list_accounts(self, arg):
        "list_accounts - list all accounts"
        accounts = Account.objects.all().order_by("created_at")
        if not accounts:
            print("(no accounts yet)")
            return
        for acc in accounts:
            print(f"{acc.id}  {acc.owner_name:<20}  {acc.balance:>14} {acc.currency}  [{acc.status}]")

    def do_create_account(self, arg):
        "create_account <owner_id> <owner_name> [currency=NGN]"
        parts = arg.split()
        if len(parts) < 2:
            print("usage: create_account <owner_id> <owner_name> [currency]")
            return
        owner_id, owner_name = parts[0], parts[1]
        currency = parts[2].upper() if len(parts) > 2 else "NGN"
        acc = Account.objects.create(owner_id=owner_id, owner_name=owner_name, currency=currency)
        print(f"created account {acc.id}")

    def do_show_account(self, arg):
        "show_account <account_id>"
        acc = self._find_account(arg)
        if acc:
            print(
                f"{acc.id}\n"
                f"  owner:   {acc.owner_name} ({acc.owner_id})\n"
                f"  balance: {acc.balance} {acc.currency}\n"
                f"  status:  {acc.status}\n"
            )

    def do_freeze_account(self, arg):
        "freeze_account <account_id>"
        self._set_account_status(arg, Account.Status.FROZEN)

    def do_unfreeze_account(self, arg):
        "unfreeze_account <account_id>"
        self._set_account_status(arg, Account.Status.ACTIVE)

    def _find_account(self, account_id):
        try:
            return Account.objects.get(id=account_id.strip())
        except (Account.DoesNotExist, ValueError):
            print("account not found")
            return None

    def _set_account_status(self, account_id, new_status):
        acc = self._find_account(account_id)
        if not acc:
            return
        acc.status = new_status
        acc.save(update_fields=["status", "updated_at"])
        print(f"account {acc.id} is now {new_status}")

    # ------------------------------------------------------------ money moves

    def do_credit(self, arg):
        "credit <account_id> <amount> - deposit funds into an account"
        self._run_money_command(arg, expected_parts=2, op=self._credit_op)

    def do_debit(self, arg):
        "debit <account_id> <amount> - withdraw funds from an account"
        self._run_money_command(arg, expected_parts=2, op=self._debit_op)

    def do_transfer(self, arg):
        "transfer <from_account_id> <to_account_id> <amount>"
        self._run_money_command(arg, expected_parts=3, op=self._transfer_op)

    def _credit_op(self, parts):
        account_id, amount = parts
        return TransferService.deposit(
            account_id=account_id,
            amount=Decimal(amount),
            idempotency_key=f"adminshell-credit-{uuid.uuid4()}",
        )

    def _debit_op(self, parts):
        account_id, amount = parts
        return TransferService.withdraw(
            account_id=account_id,
            amount=Decimal(amount),
            idempotency_key=f"adminshell-debit-{uuid.uuid4()}",
        )

    def _transfer_op(self, parts):
        from_id, to_id, amount = parts
        return TransferService.transfer(
            from_account_id=from_id,
            to_account_id=to_id,
            amount=Decimal(amount),
            idempotency_key=f"adminshell-transfer-{uuid.uuid4()}",
        )

    def _run_money_command(self, arg, expected_parts, op):
        parts = arg.split()
        if len(parts) != expected_parts:
            print("wrong number of arguments - see 'help <command>'")
            return
        try:
            # validate the amount is parseable before calling the service
            Decimal(parts[-1])
        except InvalidOperation:
            print("invalid amount")
            return
        try:
            txn = op(parts)
        except ValidationError as e:
            print(f"error: {e}")
            return
        extra = f" ({txn.failure_reason})" if txn.failure_reason else ""
        print(f"transaction {txn.id} -> {txn.status}{extra}")

    # ------------------------------------------------------------ transactions

    def do_list_transactions(self, arg):
        "list_transactions [limit=20]"
        limit = int(arg.strip()) if arg.strip().isdigit() else 20
        for txn in Transaction.objects.all().order_by("-created_at")[:limit]:
            print(f"{txn.id}  {txn.tx_type:<10}  {txn.amount:>14} {txn.currency}  [{txn.status}]  {txn.created_at}")

    def do_show_transaction(self, arg):
        "show_transaction <transaction_id>"
        try:
            txn = Transaction.objects.get(id=arg.strip())
        except (Transaction.DoesNotExist, ValueError):
            print("transaction not found")
            return
        print(
            f"{txn.id}\n"
            f"  type:           {txn.tx_type}\n"
            f"  from_account:   {txn.from_account_id}\n"
            f"  to_account:     {txn.to_account_id}\n"
            f"  amount:         {txn.amount} {txn.currency}\n"
            f"  status:         {txn.status}\n"
            f"  failure_reason: {txn.failure_reason}\n"
            f"  created_at:     {txn.created_at}\n"
            f"  completed_at:   {txn.completed_at}\n"
        )

    # ------------------------------------------------------------ housekeeping

    def do_exit(self, arg):
        "exit - leave the admin shell"
        print("bye")
        return True

    def do_EOF(self, arg):
        print()
        return True

    def emptyline(self):
        pass


class Command(BaseCommand):
    help = "Interactive admin shell for managing accounts and transactions"

    def handle(self, *args, **options):
        AdminShell().cmdloop()
