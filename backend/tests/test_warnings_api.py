"""اختبارات واجهات الإنذارات (م11) — الأدوار، العزل، منع mass assignment، الإلغاء."""

import pytest

from student_warnings.models import (
    StudentWarning,
    WarningLevel,
    WarningRuleType,
    WarningStatus,
)
from tests.excuse_env import build_env
from tests.test_warnings import ABSENCE, absence_days, issue, set_rules


@pytest.fixture
def env(make_school, make_user, make_membership):
    school = make_school()
    return build_env(
        school=school,
        teacher_membership=make_membership(make_user("0550000960"), school, ["TEACHER"]),
        vice_membership=make_membership(
            make_user("0550000961"), school, ["VICE_PRINCIPAL"]
        ),
    )

RULES_URL = "/api/v1/warning-rules/"
ELIGIBILITY_URL = "/api/v1/warnings/eligibility/"
ISSUE_URL = "/api/v1/warnings/issue/"
WARNINGS_URL = "/api/v1/warnings/"


def login(role_client, env, roles):
    """عميل بأدوار محددة داخل نفس مدرسة البيئة."""
    client, _, _ = role_client(roles, school=env["school"])
    return client


# ---------- القواعد (البنود 76-79) ----------


@pytest.mark.django_db
def test_rules_get_and_patch_roles(role_client, env):  # noqa: F811
    manager = login(role_client, env, ["SCHOOL_MANAGER"])
    vice = login(role_client, env, ["VICE_PRINCIPAL"])
    teacher = login(role_client, env, ["TEACHER"])
    counselor = login(role_client, env, ["COUNSELOR"])

    response = manager.get(RULES_URL)
    assert response.status_code == 200
    assert response.json()[ABSENCE]["levels"] == {
        "LEVEL_1": 3, "LEVEL_2": 5, "LEVEL_3": 10
    }
    assert vice.get(RULES_URL).status_code == 200  # الوكيل يقرأ
    assert teacher.get(RULES_URL).status_code == 403
    assert counselor.get(RULES_URL).status_code == 403

    payload = {ABSENCE: {"levels": {"LEVEL_1": 2, "LEVEL_2": 4, "LEVEL_3": 7}}}
    assert manager.patch(
        RULES_URL, payload, content_type="application/json"
    ).status_code == 200
    # الوكيل لا يعدل الإعدادات (قرار MVP الموثق)
    assert vice.patch(
        RULES_URL, payload, content_type="application/json"
    ).status_code == 403
    assert manager.get(RULES_URL).json()[ABSENCE]["levels"]["LEVEL_1"] == 2


@pytest.mark.django_db
def test_rules_patch_validation_errors(role_client, env):  # noqa: F811
    manager = login(role_client, env, ["SCHOOL_MANAGER"])
    response = manager.patch(
        RULES_URL,
        {ABSENCE: {"levels": {"LEVEL_1": 5, "LEVEL_2": 3, "LEVEL_3": 10}}},
        content_type="application/json",
    )
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_WARNING_THRESHOLD_ORDER"
    # القيم لم تتغير — التحديث ذري
    assert manager.get(RULES_URL).json()[ABSENCE]["levels"]["LEVEL_1"] == 3


# ---------- الاستحقاق والإصدار ----------


