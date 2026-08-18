from django.urls import include, path

from common import errors

urlpatterns = [
    path("api/v1/", include("common.urls")),
]

# أخطاء JSON موحدة بدل صفحات HTML (لا stack traces في الإنتاج)
handler404 = errors.handler404
handler500 = errors.handler500
