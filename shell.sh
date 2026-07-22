#!/usr/bin/env bash
# Convenience wrapper: ./shell.sh drops you into the interactive admin CLI.
# ./shell.sh django gives you the plain Django ORM shell instead.
set -euo pipefail

if [[ "${1:-}" == "django" ]]; then
    exec python manage.py shell
else
    exec python manage.py adminshell
fi
