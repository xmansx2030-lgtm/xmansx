"""اختبارات إعدادات المدرسة: الصلاحيات، الحدود، mass assignment، تعدد المدارس."""

import pytest

from audit.models import AuditLog

URL = "/api/v1/school/settings/"


@pytest.mark.django_db
def test_get_settings_creates_defaults(role_client):
    client, school, _ = role_client(["SCHOOL_MANAGER"])
    response = client.get(URL)
    assert response.status_code == 200
    body = response.json()
    assert body["school"]["name"] == school.name
    assert body["attendance_edit_window_minutes"] == 15
    assert body["unprepared_period_alert_minutes"] == 25
    assert body["timezone"] == "Asia/Riyadh"
    assert body["staff"]["managers"]  # المدير الحالي يظهر من العضويات


@pytest.mark.django_db
def test_manager_can_patch_settings_with_audit(role_client):
    client, school, _ = role_client(["SCHOOL_MANAGER"])
    response = client.patch(
        URL,
        {
            "name": "ثانوية النور",
            "city": "الرياض",
            "ministry_school_number": "12345",
            "education_stage": "SECONDARY",
            "attendance_edit_window_minutes": 20,
            "unprepared_period_alert_minutes": 30,
        },
        content_type="application/json",
    )
    assert response.status_code == 200
    body = response.json()
    assert body["school"]["name"] == "ثانوية النور"
    assert body["city"] == "الرياض"
    assert body["attendance_edit_window_minutes"] == 20

    actions = set(AuditLog.objects.values_list("action", flat=True))
    assert "SCHOOL_NAME_UPDATED" in actions
    assert "SCHOOL_SETTINGS_UPDATED" in actions
    log = AuditLog.objects.get(action="SCHOOL_SETTINGS_UPDATED")
    assert "city" in log.metadata["changed"]


@pytest.mark.django_db
def test_vice_principal_reads_but_cannot_write(role_client):
    client, _, _ = role_client(["VICE_PRINCIPAL"])
    assert client.get(URL).status_code == 200
    response = client.patch(URL, {"city": "جدة"}, content_type="application/json")
    assert response.status_code == 403
    assert response.json()["code"] == "PERMISSION_DENIED"


@pytest.mark.django_db
def test_counselor_reads_but_cannot_write(role_client):
    client, _, _ = role_client(["COUNSELOR"])
    assert client.get(URL).status_code == 200
    assert client.patch(URL, {"city": "x"}, content_type="application/json").status_code == 403


@pytest.mark.django_db
def test_teacher_denied_settings_entirely(role_client):
    client, _, _ = role_client(["TEACHER"])
    assert client.get(URL).status_code == 403
    assert client.patch(URL, {"city": "x"}, content_type="application/json").status_code == 403


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("field", "value", "ok"),
    [
        ("unprepared_period_alert_minutes", 0, False),
        ("unprepared_period_alert_minutes", 1, True),
        ("unprepared_period_alert_minutes", 25, True),
        ("unprepared_period_alert_minutes", 120, True),
        ("unprepared_period_alert_minutes", 121, False),
        ("unprepared_period_alert_minutes", -5, False),
        ("attendance_edit_window_minutes", 0, True),
        ("attendance_edit_window_minutes", 120, True),
        ("attendance_edit_window_minutes", 121, False),
        ("attendance_edit_window_minutes", -1, False),
    ],
)
def test_minutes_boundary_values(role_client, field, value, ok):
    client, _, _ = role_client(["SCHOOL_MANAGER"])
    response = client.patch(URL, {field: value}, content_type="application/json")
    assert (response.status_code == 200) is ok


@pytest.mark.django_db
def test_invalid_timezone_rejected(role_client):
    client, _, _ = role_client(["SCHOOL_MANAGER"])
    response = client.patch(URL, {"timezone": "Mars/Olympus"}, content_type="application/json")
    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_ERROR"


@pytest.mark.django_db
def test_empty_school_name_rejected(role_client):
    client, _, _ = role_client(["SCHOOL_MANAGER"])
    response = client.patch(URL, {"name": "   "}, content_type="application/json")
    assert response.status_code == 400


@pytest.mark.django_db
def test_mass_assignment_school_and_status_ignored(role_client, make_school):
    """حقول school/status/slug لا يقبلها الـ API — منع mass assignment."""
    client, school, _ = role_client(["SCHOOL_MANAGER"])
    other = make_school("أخرى")
    response = client.patch(
        URL,
        {"school": other.id, "school_id": other.id, "status": "SUSPENDED", "slug": "hacked"},
        content_type="application/json",
    )
    assert response.status_code == 200
    school.refresh_from_db()
    assert school.status == "ACTIVE"
    assert school.slug != "hacked"
    assert response.json()["school"]["id"] == school.id


@pytest.mark.django_db
def test_multi_school_manager_scope(make_user, make_school, make_membership, login_client):
    """مدير في A ومعلم في B: الكتابة تعمل في A فقط — اختبار إلزامي (البند 52)."""
    user = make_user("0550000700")
    a, b = make_school("مدرسة أ"), make_school("مدرسة ب")
    make_membership(user, a, ["SCHOOL_MANAGER"])
    make_membership(user, b, ["TEACHER"])
    client, _ = login_client("0550000700")

    switch = client.post(
        "/api/v1/session/active-school/", {"school_id": a.id}, content_type="application/json"
    )
    assert switch.status_code == 200
    assert client.patch(URL, {"city": "الرياض"}, content_type="application/json").status_code == 200

    client.post(
        "/api/v1/session/active-school/", {"school_id": b.id}, content_type="application/json"
    )
    assert client.get(URL).status_code == 403  # معلم في B: لا وصول للإعدادات
    response = client.patch(URL, {"city": "اختراق"}, content_type="application/json")
    assert response.status_code == 403

    # ولم تتأثر بيانات B
    from schools.models import SchoolSettings

    assert not SchoolSettings.objects.filter(school=b, city="اختراق").exists()


@pytest.mark.django_db
def test_settings_query_count_is_bounded(role_client, django_assert_max_num_queries):
    client, _, _ = role_client(["SCHOOL_MANAGER"])
    client.get(URL)  # الأولى تنشئ الإعدادات
    with django_assert_max_num_queries(8):
        response = client.get(URL)
    assert response.status_code == 200
