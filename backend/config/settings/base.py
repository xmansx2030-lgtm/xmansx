"""الإعدادات المشتركة لكل البيئات.

لا تضع هنا أي سر إنتاجي — الأسرار تأتي من متغيرات البيئة حصرًا.
production.py يعيد فرض المتغيرات الحساسة كمتغيرات إلزامية بلا defaults.
"""

import math
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

from beat_schedule import build_beat_schedule
from config.database import postgres_database
from config.env import env_bool, env_float, env_int, env_list, env_str
from config.redis import cache_options

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# مفتاح تطوير فقط — production.py يرفض هذا المفتاح ويطلب متغير البيئة إلزاميًا
SECRET_KEY = env_str("DJANGO_SECRET_KEY", "django-insecure-dev-only-key-do-not-use")

DEBUG = False  # كل بيئة تحدد قيمتها صراحةً
DJANGO_ADMIN_ENABLED = env_bool("DJANGO_ADMIN_ENABLED", True)

ALLOWED_HOSTS: list[str] = []

# التطبيقات المحلية أولاً: يتيح تجاوز أوامر الإدارة القياسية (مثل createsuperuser)
INSTALLED_APPS = [
    "common",
    "accounts",
    "schools",
    "memberships",
    "academics",
    "students",
    "staff",
    "attendance",
    "devices",
    "excuses",
    "student_warnings",
    "student_actions",
    "student_leaves",
    "documents",
    "referrals",
    "counseling",
    "school_dashboard",
    "school_sms",
    "parents",
    "subscriptions",
    "platform_team",
    "audit",
    "operations",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "drf_spectacular",
]

AUTH_USER_MODEL = "accounts.User"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "common.middleware.ResponseSecurityMiddleware",
    "common.middleware.RequestIDMiddleware",
    "common.middleware.RequestLogMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "common.middleware.SessionActivityMiddleware",
    "memberships.middleware.TenantContextMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "csp.middleware.CSPMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# ---- Database: PostgreSQL فقط (لا SQLite — نعتمد constraints/locking/RLS لاحقًا) ----
DATABASES = {"default": postgres_database(production=False)}
DATABASE_RLS_ENFORCED = False

# Activation URL is constructed from trusted deployment configuration, never Host.
PARENT_PORTAL_BASE_URL = env_str("PARENT_PORTAL_BASE_URL", "http://localhost:5173")
PARENT_ACTIVATION_TTL_SECONDS = env_int("PARENT_ACTIVATION_TTL_SECONDS", 48 * 60 * 60)
PARENT_FAMILY_INVITATION_TTL_SECONDS = env_int("PARENT_FAMILY_INVITATION_TTL_SECONDS", 24 * 60 * 60)
PARENT_FAMILY_INVITATION_SMS_ENABLED = env_bool("PARENT_FAMILY_INVITATION_SMS_ENABLED", False)
# Only invitation delivery; absence SMS configuration and eligibility are independent.
PARENT_FAMILY_INVITATION_SMS_ADAPTER = env_str("PARENT_FAMILY_INVITATION_SMS_ADAPTER", "provider")
PARENT_REGISTRATION_IP_LIMIT = env_int("PARENT_REGISTRATION_IP_LIMIT", 60)
PARENT_REGISTRATION_MOBILE_LIMIT = env_int("PARENT_REGISTRATION_MOBILE_LIMIT", 10)

# Recovery delivery only; this never disables the parent-space ownership gate.
PARENT_RECOVERY_EMAIL_ENABLED = env_bool("PARENT_RECOVERY_EMAIL_ENABLED", False)
PARENT_RECOVERY_VERIFY_TTL_SECONDS = env_int("PARENT_RECOVERY_VERIFY_TTL_SECONDS", 86400)
PARENT_RECOVERY_RESET_TTL_SECONDS = env_int("PARENT_RECOVERY_RESET_TTL_SECONDS", 900)
PARENT_RECOVERY_EMAIL_ADAPTER = env_str("PARENT_RECOVERY_EMAIL_ADAPTER", "resend")
PARENT_RECOVERY_SYNTHETIC_EMAIL_ROOT = env_str("PARENT_RECOVERY_SYNTHETIC_EMAIL_ROOT", "")
RESEND_API_KEY = env_str("RESEND_API_KEY", "")
RESEND_FROM_EMAIL = env_str("RESEND_FROM_EMAIL", "")
RESEND_TIMEOUT_SECONDS = env_int("RESEND_TIMEOUT_SECONDS", 10)

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Argon2id أولاً (ADR-004) — البقية للتوافق مع hashes قديمة فقط
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---- Internationalization: Arabic First ----
LANGUAGE_CODE = "ar"
TIME_ZONE = "Asia/Riyadh"
USE_I18N = True
USE_TZ = True

