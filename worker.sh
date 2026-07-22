#!/usr/bin/env bash
# Runs the Celery worker (processes tasks queued by the web process, e.g.
# send_transaction_notification). Run as a separate container/pod from the
# web process, same as the Go services separate their API and any
# background workers.
set -euo pipefail

echo "==> Waiting for database..."
python manage.py wait_for_db --timeout "${DB_WAIT_TIMEOUT:-30}"

exec celery -A gowobo_py worker \
    --loglevel="${CELERY_LOG_LEVEL:-info}" \
    --concurrency="${CELERY_CONCURRENCY:-4}"
