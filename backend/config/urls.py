from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from common import errors


class _DynamicServePermissionsMixin:
    """يقرأ SERVE_PERMISSIONS وقت الطلب (لا وقت الاستيراد) — يضمن تطبيق إعداد البيئة."""

    def get_permissions(self):
        from django.utils.module_loading import import_string

        declared = settings.SPECTACULAR_SETTINGS.get(
            "SERVE_PERMISSIONS", ["rest_framework.permissions.IsAdminUser"]
        )
        return [
            (import_string(p) if isinstance(p, str) else p)() for p in declared
        ]


class SchemaView(_DynamicServePermissionsMixin, SpectacularAPIView):
    pass


class DocsView(_DynamicServePermissionsMixin, SpectacularSwaggerView):
    pass

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include("common.urls")),
    path("api/v1/auth/", include("accounts.urls")),
    path("api/v1/session/", include("memberships.urls")),
    path("api/v1/school/", include("schools.urls")),
    path("api/v1/school/", include("academics.urls")),
    path("api/v1/", include("students.urls")),
    path("api/v1/", include("staff.urls")),
    path("api/v1/schema/", SchemaView.as_view(), name="schema"),
    path("api/v1/docs/", DocsView.as_view(url_name="schema"), name="docs"),
]

# Media للتطوير فقط (شعارات المدارس) — الإنتاج عبر Object Storage لاحقًا
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# أخطاء JSON موحدة بدل صفحات HTML (لا stack traces في الإنتاج)
handler404 = errors.handler404
handler500 = errors.handler500
