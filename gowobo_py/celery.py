import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "gowobo_py.settings")

app = Celery("gowobo_py")
# Pull CELERY_* settings from Django settings.py (namespace="CELERY" means
# CELERY_BROKER_URL in settings.py becomes broker_url here, etc.)
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@app.task(bind=True)
def debug_task(self):
    print(f"Request: {self.request!r}")
