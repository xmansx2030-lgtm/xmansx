from django.contrib import admin
from django.urls import include, path

from common import errors

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include("common.urls")),
    path("api/v1/auth/", include("accounts.urls")),
    path("api/v1/session/", include("memberships.urls")),
]

# أخطاء JSON موحدة بدل صفحات HTML (لا stack traces في الإنتاج)
handler404 = errors.handler404
handler500 = errors.handler500
