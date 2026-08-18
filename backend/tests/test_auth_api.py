"""اختبارات المصادقة: login/logout/me/csrf + الجلسات + Rate limiting + enumeration."""

import pytest
from django.core.cache import cache
from django.test import Client

from audit.models import AuditAction, AuditLog
from tests.conftest import PASSWORD


@pytest.mark.django_db
def test_csrf_bootstrap_sets_cookie(client):
    response = client.get("/api/v1/auth/csrf/")
    assert response.status_code == 200
    assert "csrftoken" in response.cookies
    assert response.json() == {"detail": "ok"}


@pytest.mark.django_db
def test_login_success_creates_authenticated_session(make_user, login_client):
    make_user("0550000200", first_name="أحمد", last_name="محمد")
    client, response = login_client("0550000200")
    assert response.status_code == 200
    body = response.json()
    assert body["mobile"] == "+966550000200"
    assert body["name"] == "أحمد محمد"
    assert "password" not in str(body)
    # الجلسة أصبحت مصادقة فعلاً
    me = client.get("/api/v1/auth/me/")
    assert me.status_code == 200


@pytest.mark.django_db
def test_login_accepts_any_mobile_format(make_user, client):
    make_user("0550000201")
    response = client.post(
        "/api/v1/auth/login/",
        {"mobile": "00966550000201", "password": PASSWORD},
        content_type="application/json",
    )
    assert response.status_code == 200


@pytest.mark.django_db
def test_login_rotates_session_key(make_user, client):
    """حماية Session Fixation: مفتاح الجلسة يتغير بعد الدخول."""
    make_user("0550000202")
    client.get("/api/v1/auth/csrf/")
    session_before = client.session.session_key
    client.post(
        "/api/v1/auth/login/",
        {"mobile": "0550000202", "password": PASSWORD},
        content_type="application/json",
    )
    assert client.session.session_key != session_before


@pytest.mark.django_db
def test_login_failure_is_generic_no_enumeration(make_user, login_client):
    """نفس الرد لرقم غير موجود وكلمة مرور خاطئة — لا user enumeration."""
    make_user("0550000203")
    _, wrong_password = login_client("0550000203", password="wrong-password")
    _, unknown_mobile = login_client("0550000299")
    assert wrong_password.status_code == unknown_mobile.status_code == 401
    assert wrong_password.json() == unknown_mobile.json()
    assert wrong_password.json()["code"] == "INVALID_CREDENTIALS"


@pytest.mark.django_db
def test_login_invalid_mobile_format_is_validation_error(client):
    response = client.post(
        "/api/v1/auth/login/",
        {"mobile": "12345", "password": "x"},
        content_type="application/json",
    )
    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_ERROR"


@pytest.mark.django_db
def test_login_requires_csrf_token(make_user):
    """CSRF مفروض على login — عميل يفرض الفحص بلا token يرفض بـ 403."""
    make_user("0550000204")
    strict_client = Client(enforce_csrf_checks=True)
    response = strict_client.post(
        "/api/v1/auth/login/",
        {"mobile": "0550000204", "password": PASSWORD},
        content_type="application/json",
    )
    assert response.status_code == 403
    # ومع token صحيح من csrf bootstrap ينجح
    strict_client.get("/api/v1/auth/csrf/")
    token = strict_client.cookies["csrftoken"].value
    response = strict_client.post(
        "/api/v1/auth/login/",
        {"mobile": "0550000204", "password": PASSWORD},
        content_type="application/json",
        headers={"X-CSRFToken": token},
    )
    assert response.status_code == 200


@pytest.mark.django_db
def test_me_requires_authentication(client):
    response = client.get("/api/v1/auth/me/")
    assert response.status_code == 403
    assert response.json()["code"] == "AUTHENTICATION_REQUIRED"


@pytest.mark.django_db
def test_logout_invalidates_session(make_user, login_client):
    make_user("0550000205")
    client, _ = login_client("0550000205")
    assert client.get("/api/v1/auth/me/").status_code == 200
    response = client.post("/api/v1/auth/logout/")
    assert response.status_code == 200
    assert client.get("/api/v1/auth/me/").status_code == 403


@pytest.mark.django_db
def test_me_payload_has_no_sensitive_fields(make_user, login_client):
    make_user("0550000206")
    client, _ = login_client("0550000206")
    body = client.get("/api/v1/auth/me/").json()
    text = str(body)
    assert "password" not in text
    assert "argon2" not in text
    assert "is_superuser" not in body  # نعرض is_platform_admin فقط


@pytest.mark.django_db
def test_audit_events_for_login_logout(make_user, login_client):
    make_user("0550000207")
    client, _ = login_client("0550000207")
    client.post("/api/v1/auth/logout/")
    _, failed = login_client("0550000207", password="wrong")
    actions = list(AuditLog.objects.values_list("action", flat=True))
    assert AuditAction.LOGIN_SUCCESS in actions
    assert AuditAction.LOGOUT in actions
    assert AuditAction.LOGIN_FAILED in actions
    # لا رقم جوال كامل في metadata الفشل
    failed_log = AuditLog.objects.filter(action=AuditAction.LOGIN_FAILED).latest("id")
    assert "+966550000207" not in str(failed_log.metadata)
    assert failed_log.metadata["mobile_masked"].endswith("0207")


class TestLoginRateLimit:
    @pytest.fixture(autouse=True)
    def _clear_cache(self):
        cache.clear()
        yield
        cache.clear()

    @pytest.mark.django_db
    def test_repeated_failures_reach_429(self, make_user, login_client):
        make_user("0550000208")
        limit = 5  # LOGIN_RATE_LIMIT_MOBILE
        for _ in range(limit):
            _, response = login_client("0550000208", password="wrong")
            assert response.status_code == 401
        _, blocked = login_client("0550000208", password="wrong")
        assert blocked.status_code == 429
        assert blocked.json()["code"] == "LOGIN_RATE_LIMITED"
        # حتى كلمة المرور الصحيحة محجوبة أثناء النافذة
        _, still_blocked = login_client("0550000208")
        assert still_blocked.status_code == 429

    @pytest.mark.django_db
    def test_success_resets_mobile_counter(self, make_user, login_client):
        make_user("0550000209")
        for _ in range(3):
            login_client("0550000209", password="wrong")
        _, ok = login_client("0550000209")
        assert ok.status_code == 200
        # بعد النجاح: العداد صفر — 3 محاولات فاشلة جديدة لا تصل للحد
        for _ in range(3):
            _, response = login_client("0550000209", password="wrong")
        assert response.status_code == 401
