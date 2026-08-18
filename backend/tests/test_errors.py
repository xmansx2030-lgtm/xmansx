"""اختبارات بنية الأخطاء الموحدة {code, message, details}."""

from django.test import Client


def test_unknown_api_path_returns_unified_json_404():
    response = Client().get("/api/v1/does-not-exist/")
    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "NOT_FOUND"
    assert body["message"] == "المورد المطلوب غير موجود."
    assert body["details"] == {}


def test_method_not_allowed_uses_unified_format():
    response = Client().post("/api/v1/health/")
    assert response.status_code == 405
    body = response.json()
    assert body["code"] == "METHOD_NOT_ALLOWED"
    assert body["message"] == "طريقة الطلب غير مدعومة."


def test_error_responses_contain_no_stack_traces():
    response = Client().get("/api/v1/does-not-exist/")
    text = response.content.decode()
    assert "Traceback" not in text
    assert "django" not in text.lower() or "code" in response.json()
