# gowobo-py

A Django REST Framework fintech API for managing accounts and money movement. It is designed to behave like a small, safety-first financial core: transactions are idempotent, balanced with consistent locking, and executed within a single database transaction.

This project is a Python counterpart to the Go-based Gowobo services and follows the same operational patterns around reliability, observability, and deployment.

## Why this project exists

The application is intentionally built around these safety rules:

- Idempotency: each money-moving request includes an `idempotency_key`, and the database enforces uniqueness so retrying the same request cannot double-process funds.
- Pessimistic locking: account balances are read and updated under `SELECT ... FOR UPDATE`.
- Deterministic lock ordering: when a transfer touches two accounts, they are locked in a stable order to avoid deadlocks.
- Atomicity: deposit, withdrawal, and transfer logic runs in a single DB transaction.

This keeps money movement consistent without relying on a wider distributed transaction pattern.

## Project layout

```text
gowobo_py/            Django settings, URL config, WSGI app, Celery app, logging and middleware
accounts/             Account model, API endpoints, admin setup, database wait command
transactions/         Transaction model, transfer logic, API endpoints, admin shell, Celery tasks
Dockerfile            API image used by the web service
Dockerfile.celery     Celery image used by workers and beat
compose.yml           Local stack: Postgres, Redis, API, worker, beat, and Flower
gunicorn.conf.py     Gunicorn runtime configuration
start.sh              Runs migrations, collectstatic, and starts Gunicorn
worker.sh             Starts the Celery worker
beat.sh               Starts the Celery beat scheduler
shell.sh              Opens the interactive admin CLI or the plain Django shell
manage.py             Django management entrypoint
requirements.txt      Python dependencies
```

## Prerequisites

- Python 3.11+
- PostgreSQL
- Redis
- Docker + Docker Compose (recommended for local startup)

## Quick start

### 1) Create the environment file

Create a `.env` file in the project root with values similar to:



### 2) Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3) Run migrations and create a superuser (optional)

```bash
python manage.py migrate
python manage.py createsuperuser
```

### 4) Start the app locally

#### Option A: run the Django dev server

```bash
python manage.py runserver
```

#### Option B: run the full stack with Docker

```bash
docker compose up --build
```

This starts:

- Postgres
- Redis
- API service
- Celery worker
- Celery beat
- Flower dashboard

The API is exposed on port `8000`, and Flower is exposed on port `5555`.

### 5) Check health

```bash
curl http://localhost:8000/healthz/
```

Expected response:

```json
{"status": "ok", "service": "gowobo-py"}
```

## Docker images

The project uses two image definitions, one for the API and one for the Celery stack:

```bash
# API image

docker build -f Dockerfile -t gowobo-web .

# Celery worker / beat image

docker build -f Dockerfile.celery -t gowobo-celery .

# Worker (default command)
docker run gowobo-celery

# Beat scheduler
docker run gowobo-celery ./beat.sh
```

The app entrypoint for the API is [start.sh](start.sh), which waits for Postgres, runs migrations, collects static files, and starts Gunicorn.

## Admin shell

The interactive admin CLI is available through [shell.sh](shell.sh):

```bash
./shell.sh
```

To open a plain Django shell instead:

```bash
./shell.sh django
```

Example:

```text
gowobo> create_account owner-1 "Ada Lovelace" NGN
created account 6f2e6b1a-....
gowobo> credit 6f2e6b1a-.... 5000
transaction ... -> completed
gowobo> transfer 6f2e6b1a-.... 9a1c.... 1500
transaction ... -> completed
gowobo> list_transactions
```

The admin shell calls the same money-movement service used by the HTTP API, so it benefits from the same idempotency and locking behavior.

## API overview

The service exposes REST endpoints under `/api/v1/`.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/accounts/` | List accounts |
| POST | `/api/v1/accounts/` | Create account |
| GET | `/api/v1/accounts/{id}/` | Get account details |
| GET | `/api/v1/accounts/{id}/balance/` | Get account balance |
| GET | `/api/v1/transactions/` | List transactions |
| GET | `/api/v1/transactions/{id}/` | Get transaction details |
| POST | `/api/v1/transactions/deposit/` | Deposit funds |
| POST | `/api/v1/transactions/withdraw/` | Withdraw funds |
| POST | `/api/v1/transactions/transfer/` | Transfer between accounts |
| GET | `/healthz/` | Health check |

### Auth status

The project currently uses Django REST Framework session/basic auth as a placeholder. The `DEFAULT_PERMISSION_CLASSES` in [gowobo_py/settings.py](gowobo_py/settings.py) are set to `IsAuthenticated`, so requests require authentication.

JWT auth is a known follow-up task, not yet implemented.

### Example authenticated request

```bash
curl -u admin:password http://localhost:8000/api/v1/accounts/
```

Deposit, withdrawal, and transfer operations all require an `idempotency_key` in the request body to guarantee safe retries.

## Background tasks and Celery

Money movement stays synchronous. A transfer must return a definitive success or failure within the request cycle. Celery is used for side effects that should not block or fail a transaction.

Current tasks include:

- `transactions.tasks.send_transaction_notification`: fires after a completed or failed transaction, intended for webhook, email, or SMS notifications.
- `transactions.tasks.reconcile_account_balances`: runs daily at 01:00, recomputes balances from the transaction ledger, and flags drift if totals do not match.

The task scheduler is configured in [gowobo_py/settings.py](gowobo_py/settings.py) and uses Redis as both the broker and result backend.

### Run Celery locally

Without Docker, open separate terminals:

```bash
./worker.sh
./beat.sh
```

The project also includes a Flower dashboard in the Compose stack for monitoring tasks.

## Logging and observability

The project emits structured JSON logs to stdout so they integrate cleanly with container logs and platform log aggregation.

### Logged behavior

- Request logs record method, path, response status, duration, request ID, and client address.
- Transaction logs capture completed/failed outcomes and duplicate idempotency-key replays.
- The JSON formatter is configured in [gowobo_py/logging_utils.py](gowobo_py/logging_utils.py).

Example log line:

```json
{"time": "2026-07-21T19:27:34+0000", "level": "WARNING", "logger": "transactions.services", "message": "transaction failed", "transaction_id": "...", "idempotency_key": "...", "tx_type": "withdrawal", "failure_reason": "Insufficient funds"}
```

Set the log level with the `LOG_LEVEL` environment variable.

## Known gaps

The project is intentionally similar to the Go services, but a few items are still pending:

- JWT auth is not yet wired in.
- Migrations remain the default Django migration workflow, without a separate schema-versioning layer.
- Audit logging is not yet integrated with a cloud logging sink or archival store.

## Notes for contributors

- Keep financial operations inside the transaction service layer; do not add ad hoc direct balance changes elsewhere.
- Preserve the idempotency key semantics for all create/transfer operations.
- When touching funds, prefer the existing transfer logic and avoid bypassing the common service path.

## License

This project does not currently declare a license in the repository root. If you plan to distribute it externally, add a license file and document the intended terms.
