"""Celery application — بنية تشغيل فقط في هذه المرحلة (بلا مهام أعمال)."""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")

app = Celery("xmansx")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
