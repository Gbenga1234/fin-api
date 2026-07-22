"""
Django settings for the gowobo-py fintech API.

Config is environment-driven (12-factor style) so this runs the same way
locally, in Docker, and in Kubernetes - matching the pattern used by the
Go services (ExternalSecret -> env vars -> app config).
"""
from pathlib import Path
import environ
from celery.schedules import crontab

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, False),
)
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY", default="django-insecure-change-me-in-production")
DEBUG = env.bool("DEBUG", default=False)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "accounts",
    "transactions",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Structured per-request access log (method, path, status, duration,
    # request id) - written to stdout so it shows up in `docker logs` /
    # `kubectl logs` the same way the Go services' structured logs do.
    "gowobo_py.middleware.RequestLoggingMiddleware",
]

ROOT_URLCONF = "gowobo_py.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "gowobo_py.wsgi.application"

# DATABASE_URL example: postgres://user:pass@host:5432/dbname
DATABASES = {
    "default": env.db(
        "DATABASE_URL", default="postgres://gowobo:gowobo@localhost:5432/gowobo"
    )
}
# Row-level locking (SELECT ... FOR UPDATE) requires a real transaction per
# request/command; ATOMIC_REQUESTS is deliberately left False because the
# financial services wrap their own db_transaction.atomic() blocks explicitly
# around the locked sections - see transactions/services.py.

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# NOTE: JWT auth is a known gap (tracked the same way as on the Go services).
# Session/Basic auth is a placeholder so the API is usable behind an
# internal network / API gateway today. Swap in
# `rest_framework_simplejwt.authentication.JWTAuthentication` once JWT
# issuance is wired up.
LOG_LEVEL = env("LOG_LEVEL", default="INFO")

# Everything goes to stdout as single-line JSON, no per-service log files -
# matches the Go services (structured logs, container-native, shipped
# onward by whatever's collecting stdout - GKE Cloud Logging in prod).
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "gowobo_py.logging_utils.JsonFormatter",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": LOG_LEVEL,
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": LOG_LEVEL,
            "propagate": False,
        },
        "django.request": {
            "handlers": ["console"],
            "level": "ERROR",
            "propagate": False,
        },
        # Only used by `manage.py runserver` in local dev - our own
        # RequestLoggingMiddleware already logs every request cleanly, so
        # this one is muted to avoid a noisy duplicate line.
        "django.server": {
            "handlers": [],
            "level": "CRITICAL",
            "propagate": False,
        },
        # our own apps
        "gowobo_py": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
        "accounts": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
        "transactions": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
    },
}


# --- Celery -------------------------------------------------------------
# Redis is already part of the stack (see the in-cluster Redis StatefulSet
# in the Gowobo Helm chart), so it's reused here as both broker and result
# backend rather than introducing a new dependency.
#
# Money movement itself (TransferService) stays fully synchronous - it
# needs to return a definite success/fail within the request/response
# cycle. Celery is for side effects that must never be allowed to block or
# fail a transfer: outbound notifications and the periodic balance
# reconciliation job (see transactions/tasks.py).
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://localhost:6379/0")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default=CELERY_BROKER_URL)
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_TRACK_STARTED = True
# Redeliver a task to another worker if this one dies mid-task, rather than
# silently dropping it - important for anything touching financial data.
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1

CELERY_BEAT_SCHEDULE = {
    "reconcile-account-balances-daily": {
        "task": "transactions.tasks.reconcile_account_balances",
        "schedule": crontab(hour=1, minute=0),
    },
}

REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.BasicAuthentication",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
}
