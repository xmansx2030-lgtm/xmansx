from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from common import errors

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include("common.urls")),
    path("api/v1/auth/", include("accounts.urls")),
    path("api/v1/session/", include("memberships.urls")),
    path("api/v1/school/", include("schools.urls")),
    path("api/v1/school/", include("academics.urls")),
    path("api/v1/", include("students.urls")),
]

# Media للتطوير فقط (شعارات المدارس) — الإنتاج عبر Object Storage لاحقًا
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# أخطاء JSON موحدة بدل صفحات HTML (لا stack traces في الإنتاج)
handler404 = errors.handler404
handler500 = errors.handler500