# ---- Static / Media ----
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = Path(env_str("MEDIA_ROOT", str(BASE_DIR / "mediafiles")))

# ---- Redis / Celery (foundation فقط — لا مهام أعمال بعد) ----
REDIS_URL = env_str("REDIS_URL", "redis://localhost:6379/0")
# Backward-compatible defaults keep development simple. Scalable deployments
# provide separate services so cache eviction can never discard security
# counters or queued Celery work.
CACHE_REDIS_URL = env_str("CACHE_REDIS_URL", REDIS_URL)
SECURITY_REDIS_URL = env_str("SECURITY_REDIS_URL", REDIS_URL)
CELERY_BROKER_URL = env_str("CELERY_BROKER_URL", REDIS_URL)
CELERY_RESULT_BACKEND = env_str("CELERY_RESULT_BACKEND", CELERY_BROKER_URL)
READINESS_CHECK_TIMEOUT_SECONDS = 2
OPERATIONAL_HEARTBEAT_MAX_AGE_SECONDS = env_int("OPERATIONAL_HEARTBEAT_MAX_AGE_SECONDS", 5 * 60)
BRIDGE_STALE_AFTER_SECONDS = env_int("BRIDGE_STALE_AFTER_SECONDS", 2 * 60)
BRIDGE_OFFLINE_AFTER_SECONDS = env_int("BRIDGE_OFFLINE_AFTER_SECONDS", 5 * 60)
# Production validates this value explicitly; defining it here keeps middleware
# behavior deterministic in local and test settings as well.
SESSION_ACTIVITY_TOUCH_INTERVAL_SECONDS = env_int(
    "SESSION_ACTIVITY_TOUCH_INTERVAL_SECONDS", 5 * 60
)

SENTRY_DSN = env_str("SENTRY_DSN", "")
SENTRY_ENVIRONMENT = env_str("SENTRY_ENVIRONMENT", "local")
SENTRY_RELEASE = env_str("SENTRY_RELEASE", "")
SENTRY_TRACES_SAMPLE_RATE = env_float("SENTRY_TRACES_SAMPLE_RATE", 0.0)

CACHES = {
    "default": {
        "BACKEND": "common.cache.ResilientRedisCache",
        "LOCATION": CACHE_REDIS_URL,
        "KEY_PREFIX": "xmansx",
        "OPTIONS": cache_options("cache"),
    },
    "security": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": SECURITY_REDIS_URL,
        "KEY_PREFIX": "xmansx-security",
        "OPTIONS": cache_options("security"),
    },
}

# ---- Login rate limiting: (الحد الأقصى، النافذة بالثواني) ----
# قابلة للضبط بالبيئة: التطوير/E2E يرفعها — الإنتاج يبقى على الافتراضي الصارم
LOGIN_RATE_LIMIT_IP = (env_int("LOGIN_RATE_LIMIT_IP_MAX", 20), 300)
LOGIN_RATE_LIMIT_MOBILE = (env_int("LOGIN_RATE_LIMIT_MOBILE_MAX", 5), 300)

# التسجيل الذاتي قابل للإيقاف تشغيليًا، وحدوده أضيق لأنه ينشئ مستأجرًا جديدًا.
SELF_REGISTRATION_ENABLED = env_bool("SELF_REGISTRATION_ENABLED", True)
SELF_REGISTRATION_RATE_LIMIT_IP = (
    env_int("SELF_REGISTRATION_RATE_LIMIT_IP_MAX", 5),
    60 * 60,
)
SELF_REGISTRATION_RATE_LIMIT_MOBILE = (
    env_int("SELF_REGISTRATION_RATE_LIMIT_MOBILE_MAX", 3),
    24 * 60 * 60,
)

