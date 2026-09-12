"""تكامل الواجهات بعد دمج م12 وم13 — الخصوصية والعزل عبر الوحدات.

يثبت أن دمج الإحالات **لم يوسّع** صلاحيات المستندات والإجراءات، وأن العزل بين
المستأجرين يشمل الوحدات الأربع معًا (البنود 22-30 و47-51).
"""

import pytest
from django.utils import timezone as dj_timezone

from documents.pdf import pdf_engine_available
from memberships.models import SchoolMembership
from referrals.models import ReferralCategory, ReferralReason
from student_warnings.models import StudentWarning, WarningLevel, WarningRuleType, WarningStatus
from tests.excuse_env import DAY, DAY2, build_env

pytestmark = pytest.mark.django_db

requires_pdf = pytest.mark.skipif(
    not pdf_engine_available(), reason="محرك PDF غير متوفر خارج الحاوية"
)

ACTIONS_URL = "/api/v1/student-actions/"
DOCUMENTS_URL = "/api/v1/documents/"
GENERATE_URL = "/api/v1/documents/generate/"
REFERRALS_URL = "/api/v1/referrals/"


def json_post(client, url, payload):
    return client.post(url, payload, content_type="application/json")


def school_env(make_school, make_user, make_membership, *, prefix, mobile_base):
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
    from schools.models import SchoolSettings

    SchoolSettings.objects.create(school=school, city="الرياض")
    return env


@pytest.fixture
def env(make_school, make_user, make_membership):
    return school_env(
        make_school, make_user, make_membership, prefix="31100", mobile_base="055121000"
    )


def make_warning(env, student) -> StudentWarning:
    return StudentWarning.objects.create(
        school=env["school"], student=student, academic_year=env["year"],
        warning_type=WarningRuleType.UNEXCUSED_FULL_DAY_ABSENCE, level=WarningLevel.LEVEL_2,
        status=WarningStatus.ISSUED, threshold_at_issue=5, metric_value_at_issue=5,
        student_name_snapshot=student.full_name, grade_name_snapshot="الأول الثانوي",
        section_name_snapshot="1", national_id_masked_snapshot=student.national_id_masked,
        unexcused_full_absence_days_at_issue=5,
        issued_by_membership=env["vice"], issued_at=dj_timezone.now(),
    )


@requires_pdf
def test_counselor_with_referral_still_cannot_download_documents(role_client, env):
    """البندان 30 و50: الإحالة لا تمنح صلاحية تنزيل مستند رسمي."""
    student = env["students"][0]
    vice, _, _ = role_client(["VICE_PRINCIPAL"], school=env["school"])
    counselor, _, counselor_user = role_client(["COUNSELOR"], school=env["school"])
    counselor_membership = SchoolMembership.objects.get(
        school=env["school"], user=counselor_user
    )

    document = json_post(
        vice, GENERATE_URL,
        {
            "student_id": student.id, "document_type": "ATTENDANCE_COMMITMENT",
            "from_date": DAY.isoformat(), "to_date": DAY2.isoformat(),
        },
    ).json()
    referral = json_post(
        vice, REFERRALS_URL,
        {
            "student_id": student.id,
            "category": ReferralCategory.ATTENDANCE,
            "reason_code": ReferralReason.REPEATED_ABSENCE,
            "description": "غياب متكرر يستدعي متابعة إرشادية مستمرة.",
            "assigned_counselor_id": counselor_membership.id,
        },
    )
    assert referral.status_code == 201

    # المرشد يرى الإحالة ويقرأ البيانات الوصفية للمستند، ولا ينزّل ولا يرى اللقطة
    assert counselor.get(REFERRALS_URL).status_code == 200
    listing = counselor.get(f"{DOCUMENTS_URL}?student={student.id}").json()
    assert listing["count"] == 1
    assert listing["results"][0]["can_download"] is False
    assert counselor.get(f"{DOCUMENTS_URL}{document['id']}/download/").status_code == 403
    assert "snapshot" not in counselor.get(f"{DOCUMENTS_URL}{document['id']}/").json()


def test_teacher_blocked_from_documents_and_actions_after_merge(role_client, env):
    """البند 26: المعلم يحيل، ولا يقترب من المستندات ولا الإجراءات الإدارية."""
    student = env["students"][0]
    teacher, _, _ = role_client(["TEACHER"], school=env["school"])

    created = json_post(
        teacher, REFERRALS_URL,
        {
            "student_id": student.id,
            "category": ReferralCategory.ACADEMIC,
            "reason_code": ReferralReason.ACADEMIC_WEAKNESS,
            "description": "ضعف دراسي متكرر يحتاج متابعة إرشادية.",
        },
    )
    assert created.status_code == 201
    assert teacher.get(DOCUMENTS_URL).status_code == 403
    assert teacher.get(ACTIONS_URL).status_code == 403
    assert json_post(
        teacher, ACTIONS_URL, {"student_id": student.id, "action_type": "PARENT_CONTACT"}
    ).status_code == 403
    assert json_post(
        teacher, GENERATE_URL,
        {
            "student_id": student.id, "document_type": "ATTENDANCE_COMMITMENT",
            "from_date": DAY.isoformat(), "to_date": DAY2.isoformat(),
        },
    ).status_code == 403


