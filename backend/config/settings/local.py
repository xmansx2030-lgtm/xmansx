"""بيئة التطوير المحلية."""

from config.env import env_list

from .base import *

DEBUG = True

ALLOWED_HOSTS = ["localhost", "127.0.0.1", "backend"]

# أصول تطوير إضافية: شجرة عمل موازية تخدم نفس الواجهة على منفذ آخر
# (مثال: DEV_EXTRA_ORIGINS=http://localhost:5273). فارغة افتراضيًا — لا توسيع
# للثقة في التشغيل الاعتيادي، والإنتاج لا يقرأ هذا الملف أصلًا.
_extra_dev_origins = env_list("DEV_EXTRA_ORIGINS", [])

# Vite dev server فقط — ممنوع CORS_ALLOW_ALL_ORIGINS
CORS_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    *_extra_dev_origins,
]
CSRF_TRUSTED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    *_extra_dev_origins,
]

# وثائق API مفتوحة في التطوير فقط
SPECTACULAR_SETTINGS = {
    **SPECTACULAR_SETTINGS,
    "SERVE_PERMISSIONS": ["rest_framework.permissions.AllowAny"],
}
