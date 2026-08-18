"""بيئة الاختبارات — PostgreSQL حقيقي، بلا شبكات خارجية أخرى."""

from .base import *

DEBUG = False

ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver"]

SECRET_KEY = "test-only-secret-key-not-for-production"  # noqa: S105

# hashing أسرع في الاختبارات (اختبار Argon2 نفسه يعمل بـ override_settings صريح)
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# cache الاختبارات على Redis db منفصل (2) حتى لا تمسح مفاتيح التطوير/الوسيط
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL.rsplit("/", 1)[0] + "/2",
        "KEY_PREFIX": "xmansx-test",
    }
}

# مهام Celery تنفذ متزامنة داخل الاختبارات
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
