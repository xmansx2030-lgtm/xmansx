"""بيئة الاختبارات — PostgreSQL حقيقي، بلا شبكات خارجية أخرى."""

from .base import *

DEBUG = False

ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver"]

SECRET_KEY = "test-only-secret-key-not-for-production"  # noqa: S105

# hashing أسرع في الاختبارات (لا يمس الإنتاج)
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# مهام Celery تنفذ متزامنة داخل الاختبارات
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