# Keep synchronous PDF rendering from occupying every web worker under bursts.
PDF_RENDER_CONCURRENCY = env_int("PDF_RENDER_CONCURRENCY", 4)
ATTENDANCE_CURRENT_PERIOD_CACHE_TTL = env_int("ATTENDANCE_CURRENT_PERIOD_CACHE_TTL", 10)
ATTENDANCE_MONITORING_CACHE_TTL = env_int("ATTENDANCE_MONITORING_CACHE_TTL", 5)
DASHBOARD_CACHE_WAIT_SECONDS = env_float("DASHBOARD_CACHE_WAIT_SECONDS", 5.0)
DASHBOARD_CACHE_LEASE_SECONDS = env_int("DASHBOARD_CACHE_LEASE_SECONDS", 30)
API_RATE_LIMIT_ENABLED = env_bool("API_RATE_LIMIT_ENABLED", True)
API_USER_REQUESTS_PER_MINUTE = env_int("API_USER_REQUESTS_PER_MINUTE", 240)
API_USER_EXPORTS_PER_MINUTE = env_int("API_USER_EXPORTS_PER_MINUTE", 12)
if (
    not math.isfinite(DASHBOARD_CACHE_WAIT_SECONDS)
    or DASHBOARD_CACHE_WAIT_SECONDS <= 0
    or DASHBOARD_CACHE_LEASE_SECONDS <= 0
    or min(API_USER_REQUESTS_PER_MINUTE, API_USER_EXPORTS_PER_MINUTE) <= 0
):
    raise ImproperlyConfigured("Cache wait/lease and account request budgets must be positive")

# ---- تشفير المعرفات الحساسة (ADR-009) ----
# مفاتيح تطوير فقط — production.py يفرضها من البيئة ويفشل بدونها
FIELD_ENCRYPTION_KEYS = env_list(
    "FIELD_ENCRYPTION_KEYS",
    ["g8_LpA8xmZcbg6EMSduJi5tKU9zdBr0HncpN9zAcFNo="],  # dev-only Fernet key
)
NATIONAL_ID_HMAC_KEY = env_str("NATIONAL_ID_HMAC_KEY", "dev-only-hmac-key-not-for-production")

# ---- حدود استيراد الطلاب ----
STUDENT_IMPORT_MAX_FILE_BYTES = 10 * 1024 * 1024  # 10MB
STUDENT_IMPORT_MAX_ROWS = 10_000
STUDENT_IMPORT_MAX_ZIP_ENTRIES = 200
STUDENT_IMPORT_MAX_UNCOMPRESSED_BYTES = 60 * 1024 * 1024  # حماية zip bomb

# ---- مرفقات الأعذار (م10): PDF/JPG/PNG بتخزين خاص ----
EXCUSE_ATTACHMENT_MAX_FILE_BYTES = 10 * 1024 * 1024  # 10MB

# ---- المستندات المولدة (م12): تخزين خاص **خارج** MEDIA_ROOT ----
# ‏MEDIA_ROOT يخدم عبر HTTP في التطوير؛ المستندات الرسمية لا يجوز أن تكون
# قابلة للتنزيل بلا مصادقة — التنزيل عبر endpoint مصرح فقط.
GENERATED_DOCUMENTS_ROOT = env_str(
    "GENERATED_DOCUMENTS_ROOT", str(BASE_DIR / "privatefiles" / "documents")
)

# Local roots are drill/staging areas. Production retention must use a separate failure domain.
DATABASE_BACKUP_ROOT = env_str("DATABASE_BACKUP_ROOT", str(BASE_DIR / "local_storage" / "backups"))
BACKUP_ENVIRONMENT = env_str("BACKUP_ENVIRONMENT", "local")
BACKUP_REMOTE_ENABLED = env_bool("BACKUP_REMOTE_ENABLED", False)
BACKUP_REQUIRE_REMOTE = env_bool("BACKUP_REQUIRE_REMOTE", False)
BACKUP_KEEP_LATEST_ONLY = env_bool("BACKUP_KEEP_LATEST_ONLY", False)
BACKUP_COMMAND_TIMEOUT_SECONDS = env_int("BACKUP_COMMAND_TIMEOUT_SECONDS", 60 * 60)
RESTORE_COMMAND_TIMEOUT_SECONDS = env_int("RESTORE_COMMAND_TIMEOUT_SECONDS", 60 * 60)
BACKUP_MAX_AGE_SECONDS = env_int("BACKUP_MAX_AGE_SECONDS", 26 * 60 * 60)
PG_DUMP_BINARY = env_str("PG_DUMP_BINARY", "pg_dump")
PG_RESTORE_BINARY = env_str("PG_RESTORE_BINARY", "pg_restore")

