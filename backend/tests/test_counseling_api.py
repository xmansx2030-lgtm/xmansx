"""اختبارات واجهات الإرشاد (م14) — الأدوار وخصوصية المعلم والعزل وmass assignment."""

import pytest

from counseling.models import CaseStatus, CounselorCase
from referrals.models import ReferralCategory, ReferralReason
from tests.excuse_env import build_env

pytestmark = pytest.mark.django_db

DASHBOARD = "/api/v1/counselor/dashboard/"
CASES = "/api/v1/counselor/cases/"
REFERRALS = "/api/v1/referrals/"
TEACHER_REQUESTS = "/api/v1/teacher/follow-up-requests/"


def json_post(client, url, payload=None):
    return client.post(url, payload or {}, content_type="application/json")


def build_school(make_school, make_user, make_membership, *, prefix, mobile_base):
    school = make_school()
    env = build_env(
        school=school,
        teacher_membership=make_membership(
            make_user(f"{mobile_base}1"), school, ["TEACHER"]
        ),
        vice_membership=make_membership(
            make_user(f"{mobile_base}2"), school, ["VICE_PRINCIPAL"]
        ),
        prefix=prefix,
    )
    return env


@pytest.fixture
def env(role_client, make_school, make_user, make_membership):
    """مدرسة كاملة الأدوار مع عملاء جاهزين لكل دور."""
    counselor_client, school, counselor_user = role_client(["COUNSELOR"])
    environment = build_env(
        school=school,
        teacher_membership=make_membership(make_user("0551410001"), school, ["TEACHER"]),
        vice_membership=make_membership(make_user("0551410002"), school, ["VICE_PRINCIPAL"]),
        prefix="32100",
    )
    environment["counselor_client"] = counselor_client
    environment["counselor"] = counselor_user.memberships.get(school=school)

    manager_client, _, _ = role_client(["SCHOOL_MANAGER"], school=school)
    environment["manager_client"] = manager_client
    vice_client, _, _ = role_client(["VICE_PRINCIPAL"], school=school)
    environment["vice_client"] = vice_client
    teacher_client, _, teacher_user = role_client(["TEACHER"], school=school)
    environment["teacher_client"] = teacher_client
    environment["teacher_membership"] = teacher_user.memberships.get(school=school)
    teacher2_client, _, teacher2_user = role_client(["TEACHER"], school=school)
    environment["teacher2_client"] = teacher2_client
    environment["teacher2_membership"] = teacher2_user.memberships.get(school=school)
    counselor2_client, _, counselor2_user = role_client(["COUNSELOR"], school=school)
    environment["counselor2_client"] = counselor2_client
    environment["counselor2"] = counselor2_user.memberships.get(school=school)
    return environment


def make_case(env, *, student=None, counselor=None) -> int:
    """إحالة من الوكيل ← استلام المرشد ← فتح الملف، عبر الواجهات."""
    student = student or env["students"][0]
    counselor = counselor or env["counselor"]
    created = json_post(
        env["vice_client"],
        REFERRALS,
        {
            "student_id": student.id,
            "category": ReferralCategory.ATTENDANCE,
            "reason_code": ReferralReason.REPEATED_ABSENCE,
            "description": "غياب متكرر يحتاج متابعة إرشادية مستمرة.",
            "assigned_counselor_id": counselor.id,
        },
    )
    assert created.status_code == 201, created.content
    referral_id = created.json()["id"]
    client = (
        env["counselor_client"] if counselor is env["counselor"] else env["counselor2_client"]
    )
    assert json_post(client, f"{REFERRALS}{referral_id}/acknowledge/").status_code == 200
    opened = json_post(client, f"{REFERRALS}{referral_id}/open-case/")
    assert opened.status_code == 201, opened.content
    return opened.json()["id"]


# ---------------------------------------------------------------- الأدوار


