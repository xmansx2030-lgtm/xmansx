"""بيئة الإنتاج.

القاعدة (المتطلب 30): نقص متغير حساس = فشل تشغيل واضح (ImproperlyConfigured)،
لا سقوط صامت إلى default غير آمن.
"""

from django.core.exceptions import ImproperlyConfigured

from config.env import env_bool, env_int, env_list, env_str

from .base import *

DEBUG = False

# ---- إلزامية بلا defaults ----
SECRET_KEY = env_str("DJANGO_SECRET_KEY")
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS")

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env_str("POSTGRES_DB"),
        "USER": env_str("POSTGRES_USER"),
        "PASSWORD": env_str("POSTGRES_PASSWORD"),
        "HOST": env_str("POSTGRES_HOST"),
        "PORT": env_int("POSTGRES_PORT", 5432),
        "CONN_MAX_AGE": 60,
    }
}

REDIS_URL = env_str("REDIS_URL")
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL

# مفاتيح تشفير المعرفات — إلزامية في الإنتاج (ADR-009)
FIELD_ENCRYPTION_KEYS = env_list("FIELD_ENCRYPTION_KEYS")
NATIONAL_ID_HMAC_KEY = env_str("NATIONAL_ID_HMAC_KEY")

if NATIONAL_ID_HMAC_KEY.startswith("dev-only"):
    raise ImproperlyConfigured("NATIONAL_ID_HMAC_KEY is set to an insecure development value")

if SECRET_KEY.startswith("django-insecure"):
    raise ImproperlyConfigured("DJANGO_SECRET_KEY is set to an insecure development value")

# ---- HTTPS / HSTS ----
SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", True)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_SECONDS = env_int("DJANGO_HSTS_SECONDS", 60 * 60 * 24 * 30)  # يرفع بعد الاستقرار
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = False  # يفعل يدويًا بعد التأكد

# ---- Cookies ----
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS", [])

# CORS في الإنتاج: نفس الـ Origin عبر Proxy — لا origins خارجية إلا بقرار صريح
CORS_ALLOWED_ORIGINS = env_list("DJANGO_CORS_ALLOWED_ORIGINS", [])