@pytest.mark.django_db
def test_eligibility_and_issue_flow(role_client, env):  # noqa: F811
    student = env["students"][0]
    set_rules(env, ABSENCE, 3, 5, 10)
    absence_days(env, student, 3)
    vice = login(role_client, env, ["VICE_PRINCIPAL"])

    listing = vice.get(f"{ELIGIBILITY_URL}?warning_type={ABSENCE}").json()
    row = next(r for r in listing["results"] if r["student_id"] == student.id)
    assert row["current_value"] == 3
    assert row["highest_due_level"] == WarningLevel.LEVEL_1
    assert row["issued_levels"] == []
    assert listing["summary"][ABSENCE]["due_students"] == 1

    response = vice.post(
        ISSUE_URL,
        {
            "student_id": student.id,
            "warning_type": ABSENCE,
            "level": WarningLevel.LEVEL_1,
            "notes": "بعد مراجعة السجل",
            # محاولة حقن قيم موثوقة — يجب أن يتجاهلها الخادم تمامًا
            "threshold_at_issue": 99,
            "metric_value_at_issue": 99,
            "school": 999,
            "student_name_snapshot": "اسم مزور",
        },
        content_type="application/json",
    )
    assert response.status_code == 201
    body = response.json()
    assert body["threshold_at_issue"] == 3  # لا 99
    assert body["metric_value_at_issue"] == 3
    assert body["student_name"] == student.full_name  # لا «اسم مزور»
    assert body["level_label"] == "الإنذار الأول"

    warning = StudentWarning.objects.get(id=body["id"])
    assert warning.school_id == env["school"].id
    assert warning.notes == "بعد مراجعة السجل"

    # الاستحقاق يعكس الإصدار
    updated = vice.get(f"{ELIGIBILITY_URL}?warning_type={ABSENCE}&status=all").json()
    row = next(r for r in updated["results"] if r["student_id"] == student.id)
    assert row["issued_levels"] == [WarningLevel.LEVEL_1]


@pytest.mark.django_db
def test_issue_denied_for_teacher_and_counselor(role_client, env):  # noqa: F811
    student = env["students"][0]
    set_rules(env, ABSENCE, 3, 5, 10)
    absence_days(env, student, 3)
    payload = {
        "student_id": student.id, "warning_type": ABSENCE, "level": WarningLevel.LEVEL_1
    }
    for roles in (["TEACHER"], ["COUNSELOR"]):
        client = login(role_client, env, roles)
        assert client.post(
            ISSUE_URL, payload, content_type="application/json"
        ).status_code == 403
        assert client.get(ELIGIBILITY_URL).status_code == 403
    assert not StudentWarning.objects.exists()


@pytest.mark.django_db
def test_double_click_issue_creates_one_warning(role_client, env):  # noqa: F811
    student = env["students"][0]
    set_rules(env, ABSENCE, 3, 5, 10)
    absence_days(env, student, 3)
    vice = login(role_client, env, ["VICE_PRINCIPAL"])
    payload = {
        "student_id": student.id, "warning_type": ABSENCE, "level": WarningLevel.LEVEL_1
    }
    first = vice.post(ISSUE_URL, payload, content_type="application/json")
    second = vice.post(ISSUE_URL, payload, content_type="application/json")
    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["code"] == "WARNING_ALREADY_ISSUED"
    assert StudentWarning.objects.filter(student=student).count() == 1


# ---------- التفاصيل والإلغاء ----------


@pytest.mark.django_db
def test_detail_shows_drift_and_void_is_manager_only(role_client, env):  # noqa: F811
    from tests.test_warnings import approve, excuse_for

    student = env["students"][0]
    set_rules(env, ABSENCE, 3, 5, 10)
    absence_days(env, student, 5)
    warning = issue(env, student, ABSENCE, WarningLevel.LEVEL_2)
    from tests.test_excuses import DAY

    approve(env, excuse_for(env, student, [{"attendance_date": DAY}]))

    manager = login(role_client, env, ["SCHOOL_MANAGER"])
    vice = login(role_client, env, ["VICE_PRINCIPAL"])
    counselor = login(role_client, env, ["COUNSELOR"])

    detail = manager.get(f"{WARNINGS_URL}{warning.id}/").json()
    assert detail["metric_value_at_issue"] == 5  # Snapshot
    assert detail["current_metric_value"] == 4  # بعد اعتماد عذر يوم
    assert detail["metric_drifted"] is True
    assert detail["snapshot"]["unexcused_full_absence_days"] == 5
    # المرشد يقرأ سجل الإنذارات في ملف الطالب
    assert counselor.get(f"{WARNINGS_URL}{warning.id}/").status_code == 200
    assert counselor.get(f"{WARNINGS_URL}?student={student.id}").status_code == 200

    void_url = f"{WARNINGS_URL}{warning.id}/void/"
    body = {"reason": "صدر بالخطأ"}
    assert vice.post(void_url, body, content_type="application/json").status_code == 403
    assert counselor.post(void_url, body, content_type="application/json").status_code == 403
    response = manager.post(void_url, body, content_type="application/json")
    assert response.status_code == 200
    assert response.json()["status"] == WarningStatus.VOIDED
    # الإلغاء مرتين مرفوض
    assert manager.post(
        void_url, body, content_type="application/json"
    ).json()["code"] == "WARNING_ALREADY_VOIDED"