def test_case_visibility_by_role(env):
    case_id = make_case(env)

    # المرشد صاحب الحالة والمدير والوكيل يرونها
    assert env["counselor_client"].get(f"{CASES}{case_id}/").status_code == 200
    assert env["manager_client"].get(f"{CASES}{case_id}/").status_code == 200
    assert env["vice_client"].get(f"{CASES}{case_id}/").status_code == 200
    # مرشد آخر لا يراها إطلاقًا (البند 97)
    assert env["counselor2_client"].get(f"{CASES}{case_id}/").status_code == 404
    assert env["counselor2_client"].get(CASES).json()["count"] == 0
    # المعلم محجوب عن كل مسارات الحالات (البند 78)
    assert env["teacher_client"].get(CASES).status_code == 403
    assert env["teacher_client"].get(f"{CASES}{case_id}/").status_code == 403
    assert env["teacher_client"].get(DASHBOARD).status_code == 403


def test_vice_principal_reads_but_does_not_write(env):
    """البند 73: الوكيل يتابع ولا يعدل محتوى الإرشاد."""
    case_id = make_case(env)
    assert env["vice_client"].get(f"{CASES}{case_id}/").status_code == 200
    assert env["vice_client"].get(f"{CASES}{case_id}/sessions/").status_code == 200
    assert json_post(
        env["vice_client"],
        f"{CASES}{case_id}/sessions/",
        {"session_type": "STUDENT_MEETING", "summary": "محاولة"},
    ).status_code == 403
    assert json_post(
        env["vice_client"], f"{CASES}{case_id}/status/", {"status": "UNDER_ASSESSMENT"}
    ).status_code == 403


def test_other_counselor_cannot_write_into_the_case(env):
    case_id = make_case(env)
    assert json_post(
        env["counselor2_client"],
        f"{CASES}{case_id}/sessions/",
        {"session_type": "STUDENT_MEETING", "summary": "محاولة"},
    ).status_code == 404  # لا يراها أصلًا


# ---------------------------------------------------------------- الملف والمسار


def test_case_detail_separates_opening_snapshot_from_current(env):
    case_id = make_case(env)
    body = env["counselor_client"].get(f"{CASES}{case_id}/").json()
    assert "snapshot_at_opening" in body and "current_metrics" in body
    assert body["referral"]["snapshot_at_referral"] is not None
    assert body["can_manage"] is True
    # لا رقم هوية في أي لقطة (البند 17)
    assert "national_id" not in str(body["snapshot_at_opening"])


def test_full_workflow_through_the_api(env):
    case_id = make_case(env)
    client = env["counselor_client"]

    assert json_post(
        client,
        f"{CASES}{case_id}/sessions/",
        {
            "session_type": "STUDENT_MEETING",
            "summary": "مقابلة أولى مع الطالب.",
            "observations": "متعاون",
            "outcome": "اتفقنا على خطة",
        },
    ).status_code == 201

    plan = json_post(
        client,
        f"{CASES}{case_id}/plans/",
        {"title": "خطة الحضور", "start_date": "2026-08-01", "activate": True},
    )
    assert plan.status_code == 201
    plan_id = plan.json()["id"]
    assert plan.json()["status"] == "ACTIVE"

    goal = json_post(
        client,
        f"/api/v1/counselor/plans/{plan_id}/goals/",
        {
            "goal_type": "MORNING_LATENESS",
            "title": "خفض التأخر الصباحي",
            "baseline_value": 6,
            "target_value": 1,
            "unit": "مرات",
        },
    )
    assert goal.status_code == 201
    activity = json_post(
        client,
        f"/api/v1/counselor/plans/{plan_id}/activities/",
        {"activity_type": "STUDENT_CHECK_IN", "title": "متابعة أسبوعية", "due_date": "2026-08-10"},
    )
    assert activity.status_code == 201
    assert json_post(
        client, f"/api/v1/counselor/activities/{activity.json()['id']}/complete/"
    ).json()["status"] == "COMPLETED"

    assert json_post(
        client, f"{CASES}{case_id}/status/", {"status": "FOLLOW_UP_ACTIVE"}
    ).status_code == 200
    timeline = client.get(f"{CASES}{case_id}/timeline/").json()
    types = {event["event_type"] for event in timeline}
    assert {"CASE_OPENED", "SESSION_ADDED", "PLAN_CREATED", "ACTIVITY_COMPLETED",
            "STATUS_CHANGED"} <= types


