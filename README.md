# gowobo-py

A Django REST Framework fintech API (accounts + transactions), served by
Gunicorn, with an interactive admin shell for operational tasks.

This is a Python sibling to the Go-based Gowobo services, applying the same
financial-safety rules:

- **Idempotency**: every transaction request carries an `idempotency_key`,
  enforced by a unique DB constraint - not just an app-level check - so a
  retried request can never double-process.
- **Pessimistic row locking**: balances are read/written under
  `SELECT ... FOR UPDATE` (`select_for_update()`).
- **Deterministic lock ordering**: when a transfer touches two accounts,
  they're locked in a stable order (sorted by id) so two concurrent
  transfers between the same pair of accounts can't deadlock.
- **Atomicity**: each operation runs inside one DB transaction. Because both
  accounts live in the same database here (unlike the Go services, which
  call across two HTTP APIs), a single atomic transaction gives full
  all-or-nothing semantics without needing a separate compensating-reversal
  step.

## Layout

```
gowobo_py/          project settings, root urls, wsgi
accounts/           Account model, API, admin, wait_for_db command
transactions/       Transaction model, TransferService, API, adminshell command
gunicorn.conf.py    gunicorn config (env-driven)
start.sh            migrate + collectstatic + launch gunicorn
shell.sh            ./shell.sh          -> interactive admin CLI
                    ./shell.sh django   -> plain `manage.py shell`
Dockerfile          multi-stage build
requirements.txt
.env.example
```

## Local setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # edit DATABASE_URL etc.

python manage.py migrate
python manage.py createsuperuser   # optional, for /admin/

# dev server
python manage.py runserver

# or production-style, via gunicorn
./start.sh
```

## Admin shell

```bash
python manage.py adminshell
```

```
gowobo> create_account owner-1 "Ada Lovelace" NGN
created account 6f2e6b1a-....
gowobo> credit 6f2e6b1a-.... 5000
transaction ...-> completed
gowobo> transfer 6f2e6b1a-.... 9a1c.... 1500
transaction ...-> completed
gowobo> list_transactions
```

Every money-moving shell command calls the same `TransferService` used by
the HTTP API, so it gets identical idempotency/locking/atomicity guarantees
- there's no separate, less-safe "admin" code path.

## API

| Method | Path                              | Purpose               |
|--------|------------------------------------|------------------------|
| GET    | `/api/v1/accounts/`                | list accounts          |
| POST   | `/api/v1/accounts/`                | create account         |
| GET    | `/api/v1/accounts/{id}/`           | get account            |
| GET    | `/api/v1/accounts/{id}/balance/`   | get balance            |
| GET    | `/api/v1/transactions/`            | list transactions      |
| GET    | `/api/v1/transactions/{id}/`       | get transaction        |
| POST   | `/api/v1/transactions/deposit/`    | deposit funds          |
| POST   | `/api/v1/transactions/withdraw/`   | withdraw funds         |
| POST   | `/api/v1/transactions/transfer/`   | transfer between accts |
| GET    | `/healthz/`                        | health check           |

`deposit` / `withdraw` / `transfer` all require an `idempotency_key` in the
request body.

## Background tasks (Celery)

Money movement (`TransferService`) stays fully synchronous - a transfer
must return a definite success/fail within the request cycle. Celery
handles everything else, so a slow notifier or a scheduled report can
never block or fail a transaction:

- **`transactions.tasks.send_transaction_notification`** - fires after
  every completed *or* failed transaction (stub for a webhook/email/SMS
  call). `TransferService` schedules it via `transaction.on_commit(...)`,
  so it only runs once the DB transaction has actually committed.
- **`transactions.tasks.reconcile_account_balances`** - runs daily at
  01:00 (see `CELERY_BEAT_SCHEDULE` in `settings.py`), recomputes every
  account's balance from its completed-transaction ledger, and logs an
  ERROR for any mismatch. Read-only - it flags discrepancies, it never
  auto-corrects them.

Redis is reused as both broker and result backend - it's already part of
the stack (see the Redis StatefulSet in the Gowobo Helm chart).

**Run locally:**
```bash
docker-compose up          # postgres + redis + web + worker + beat together
```
or without Docker, in separate terminals:
```bash
./worker.sh                # celery worker
./beat.sh                  # celery beat (schedules periodic tasks)
```

`CELERY_TASK_ACKS_LATE = True` means an in-flight task is redelivered to
another worker if its worker process dies mid-task, rather than being
silently dropped - important for anything touching financial data. Beat
must run as a single replica (never scaled out), or scheduled tasks fire
more than once.

## Logging

All logs are single-line JSON on stdout - visible via `docker logs` /
`kubectl logs` with no extra setup:

- **Access logs**: `RequestLoggingMiddleware` logs one line per request
  (`method`, `path`, `status_code`, `duration_ms`, `request_id`,
  `remote_addr`). The same `request_id` is echoed back as an
  `X-Request-ID` response header for client-side correlation. Gunicorn's
  own access/error logs (`accesslog = "-"`, `errorlog = "-"` in
  `gunicorn.conf.py`) also go to stdout/stderr as a second line per
  request.
- **Transaction logs**: every deposit/withdrawal/transfer outcome is
  logged from `transactions/services.py` - `"transaction completed"` (INFO)
  or `"transaction failed"` (WARNING, with `failure_reason`) - plus a line
  whenever an idempotency key is replayed, so duplicate client retries are
  visible instead of silent.
- Set the level with `LOG_LEVEL` (default `INFO`). The formatter lives in
  `gowobo_py/logging_utils.py`; anything passed via `extra={...}` on a log
  call is merged straight into the JSON line.

Example:
```json
{"time": "2026-07-21T19:27:34+0000", "level": "WARNING", "logger": "transactions.services", "message": "transaction failed", "transaction_id": "...", "idempotency_key": "...", "tx_type": "withdrawal", "failure_reason": "Insufficient funds"}
```

## Known gaps (tracked the same way as on the Go services)

- **JWT auth**: not wired up yet. `REST_FRAMEWORK["DEFAULT_AUTHENTICATION_CLASSES"]`
  currently uses Session/Basic auth as a placeholder; swap in
  `djangorestframework-simplejwt` once issuance is ready.
- **Structured migrations strategy**: Django's built-in migrations are used
  as-is; no additional Alembic-style tooling has been layered on.
- **Audit logging**: not yet wired to GKE Cloud Logging / Cloud Storage sinks.