# ---------- العزل بين المدارس (البنود 123-124) ----------


@pytest.mark.django_db
def test_tenant_isolation(role_client, env):  # noqa: F811
    student = env["students"][0]
    set_rules(env, ABSENCE, 3, 5, 10)
    absence_days(env, student, 3)
    warning = issue(env, student, ABSENCE, WarningLevel.LEVEL_1)

    foreign, foreign_school, _ = role_client(["SCHOOL_MANAGER"])  # مدرسة أخرى
    from academics.models import AcademicYear, AcademicYearStatus

    AcademicYear.objects.create(
        school=foreign_school, name="ع", start_date=env["year"].start_date,
        end_date=env["year"].end_date, status=AcademicYearStatus.ACTIVE,
    )

    # قواعد المدرسة الأخرى مستقلة تمامًا
    assert foreign.get(RULES_URL).json()[ABSENCE]["levels"]["LEVEL_1"] == 3
    # لا يرى إنذار/طالب المدرسة الأولى
    assert foreign.get(f"{WARNINGS_URL}{warning.id}/").status_code == 404
    assert foreign.post(
        f"{WARNINGS_URL}{warning.id}/void/", {"reason": "x"},
        content_type="application/json",
    ).status_code == 404
    assert foreign.get(WARNINGS_URL).json()["count"] == 0
    assert foreign.get(ELIGIBILITY_URL).json()["results"] == []
    assert foreign.post(
        ISSUE_URL,
        {"student_id": student.id, "warning_type": ABSENCE, "level": WarningLevel.LEVEL_1},
        content_type="application/json",
    ).status_code == 404


@pytest.mark.django_db
def test_multi_school_role_scope(make_user, make_school, make_membership, login_client, env):  # noqa: F811
    """مدير في A ومعلم في B: يعمل في A ويرفض في B (البند 80)."""
    from academics.models import AcademicYear, AcademicYearStatus

    user = make_user("0550000950")
    other = make_school("مدرسة ب")
    make_membership(user, env["school"], ["SCHOOL_MANAGER"])
    make_membership(user, other, ["TEACHER"])
    AcademicYear.objects.create(
        school=other, name="ع", start_date=env["year"].start_date,
        end_date=env["year"].end_date, status=AcademicYearStatus.ACTIVE,
    )
    client, _ = login_client("0550000950")

    client.post(
        "/api/v1/session/active-school/", {"school_id": env["school"].id},
        content_type="application/json",
    )
    assert client.get(RULES_URL).status_code == 200

    client.post(
        "/api/v1/session/active-school/", {"school_id": other.id},
        content_type="application/json",
    )
    assert client.get(RULES_URL).status_code == 403
    assert client.get(ELIGIBILITY_URL).status_code == 403


@pytest.mark.django_db
def test_warning_list_filters_and_no_national_id(role_client, env):  # noqa: F811
    student = env["students"][0]
    set_rules(env, ABSENCE, 3, 5, 10)
    absence_days(env, student, 3)
    issue(env, student, ABSENCE, WarningLevel.LEVEL_1)
    manager = login(role_client, env, ["SCHOOL_MANAGER"])

    body = manager.get(f"{WARNINGS_URL}?student={student.id}")
    assert body.status_code == 200
    payload = body.json()
    assert payload["count"] == 1
    assert payload["results"][0]["warning_type"] == ABSENCE
    # لا رقم هوية كامل في قائمة الإنذارات
    assert "national_id" not in body.content.decode()
    assert manager.get(
        f"{WARNINGS_URL}?warning_type={WarningRuleType.MORNING_LATE_OCCURRENCES}"
    ).json()["count"] == 0