def test_close_requires_reason_then_reopen(env):
    case_id = make_case(env)
    client = env["counselor_client"]
    assert json_post(client, f"{CASES}{case_id}/close/", {}).status_code == 400
    closed = json_post(
        client,
        f"{CASES}{case_id}/close/",
        {"closure_reason": "IMPROVED", "improvement_status": "IMPROVED"},
    )
    assert closed.status_code == 200 and closed.json()["status"] == CaseStatus.CLOSED
    assert json_post(client, f"{CASES}{case_id}/reopen/", {}).status_code == 400
    reopened = json_post(client, f"{CASES}{case_id}/reopen/", {"reason": "عاد الغياب"})
    assert reopened.status_code == 200 and reopened.json()["status"] == CaseStatus.OPEN


def test_client_cannot_inject_trusted_fields(env):
    """البند 101: school/opened_by/assigned_counselor لا تُقبل من العميل."""
    case_id = make_case(env)
    response = json_post(
        env["counselor_client"],
        f"{CASES}{case_id}/sessions/",
        {
            "session_type": "STUDENT_MEETING",
            "summary": "جلسة",
            "created_by_membership": env["counselor2"].id,
            "school": 999,
            "case": 999,
            "status": "VOIDED",
        },
    )
    assert response.status_code == 201
    case = CounselorCase.objects.get(id=case_id)
    session = case.sessions.get()
    assert session.created_by_membership_id == env["counselor"].id
    assert session.school_id == case.school_id
    assert session.status == "RECORDED"


# ---------------------------------------------------------------- خصوصية المعلم


def test_teacher_sees_only_own_request_without_case_content(env):
    case_id = make_case(env)
    created = json_post(
        env["counselor_client"],
        f"{CASES}{case_id}/teacher-requests/",
        {
            "teacher_membership_id": env["teacher_membership"].id,
            "request_type": "CLASSROOM_BEHAVIOR",
            "question": "كيف كان تفاعله هذا الأسبوع؟",
        },
    )
    assert created.status_code == 201
    request_id = created.json()["id"]

    inbox = env["teacher_client"].get(TEACHER_REQUESTS).json()
    assert len(inbox) == 1
    row = inbox[0]
    assert row["question"].startswith("كيف")
    assert row["student_name"]
    # لا محتوى إرشادي في صندوق المعلم (البند 71)
    for forbidden in ("case_id", "sessions", "snapshot", "summary", "counselor_notes"):
        assert forbidden not in row

    # معلم آخر لا يرى الطلب ولا يرد عليه (البندان 98-99)
    assert env["teacher2_client"].get(TEACHER_REQUESTS).json() == []
    assert json_post(
        env["teacher2_client"],
        f"{TEACHER_REQUESTS}{request_id}/respond/",
        {"observation": "محاولة", "improvement_status": "IMPROVED"},
    ).status_code == 404

    answered = json_post(
        env["teacher_client"],
        f"{TEACHER_REQUESTS}{request_id}/respond/",
        {"observation": "تحسن ملحوظ في الالتزام.", "improvement_status": "IMPROVED"},
    )
    assert answered.status_code == 201
    # الرد ثابت: محاولة ثانية مرفوضة (البند 127)
    assert json_post(
        env["teacher_client"],
        f"{TEACHER_REQUESTS}{request_id}/respond/",
        {"observation": "تعديل", "improvement_status": "WORSE"},
    ).status_code == 409

    # والمرشد يرى الرد داخل حالته
    requests = env["counselor_client"].get(f"{CASES}{case_id}/teacher-requests/").json()
    assert requests[0]["response"]["improvement_status"] == "IMPROVED"


def test_teacher_cannot_reach_case_endpoints_by_id(env):
    """البند 98: معرف الحالة ليس بابًا لاستكشاف بيانات الطلاب."""
    case_id = make_case(env)
    teacher = env["teacher_client"]
    for url in (
        f"{CASES}{case_id}/",
        f"{CASES}{case_id}/sessions/",
        f"{CASES}{case_id}/plans/",
        f"{CASES}{case_id}/timeline/",
        f"{CASES}{case_id}/teacher-requests/",
    ):
        assert teacher.get(url).status_code == 403, url
    assert env["teacher_client"].get(
        f"/api/v1/students/{env['students'][0].id}/counseling/"
    ).status_code == 403