@requires_pdf
def test_cross_school_idor_across_all_four_modules(
    role_client, env, make_school, make_user, make_membership
):
    """البند 47: مدير مدرسة أخرى لا يصل لإجراء/مستند/إحالة/ملاحظة هذه المدرسة."""
    student = env["students"][0]
    vice, _, _ = role_client(["VICE_PRINCIPAL"], school=env["school"])

    action = json_post(
        vice, ACTIONS_URL, {"student_id": student.id, "action_type": "PARENT_CONTACT"}
    ).json()
    document = json_post(
        vice, GENERATE_URL,
        {
            "student_id": student.id, "document_type": "ATTENDANCE_COMMITMENT",
            "from_date": DAY.isoformat(), "to_date": DAY2.isoformat(),
        },
    ).json()
    referral = json_post(
        vice, REFERRALS_URL,
        {
            "student_id": student.id,
            "category": ReferralCategory.ATTENDANCE,
            "reason_code": ReferralReason.REPEATED_ABSENCE,
            "description": "غياب متكرر يستدعي متابعة إرشادية مستمرة.",
        },
    ).json()
    contribution = json_post(
        vice, f"{REFERRALS_URL}{referral['id']}/contributions/",
        {
            "observation_type": "ATTENDANCE_OBSERVATION",
            "notes": "ملاحظة إدارية على الحالة المفتوحة.",
        },
    )
    assert contribution.status_code in (200, 201)

    other = school_env(
        make_school, make_user, make_membership, prefix="31200", mobile_base="055122000"
    )
    foreign_manager, _, _ = role_client(["SCHOOL_MANAGER"], school=other["school"])

    assert foreign_manager.get(f"{ACTIONS_URL}{action['id']}/").status_code == 404
    assert foreign_manager.get(f"{DOCUMENTS_URL}{document['id']}/").status_code == 404
    assert foreign_manager.get(f"{DOCUMENTS_URL}{document['id']}/download/").status_code == 404
    assert foreign_manager.get(f"{REFERRALS_URL}{referral['id']}/").status_code == 404
    assert foreign_manager.get(
        f"{REFERRALS_URL}{referral['id']}/contributions/"
    ).status_code == 404
    # ولا تسرب عبر القوائم
    assert foreign_manager.get(ACTIONS_URL).json()["count"] == 0
    assert foreign_manager.get(DOCUMENTS_URL).json()["count"] == 0
    assert foreign_manager.get(REFERRALS_URL).json()["count"] == 0


def test_admin_referral_action_appears_in_the_actions_tab(role_client, env):
    """البند 72: أثر الإحالة الإداري يظهر ضمن إجراءات ملف الطالب."""
    student = env["students"][0]
    vice, _, _ = role_client(["VICE_PRINCIPAL"], school=env["school"])
    _, _, counselor_user = role_client(["COUNSELOR"], school=env["school"])
    counselor_membership = SchoolMembership.objects.get(
        school=env["school"], user=counselor_user
    )
    json_post(
        vice, REFERRALS_URL,
        {
            "student_id": student.id,
            "category": ReferralCategory.ATTENDANCE,
            "reason_code": ReferralReason.REPEATED_ABSENCE,
            "description": "غياب متكرر يستدعي متابعة إرشادية مستمرة.",
            "assigned_counselor_id": counselor_membership.id,
        },
    )
    rows = vice.get(f"{ACTIONS_URL}?student={student.id}").json()["results"]
    assert [row["action_type"] for row in rows] == ["REFERRED_TO_COUNSELOR"]
    assert rows[0]["action_type_label"] == "إحالة إلى المرشد الطلابي"


def test_multi_role_multi_school_scopes_are_independent(
    role_client, env, make_school, make_user, make_membership
):
    """البند 73: معلم في مدرسة ومرشد في أخرى — لا توارث صلاحيات بين المدرستين."""
    other = school_env(
        make_school, make_user, make_membership, prefix="31300", mobile_base="055123000"
    )
    client, _, user = role_client(["TEACHER"], school=env["school"])
    make_membership(user, other["school"], ["COUNSELOR"])

    # في مدرسة A هو معلم: يحيل ولا يفتح المستندات
    assert json_post(
        client, REFERRALS_URL,
        {
            "student_id": env["students"][0].id,
            "category": ReferralCategory.ACADEMIC,
            "reason_code": ReferralReason.ACADEMIC_WEAKNESS,
            "description": "ضعف دراسي متكرر يحتاج متابعة إرشادية.",
        },
    ).status_code == 201
    assert client.get(DOCUMENTS_URL).status_code == 403

    # وبعد التبديل إلى B هو مرشد: يقرأ البيانات الوصفية ولا ينشئ إحالة
    switched = json_post(
        client, "/api/v1/session/active-school/", {"school_id": other["school"].id}
    )
    assert switched.status_code == 200
    assert client.get(DOCUMENTS_URL).status_code == 200
    assert json_post(
        client, REFERRALS_URL,
        {
            "student_id": other["students"][0].id,
            "category": ReferralCategory.ACADEMIC,
            "reason_code": ReferralReason.ACADEMIC_WEAKNESS,
            "description": "المرشد لا ينشئ إحالة — سياسة م13.",
        },
    ).status_code == 403
