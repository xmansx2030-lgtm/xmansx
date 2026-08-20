"""الإعدادات المشتركة لكل البيئات.

لا تضع هنا أي سر إنتاجي — الأسرار تأتي من متغيرات البيئة حصرًا.
production.py يعيد فرض المتغيرات الحساسة كمتغيرات إلزامية بلا defaults.
"""

from pathlib import Path

from config.env import env_int, env_list, env_str

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# مفتاح تطوير فقط — production.py يرفض هذا المفتاح ويطلب متغير البيئة إلزاميًا
SECRET_KEY = env_str("DJANGO_SECRET_KEY", "django-insecure-dev-only-key-do-not-use")

DEBUG = False  # كل بيئة تحدد قيمتها صراحةً

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
    "documents",
    "referrals",
    "school_dashboard",
    "audit",
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
    "common.middleware.RequestIDMiddleware",
    "common.middleware.RequestLogMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
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
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env_str("POSTGRES_DB", "xmansx"),
        "USER": env_str("POSTGRES_USER", "xmansx"),
        "PASSWORD": env_str("POSTGRES_PASSWORD", "xmansx-dev"),
        "HOST": env_str("POSTGRES_HOST", "localhost"),
        # Docker publishes PostgreSQL on host port 5433; compose overrides this
        # to 5432 for containers talking to the postgres service directly.
        "PORT": env_int("POSTGRES_PORT", 5433),
        "CONN_MAX_AGE": 60,
    }
}

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

# ---- Static / Media (مفهومان منفصلان؛ Object Storage للمرفقات يأتي لاحقًا) ----
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "mediafiles"

# ---- Redis / Celery (foundation فقط — لا مهام أعمال بعد) ----
REDIS_URL = env_str("REDIS_URL", "redis://localhost:6379/0")
READINESS_CHECK_TIMEOUT_SECONDS = 2

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
        "KEY_PREFIX": "xmansx",
    }
}

# ---- Login rate limiting: (الحد الأقصى، النافذة بالثواني) ----
# قابلة للضبط بالبيئة: التطوير/E2E يرفعها — الإنتاج يبقى على الافتراضي الصارم
LOGIN_RATE_LIMIT_IP = (env_int("LOGIN_RATE_LIMIT_IP_MAX", 20), 300)
LOGIN_RATE_LIMIT_MOBILE = (env_int("LOGIN_RATE_LIMIT_MOBILE_MAX", 5), 300)

# ---- تشفير المعرفات الحساسة (ADR-009) ----
# مفاتيح تطوير فقط — production.py يفرضها من البيئة ويفشل بدونها
FIELD_ENCRYPTION_KEYS = env_list(
    "FIELD_ENCRYPTION_KEYS",
    ["g8_LpA8xmZcbg6EMSduJi5tKU9zdBr0HncpN9zAcFNo="],  # dev-only Fernet key
)
NATIONAL_ID_HMAC_KEY = env_str(
    "NATIONAL_ID_HMAC_KEY", "dev-only-hmac-key-not-for-production"
)

# ---- حدود استيراد الطلاب ----
STUDENT_IMPORT_MAX_FILE_BYTES = 10 * 1024 * 1024      # 10MB
STUDENT_IMPORT_MAX_ROWS = 10_000
STUDENT_IMPORT_MAX_ZIP_ENTRIES = 200
STUDENT_IMPORT_MAX_UNCOMPRESSED_BYTES = 60 * 1024 * 1024  # حماية zip bomb

# ---- مرفقات الأعذار (م10): PDF/JPG/PNG بتخزين خاص ----
EXCUSE_ATTACHMENT_MAX_FILE_BYTES = 10 * 1024 * 1024        # 10MB

# ---- المستندات المولدة (م12): تخزين خاص **خارج** MEDIA_ROOT ----
# ‏MEDIA_ROOT يخدم عبر HTTP في التطوير؛ المستندات الرسمية لا يجوز أن تكون
# قابلة للتنزيل بلا مصادقة — التنزيل عبر endpoint مصرح فقط.
GENERATED_DOCUMENTS_ROOT = env_str(
    "GENERATED_DOCUMENTS_ROOT", str(BASE_DIR / "privatefiles" / "documents")
)

CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_TASK_ALWAYS_EAGER = False
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_TIMEZONE = TIME_ZONE

# ---- DRF ----
REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
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