# ---------------------------------------------------------------- العزل


def test_cross_school_isolation(
    env, role_client, make_school, make_user, make_membership
):
    case_id = make_case(env)
    other = build_school(
        make_school, make_user, make_membership, prefix="32200", mobile_base="055142000"
    )
    foreign_manager, _, _ = role_client(["SCHOOL_MANAGER"], school=other["school"])
    foreign_counselor, _, _ = role_client(["COUNSELOR"], school=other["school"])

    assert foreign_manager.get(f"{CASES}{case_id}/").status_code == 404
    assert foreign_counselor.get(f"{CASES}{case_id}/").status_code == 404
    assert foreign_manager.get(CASES).json()["count"] == 0
    assert json_post(
        foreign_counselor,
        f"{CASES}{case_id}/sessions/",
        {"session_type": "STUDENT_MEETING", "summary": "اختراق"},
    ).status_code == 404
    assert foreign_manager.get(
        f"/api/v1/students/{env['students'][0].id}/counseling/"
    ).status_code == 404


def test_multi_role_multi_school_no_leakage(
    env, role_client, make_school, make_user, make_membership
):
    """البند 131: معلم في A ومرشد في B — كل دور في مدرسته فقط."""
    case_id = make_case(env)
    other = build_school(
        make_school, make_user, make_membership, prefix="32300", mobile_base="055143000"
    )
    client, _, user = role_client(["TEACHER"], school=env["school"])
    make_membership(user, other["school"], ["COUNSELOR"])

    # في A هو معلم: لا حالات، وصندوق طلبات فقط
    assert client.get(CASES).status_code == 403
    assert client.get(TEACHER_REQUESTS).status_code == 200

    switched = json_post(
        client, "/api/v1/session/active-school/", {"school_id": other["school"].id}
    )
    assert switched.status_code == 200
    # في B هو مرشد: لوحة وحالات (فارغة) — ولا يرى حالة مدرسة A
    assert client.get(DASHBOARD).status_code == 200
    assert client.get(CASES).json()["count"] == 0
    assert client.get(f"{CASES}{case_id}/").status_code == 404
    assert client.get(TEACHER_REQUESTS).status_code == 403


def test_student_profile_counseling_summary_roles(env):
    case_id = make_case(env)
    url = f"/api/v1/students/{env['students'][0].id}/counseling/"
    manager = env["manager_client"].get(url).json()
    assert manager["open_cases"] == 1
    assert manager["cases"][0]["id"] == case_id
    # المرشد صاحب الحالة يراها؛ زميله لا يراها في الملخص كذلك
    assert env["counselor_client"].get(url).json()["total_cases"] == 1
    assert env["counselor2_client"].get(url).json()["total_cases"] == 0
    # ولا نص إرشادي في الملخص
    assert "summary" not in manager["cases"][0]


def test_dashboard_kpis_shape(env):
    make_case(env)
    body = env["counselor_client"].get(DASHBOARD).json()
    assert set(body) == {
        "new_referrals", "open_cases", "under_assessment", "follow_up_active",
        "resolved", "waiting_teacher_response", "due_activities", "closed_this_month",
    }
    assert body["open_cases"] == 1


def test_case_list_filters_and_sorting(env):
    make_case(env)
    client = env["counselor_client"]
    assert client.get(f"{CASES}?status=live").json()["count"] == 1
    assert client.get(f"{CASES}?status=CLOSED").json()["count"] == 0
    assert client.get(f"{CASES}?category=ATTENDANCE").json()["count"] == 1
    assert client.get(f"{CASES}?category=ACADEMIC").json()["count"] == 0
    assert client.get(f"{CASES}?sort=oldest_unattended").status_code == 200
    row = client.get(CASES).json()["results"][0]
    assert row["student_name"] and row["referral_category_label"] == "المواظبة"
