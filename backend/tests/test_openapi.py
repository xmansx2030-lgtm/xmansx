"""اختبارات OpenAPI — التوليد ينجح ويشمل الواجهات الأساسية."""

import pytest
from django.test import Client, override_settings


@pytest.mark.django_db
@override_settings(
    SPECTACULAR_SETTINGS={
        "SERVE_PERMISSIONS": ["rest_framework.permissions.AllowAny"],
        "SERVE_INCLUDE_SCHEMA": False,
    }
)
def test_schema_endpoint_generates_successfully(client):
    response = client.get("/api/v1/schema/")
    assert response.status_code == 200
    content = response.content.decode()
    # تغطية الواجهات المطلوبة (البند 2)
    for path in [
        "/api/v1/auth/login/",
        "/api/v1/session/active-school/",
        "/api/v1/school/settings/",
        "/api/v1/school/academic-years/",
        "/api/v1/school/bell-schedules/",
        "/api/v1/students/",
        "/api/v1/student-imports/",
        "/api/v1/staff/",
        "/api/v1/staff-imports/",
        "/api/v1/auth/invitations/",
    ]:
        assert path in content, f"missing path: {path}"


@pytest.mark.django_db
def test_docs_endpoint_available(client):
    # في بيئة الاختبار (ترث base): للمشرفين فقط — anonymous يرفض
    response = client.get("/api/v1/docs/")
    assert response.status_code == 403


@pytest.mark.django_db
@override_settings(
    SPECTACULAR_SETTINGS={
        "SERVE_PERMISSIONS": ["rest_framework.permissions.AllowAny"],
        "SERVE_INCLUDE_SCHEMA": False,
    }
)
def test_docs_endpoint_open_when_allowed():
    response = Client().get("/api/v1/docs/")
    assert response.status_code == 200