R2_ENABLED = env_bool("R2_ENABLED", False)
R2_BACKUP_ENABLED = env_bool("R2_BACKUP_ENABLED", R2_ENABLED)


def _r2_storage(bucket_name: str, location: str) -> dict:
    """Build an isolated, private R2 storage alias.

    Alias-local options avoid the global ``AWS_STORAGE_BUCKET_NAME`` setting so
    application objects and database backups can live in different buckets.
    """
    return {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "access_key": env_str("R2_ACCESS_KEY_ID", ""),
            "secret_key": env_str("R2_SECRET_ACCESS_KEY", ""),
            "bucket_name": bucket_name,
            "endpoint_url": env_str("R2_ENDPOINT_URL", ""),
            "region_name": "auto",
            "location": location,
            "default_acl": None,
            "querystring_auth": True,
            "file_overwrite": False,
            # R2 encrypts at rest automatically and rejects the S3 SSE header.
        },
    }


STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "private_documents": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
        "OPTIONS": {"location": GENERATED_DOCUMENTS_ROOT},
    },
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    "backups": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
        "OPTIONS": {
            "location": env_str(
                "BACKUP_STORAGE_LOCATION", str(BASE_DIR / "local_storage" / "repository")
            )
        },
    },
}
if R2_ENABLED:
    _private_bucket = env_str("R2_PRIVATE_BUCKET_NAME", "")
    STORAGES["default"] = _r2_storage(_private_bucket, env_str("R2_MEDIA_PREFIX", "media"))
    STORAGES["private_documents"] = _r2_storage(
        _private_bucket, env_str("R2_DOCUMENTS_PREFIX", "documents")
    )
if R2_BACKUP_ENABLED:
    STORAGES["backups"] = _r2_storage(
        env_str("R2_BACKUP_BUCKET_NAME", ""),
        env_str("R2_BACKUPS_PREFIX", "database-backups"),
    )

# Application workflows persist their progress in PostgreSQL and clients poll that
# durable state. Keep the result backend only for the small number of diagnostic
# tasks that opt in, and expire those values predictably instead of letting them
# compete indefinitely with the broker and performance cache.
CELERY_RESULT_EXPIRES = env_int("CELERY_RESULT_EXPIRES", 60 * 60)
CELERY_TASK_ALWAYS_EAGER = False
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_BROKER_POOL_LIMIT = env_int("CELERY_BROKER_POOL_LIMIT", 4)
CELERY_BROKER_CONNECTION_TIMEOUT = 5
CELERY_BROKER_TRANSPORT_OPTIONS = {
    "max_connections": env_int("CELERY_BROKER_MAX_CONNECTIONS", 16),
    "socket_connect_timeout": 3,
    "socket_timeout": 5,
    "retry_on_timeout": False,
    "health_check_interval": 30,
}
CELERY_REDIS_MAX_CONNECTIONS = env_int("CELERY_RESULT_MAX_CONNECTIONS", 8)
CELERY_REDIS_SOCKET_CONNECT_TIMEOUT = 3
CELERY_REDIS_SOCKET_TIMEOUT = 5
if min(
    CELERY_BROKER_POOL_LIMIT,
    CELERY_BROKER_TRANSPORT_OPTIONS["max_connections"],
    CELERY_REDIS_MAX_CONNECTIONS,
) < 1:
    raise ImproperlyConfigured("Celery Redis connection limits must be positive")
