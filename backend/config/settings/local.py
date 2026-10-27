"""بيئة التطوير المحلية."""

from config.env import env_list, env_str

from .base import *

DEBUG = True

_replit_dev_domain = env_str("REPLIT_DEV_DOMAIN", "")
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "backend"]
if _replit_dev_domain:
    ALLOWED_HOSTS.append(_replit_dev_domain)

# أصول تطوير إضافية: شجرة عمل موازية تخدم نفس الواجهة على منفذ آخر
# (مثال: DEV_EXTRA_ORIGINS=http://localhost:5273). فارغة افتراضيًا — لا توسيع
# للثقة في التشغيل الاعتيادي، والإنتاج لا يقرأ هذا الملف أصلًا.
_extra_dev_origins = env_list("DEV_EXTRA_ORIGINS", [])
_replit_preview_origins = (
    ["http://localhost:5000", "http://127.0.0.1:5000", f"https://{_replit_dev_domain}"]
    if _replit_dev_domain
    else []
)

# Vite dev server فقط — ممنوع CORS_ALLOW_ALL_ORIGINS
CORS_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    *_extra_dev_origins,
]
CSRF_TRUSTED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    # Vite serves the Replit preview on 5000; the browser sends its HTTPS
    # Origin through the same-origin API proxy even when changeOrigin rewrites Host.
    *_replit_preview_origins,
    *_extra_dev_origins,
]

# وثائق API مفتوحة في التطوير فقط
SPECTACULAR_SETTINGS = {
    **SPECTACULAR_SETTINGS,
    "SERVE_PERMISSIONS": ["rest_framework.permissions.AllowAny"],
}
