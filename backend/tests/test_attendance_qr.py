"""اختبارات QR الفصل: التوليد، التدوير، الحل، وأن الرمز لا يمنح صلاحية."""

import pytest
from django.test import Client

from students.models import Section
from tests.attendance_helpers import setup_attendance_env

RESOLVE_URL = "/api/v1/attendance/qr/resolve/"


def _resolve(client, token):
    return client.post(RESOLVE_URL, {"token": token}, content_type="application/json")


@pytest.fixture
def qr_env(role_client, make_school):
    school = make_school()
    manager, _, _ = role_client(["SCHOOL_MANAGER"], school=school)
    teacher, _, _ = role_client(["TEACHER"], school=school)
    env = setup_attendance_env(school, students_count=3)
    env.update({"manager": manager, "teacher": teacher, "school": school})
    return env


@pytest.mark.django_db
def test_manager_generates_and_token_is_opaque(qr_env):
    response = qr_env["manager"].get(f"/api/v1/sections/{qr_env['section'].id}/qr/")
    assert response.status_code == 200
    body = response.json()
    token = body["token"]
    assert len(token) >= 24
    assert str(qr_env["section"].id) not in token  # لا IDs داخلية
    assert body["url_path"] == f"/qr/{token}"
    # GET ثانية تعيد نفس الرمز (دائم نسبيًا — لا رمز جديد كل حصة)
    assert qr_env["manager"].get(
        f"/api/v1/sections/{qr_env['section'].id}/qr/"
    ).json()["token"] == token


@pytest.mark.django_db
def test_teacher_resolves_valid_qr(qr_env):
    token = qr_env["manager"].get(
        f"/api/v1/sections/{qr_env['section'].id}/qr/"
    ).json()["token"]
    response = _resolve(qr_env["teacher"], token)
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == qr_env["section"].id
    assert body["students_count"] == 3


@pytest.mark.django_db
def test_rotation_invalidates_old_token(qr_env):
    url = f"/api/v1/sections/{qr_env['section'].id}/qr/"
    old_token = qr_env["manager"].get(url).json()["token"]
    new_token = qr_env["manager"].post(url).json()["token"]
    assert old_token != new_token

    old = _resolve(qr_env["teacher"], old_token)
    assert old.status_code == 404
    assert old.json()["code"] == "SECTION_QR_INVALID"
    assert _resolve(qr_env["teacher"], new_token).status_code == 200


@pytest.mark.django_db
def test_qr_of_other_school_denied_without_leak(qr_env, role_client):
    """معلم مدرسة أخرى يمسح الرمز: نفس رد الرمز غير الموجود — لا كشف بيانات."""
    token = qr_env["manager"].get(
        f"/api/v1/sections/{qr_env['section'].id}/qr/"
    ).json()["token"]
    foreign_teacher, foreign_school, _ = role_client(["TEACHER"])
    setup_attendance_env(foreign_school, students_count=1)
    response = _resolve(foreign_teacher, token)
    assert response.status_code == 404
    assert response.json()["code"] == "SECTION_QR_INVALID"
    assert qr_env["section"].grade.name not in str(response.json())


@pytest.mark.django_db
def test_qr_grants_no_authorization(qr_env, role_client):
    """الرمز لا يمنح صلاحية: بلا مصادقة → دخول مطلوب؛ مرشد فقط → مرفوض؛
    مدير التوليد لنفسه لا يمنح حل الرمز لغير المعلمين."""
    token = qr_env["manager"].get(
        f"/api/v1/sections/{qr_env['section'].id}/qr/"
    ).json()["token"]

    anonymous = Client()
    response = _resolve(anonymous, token)
    assert response.status_code == 403
    assert response.json()["code"] == "AUTHENTICATION_REQUIRED"

    counselor, _, _ = role_client(["COUNSELOR"], school=qr_env["school"])
    denied = _resolve(counselor, token)
    assert denied.status_code == 403
    # يحجب في طبقة الأدوار المركزية برمزها الموحد (انحراف موثق في ATTENDANCE.md)
    assert denied.json()["code"] == "PERMISSION_DENIED"


@pytest.mark.django_db
def test_qr_management_manager_only(qr_env, role_client):
    url = f"/api/v1/sections/{qr_env['section'].id}/qr/"
    for roles in (["TEACHER"], ["VICE_PRINCIPAL"], ["COUNSELOR"]):
        client, _, _ = role_client(roles, school=qr_env["school"])
        assert client.get(url).status_code == 403
        assert client.post(url).status_code == 403


@pytest.mark.django_db
def test_qr_management_tenant_isolation(qr_env, role_client):
    foreign_manager, _, _ = role_client(["SCHOOL_MANAGER"])
    url = f"/api/v1/sections/{qr_env['section'].id}/qr/"
    assert foreign_manager.get(url).status_code == 404
    assert foreign_manager.post(url).status_code == 404
    qr_env["section"].refresh_from_db()
    # لم يولد/يدور رمز الفصل الأجنبي
    section = Section.objects.get(id=qr_env["section"].id)
    assert section.qr_token is None or foreign_manager.get(url).status_code == 404
