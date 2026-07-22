#!/usr/bin/env bash
# Entrypoint for both docker and bare-metal runs.
set -euo pipefail

echo "==> Waiting for database..."
python manage.py wait_for_db --timeout "${DB_WAIT_TIMEOUT:-30}"

echo "==> Running migrations..."
python manage.py migrate --noinput

echo "==> Collecting static files..."
python manage.py collectstatic --noinput

echo "==> Starting gunicorn..."
exec gunicorn gowobo_py.wsgi:application -c gunicorn.conf.py
