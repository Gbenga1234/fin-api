#!/usr/bin/env bash
# Runs Celery beat, which enqueues scheduled tasks (see CELERY_BEAT_SCHEDULE
# in settings.py, e.g. the daily reconcile_account_balances job). Run as its
# own single-replica container - beat must not be scaled out, or scheduled
# tasks fire multiple times.
set -euo pipefail

exec celery -A gowobo_py beat --loglevel="${CELERY_LOG_LEVEL:-info}"
