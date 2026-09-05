"""بيئة الإنتاج.

القاعدة (المتطلب 30): نقص متغير حساس = فشل تشغيل واضح (ImproperlyConfigured)،
لا سقوط صامت إلى default غير آمن.
"""

from urllib.parse import urlparse

from cryptography.fernet import Fernet
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
SENTRY_ENVIRONMENT = env_str("SENTRY_ENVIRONMENT", "production")
BACKUP_ENVIRONMENT = env_str("BACKUP_ENVIRONMENT", "production")
BACKUP_REQUIRE_REMOTE = env_bool("BACKUP_REQUIRE_REMOTE", True)
R2_ENABLED = env_bool("R2_ENABLED", False)

# مفاتيح تشفير المعرفات — إلزامية في الإنتاج (ADR-009)
FIELD_ENCRYPTION_KEYS = env_list("FIELD_ENCRYPTION_KEYS")
NATIONAL_ID_HMAC_KEY = env_str("NATIONAL_ID_HMAC_KEY")

_DEV_FERNET_KEY = "g8_LpA8xmZcbg6EMSduJi5tKU9zdBr0HncpN9zAcFNo="


def _reject_insecure_production_values() -> None:
    # A base64-encoded 256-bit platform-generated secret is 44 characters.
    if len(SECRET_KEY) < 43 or len(set(SECRET_KEY)) < 5 or SECRET_KEY.startswith("django-insecure"):
        raise ImproperlyConfigured("DJANGO_SECRET_KEY does not meet production requirements")
    if not ALLOWED_HOSTS or any(host == "*" for host in ALLOWED_HOSTS):
        raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS must be explicit and cannot contain '*'")
    if any("://" in host or "/" in host for host in ALLOWED_HOSTS):
        raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS must contain host names only")
    if len(NATIONAL_ID_HMAC_KEY) < 32 or NATIONAL_ID_HMAC_KEY.startswith("dev-only"):
        raise ImproperlyConfigured("NATIONAL_ID_HMAC_KEY does not meet production requirements")
    if _DEV_FERNET_KEY in FIELD_ENCRYPTION_KEYS:
        raise ImproperlyConfigured("FIELD_ENCRYPTION_KEYS contains the development key")
    try:
        for key in FIELD_ENCRYPTION_KEYS:
            Fernet(key.encode("ascii"))
    except (ValueError, TypeError) as exc:
        raise ImproperlyConfigured("FIELD_ENCRYPTION_KEYS contains an invalid Fernet key") from exc
    if R2_ENABLED:
        required_r2_values = {
            "R2_ENDPOINT_URL": env_str("R2_ENDPOINT_URL", ""),
            "R2_ACCESS_KEY_ID": env_str("R2_ACCESS_KEY_ID", ""),
            "R2_SECRET_ACCESS_KEY": env_str("R2_SECRET_ACCESS_KEY", ""),
            "R2_PRIVATE_BUCKET_NAME": env_str("R2_PRIVATE_BUCKET_NAME", ""),
            "R2_BACKUP_BUCKET_NAME": env_str("R2_BACKUP_BUCKET_NAME", ""),
        }
        missing_r2_values = [name for name, value in required_r2_values.items() if not value]
        if missing_r2_values:
            raise ImproperlyConfigured(
                "Missing required R2 settings: " + ", ".join(sorted(missing_r2_values))
            )
        if (
            required_r2_values["R2_PRIVATE_BUCKET_NAME"]
            == required_r2_values["R2_BACKUP_BUCKET_NAME"]
        ):
            raise ImproperlyConfigured(
                "R2 private objects and backups must use different buckets"
            )


# ---- HTTPS / HSTS ----
SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", True)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_SECONDS = env_int("DJANGO_HSTS_SECONDS", 60 * 60 * 24 * 30)  # يرفع بعد الاستقرار
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = False  # يفعل يدويًا بعد التأكد

# ---- Cookies ----
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = False  # SPA reads this cookie and mirrors it in X-CSRFToken
SESSION_COOKIE_AGE = env_int("DJANGO_SESSION_COOKIE_AGE", 12 * 60 * 60)
SESSION_SAVE_EVERY_REQUEST = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = False

CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

# CORS في الإنتاج: نفس الـ Origin عبر Proxy — لا origins خارجية إلا بقرار صريح
CORS_ALLOWED_ORIGINS = env_list("DJANGO_CORS_ALLOWED_ORIGINS", [])


def _validate_origins(name: str, origins: list[str]) -> None:
    for origin in origins:
        parsed = urlparse(origin)
        local_http = (
            not SECURE_SSL_REDIRECT
            and parsed.scheme == "http"
            and parsed.hostname in {"localhost", "127.0.0.1", "frontend"}
        )
        if not parsed.hostname or (parsed.scheme != "https" and not local_http):
            raise ImproperlyConfigured(f"{name} must contain explicit HTTPS origins")


if SESSION_COOKIE_AGE <= 0:
    raise ImproperlyConfigured("DJANGO_SESSION_COOKIE_AGE must be a positive number of seconds")

_reject_insecure_production_values()
_validate_origins("DJANGO_CSRF_TRUSTED_ORIGINS", CSRF_TRUSTED_ORIGINS)
_validate_origins("DJANGO_CORS_ALLOWED_ORIGINS", CORS_ALLOWED_ORIGINS)
