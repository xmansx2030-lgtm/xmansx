"""اختبارات إقلاع الأساس: الإعدادات + مهمة Celery التقنية."""

from django.conf import settings

from common.tasks import foundation_ping


def test_test_settings_are_safe():
    assert settings.DEBUG is False
    assert settings.DATABASES["default"]["ENGINE"] == "django.db.backends.postgresql"
    assert settings.CORS_ALLOWED_ORIGINS == []  # لا CORS مفتوح في test/base


def test_foundation_ping_task_runs_eagerly():
    result = foundation_ping.delay()
    assert result.get(timeout=5) == "pong"