CELERY_TIMEZONE = TIME_ZONE
# Fair scheduling prevents one large school's imports from reserving a whole
# worker's future task capacity. Jobs are idempotent and acknowledged on finish.
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_IMPORTS = ("parents.email_recovery_tasks", "parents.activation_email")
CELERY_TASK_ROUTES = {
    "students.process_import_job": {"queue": "imports"},
    "students.commit_import_job": {"queue": "imports"},
    "staff.process_import_job": {"queue": "imports"},
    "students.run_purge_job": {"queue": "maintenance"},
    "operations.scheduled_database_backup": {"queue": "maintenance"},
    "academics.sync_ministry_calendar": {"queue": "maintenance"},
    "academics.apply_ministry_calendars": {"queue": "maintenance"},
}
_backup_schedule_enabled = env_bool("BACKUP_SCHEDULE_ENABLED", False)
MINISTRY_CALENDAR_ENABLED = env_bool("MINISTRY_CALENDAR_ENABLED", True)
CELERY_BEAT_SCHEDULE = build_beat_schedule(
    ministry_calendar_enabled=MINISTRY_CALENDAR_ENABLED,
    heartbeat_interval_seconds=env_int("OPERATIONAL_HEARTBEAT_INTERVAL_SECONDS", 120),
    backup_enabled=_backup_schedule_enabled,
    backup_interval_seconds=(
        env_int("BACKUP_SCHEDULE_INTERVAL_SECONDS", 24 * 60 * 60)
        if _backup_schedule_enabled
        else 24 * 60 * 60
    ),
)

# ---- DRF ----
REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_THROTTLE_CLASSES": ["common.throttling.AccountPressureThrottle"],
    # آمن افتراضيًا: كل endpoint مغلق ما لم يصرح بعكس ذلك (health تصرح بـ AllowAny)
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "EXCEPTION_HANDLER": "common.errors.api_exception_handler",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "منصة المواظبة والمتابعة الطلابية — API",
    "VERSION": "1.0.0",
    "DESCRIPTION": "واجهات SaaS متعددة المدارس. المدرسة تستمد من الجلسة — لا school_id من العميل.",
    "SERVE_INCLUDE_SCHEMA": False,
    # الإنتاج: الوثائق للمستخدمين المصادقين فقط — local.py يفتحها للتطوير
    "SERVE_PERMISSIONS": ["rest_framework.permissions.IsAdminUser"],
    "SWAGGER_UI_SETTINGS": {"persistAuthorization": True},
    "ENUM_NAME_OVERRIDES": {
        "ParentRequestStatusEnum": ["PENDING", "NEEDS_INFO", "APPROVED", "REJECTED", "CANCELLED"],
        "ParentExcuseTypeEnum": ["EXCUSE"],
        "ParentCorrectionTypeEnum": ["CORRECTION"],
        "RecoveryOperationEnum": "parents.recovery_models.RecoveryOperation",
        "RecoveryEvidenceKindEnum": "parents.recovery_models.RecoveryEvidenceKind",
        "RecoveryReviewStageEnum": "parents.recovery_models.RecoveryReviewStage",
        "RecoveryRecommendationEnum": "parents.recovery_models.RecoveryRecommendation",
    },
}

# ---- CORS: مغلق افتراضيًا؛ local.py يسمح لـ Vite dev فقط ----
CORS_ALLOWED_ORIGINS: list[str] = []
CORS_ALLOW_CREDENTIALS = True

# ---- Security headers (الأساس المشترك؛ production يشدد أكثر) ----
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
X_FRAME_OPTIONS = "DENY"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"

# ---- CSP (django-csp v4) ----
CONTENT_SECURITY_POLICY = {
    "DIRECTIVES": {
        "default-src": ["'self'"],
        "img-src": ["'self'", "data:"],
        "style-src": ["'self'"],
        "script-src": ["'self'"],
        "connect-src": ["'self'"],
        "frame-ancestors": ["'none'"],
        "base-uri": ["'self'"],
        "form-action": ["'self'"],
    },
}

# ---- Structured JSON logging ----
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {"()": "common.logging.JsonFormatter"},
    },
    "filters": {
        "request_id": {"()": "common.logging.RequestIDFilter"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
            "filters": ["request_id"],
        },
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django.request": {"level": "WARNING"},  # نسجل الطلبات بأنفسنا في RequestLogMiddleware
        "xmansx.request": {"level": "INFO"},
        # توليد PDF (م12): WeasyPrint/fontTools يسجلان كل خطوة تخطيط وكل glyph —
        # ضجيج بمئات الأسطر لكل مستند يخفي سجلاتنا. الأخطاء وحدها تهم.
        "weasyprint": {"level": "WARNING"},
        "fontTools": {"level": "WARNING"},
    },
}
