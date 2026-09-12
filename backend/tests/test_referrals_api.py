"""اختبارات API الإحالات (م13): سير العمل، الصلاحيات، خصوصية المعلم، العزل/IDOR."""

import pytest

from audit.models import AuditAction, AuditLog
from referrals.models import ReferralCategory, ReferralReason, StudentReferral
from tests.attendance_helpers import make_students

BASE = "/api/v1/referrals/"


def build_school_env(school, make_user, make_membership, prefix="60100", tag="1"):
    """صف/فصل + طالبان + عضويات كل الأدوار داخل المدرسة المعطاة."""
    from academics.models import AcademicYear, AcademicYearStatus
    from students.models import Grade, Section

    year = AcademicYear.objects.create(
        school=school, name="2026/2027", start_date="2026-08-01",
        end_date="2027-06-25", status=AcademicYearStatus.ACTIVE,
    )
    grade = Grade.objects.create(school=school, name="الأول الثانوي", code="G1", sequence=1)
    section = Section.objects.create(school=school, grade=grade, code="1", name="1")
    students = make_students(school, section, year, 2, prefix=prefix)
    return {
        "school": school,
        "grade": grade,
        "section": section,
        "students": students,
        # جوال فريد لكل مدرسة اختبار (10 أرقام) — tag رقم واحد
        "counselor": make_membership(
            make_user(f"05514{tag}0005"), school, ["COUNSELOR"]
        ),
    }


@pytest.fixture
def api_env(role_client, make_user, make_membership):
    """عميل وكيل + بيئة مدرسة + عملاء بقية الأدوار في نفس المدرسة."""
    vice_client, school, vice_user = role_client(["VICE_PRINCIPAL"])
    env = build_school_env(school, make_user, make_membership)
    env["vice_client"] = vice_client
    env["vice"] = vice_user.memberships.get(school=school)
    from staff.models import VicePrincipalScopeAssignment

    VicePrincipalScopeAssignment.objects.create(
        school=school,
        grade=env["grade"],
        vice_principal_membership=env["vice"],
    )

    teacher_client, _, teacher_user = role_client(["TEACHER"], school=school)
    env["teacher_client"] = teacher_client
    env["teacher"] = teacher_user.memberships.get(school=school)

    counselor_client, _, counselor_user = role_client(["COUNSELOR"], school=school)
    env["counselor_client"] = counselor_client
    env["counselor_membership"] = counselor_user.memberships.get(school=school)

    manager_client, _, manager_user = role_client(["SCHOOL_MANAGER"], school=school)
    env["manager_client"] = manager_client
    env["manager"] = manager_user.memberships.get(school=school)
    return env


def create_referral(client, student_id, **overrides):
    payload = {
        "student_id": student_id,
        "category": ReferralCategory.ACADEMIC,
        "reason_code": ReferralReason.ACADEMIC_WEAKNESS,
        "description": "ضعف واضح في حل المسائل خلال الأسبوعين الماضيين.",
    }
    payload.update(overrides)
    return client.post(BASE, payload, content_type="application/json")


# ---------- سير العمل الكامل ----------


@pytest.mark.django_db
def test_teacher_creates_and_counselor_acknowledges(api_env):
    student = api_env["students"][0]
    created = create_referral(api_env["teacher_client"], student.id)
    assert created.status_code == 201, created.content
    body = created.json()
    assert body["status"] == "PENDING_VICE"
    assert body["source_type"] == "TEACHER"
    assert body["assigned_vice_principal_id"] == api_env["vice"].id
    assert body["assigned_counselor_id"] is None
    referral_id = body["id"]

    # الوكيل يعيّن المرشد
    assigned = api_env["vice_client"].post(
        f"{BASE}{referral_id}/assign/",
        {"counselor_membership_id": api_env["counselor_membership"].id},
        content_type="application/json",
    )
    assert assigned.status_code == 200
    assert assigned.json()["assigned_counselor_id"] == api_env["counselor_membership"].id

    # المرشد يستلم
    acknowledged = api_env["counselor_client"].post(f"{BASE}{referral_id}/acknowledge/")
    assert acknowledged.status_code == 200
    assert acknowledged.json()["status"] == "ACKNOWLEDGED"
    assert acknowledged.json()["accepted_at"] is not None

    events = [e["event_type"] for e in acknowledged.json()["events"]]
    assert events == [
        "CREATED",
        "ROUTED_TO_VICE",
        "FORWARDED_TO_COUNSELOR",
        "ACKNOWLEDGED",
    ]
    assert AuditLog.objects.filter(action=AuditAction.REFERRAL_CREATED).exists()
    assert AuditLog.objects.filter(action=AuditAction.REFERRAL_ACKNOWLEDGED).exists()


@pytest.mark.django_db
def test_duplicate_returns_409_with_existing_case(api_env):
    student = api_env["students"][0]
    first = create_referral(api_env["teacher_client"], student.id).json()

    duplicate = create_referral(api_env["vice_client"], student.id)
    assert duplicate.status_code == 409
    body = duplicate.json()
    assert body["code"] == "DUPLICATE_OPEN_REFERRAL"
    assert body["details"]["existing_referral_id"] == first["id"]
    assert body["details"]["recommended_action"] == "ADD_CONTRIBUTION"

    # الإجراء الموصى به: ملاحظة على الحالة القائمة
    contribution = api_env["vice_client"].post(
        f"{BASE}{first['id']}/contributions/",
        {"observation_type": "ACADEMIC_OBSERVATION", "notes": "لوحظ نفس الأمر إداريًا."},
        content_type="application/json",
    )
    assert contribution.status_code == 201
    assert StudentReferral.objects.count() == 1


@pytest.mark.django_db
def test_options_endpoint_restricts_teacher_categories(api_env):
    teacher_options = api_env["teacher_client"].get(f"{BASE}options/").json()
    teacher_categories = {c["value"] for c in teacher_options["categories"]}
    assert "ATTENDANCE" not in teacher_categories
    assert {"ACADEMIC", "CLASSROOM_BEHAVIOR", "SOCIAL", "OTHER"} == teacher_categories
    assert teacher_options["can_assign"] is False

    vice_options = api_env["vice_client"].get(f"{BASE}options/").json()
    assert "ATTENDANCE" in {c["value"] for c in vice_options["categories"]}
    assert vice_options["can_assign"] is True


@pytest.mark.django_db
def test_referral_student_search_is_filtered_and_privacy_limited(api_env):
    """صفحة التحويل تبحث في النشطين وتعيد أقل قدر لازم من بيانات الطالب."""
    first, second = api_env["students"]
    first.full_name = "أحمد المرشح"
    first.save(update_fields=["full_name"])
    second.full_name = "محمد الآخر"
    second.save(update_fields=["full_name"])

    response = api_env["teacher_client"].get(
        f"{BASE}students/?search=أحمد&grade={api_env['grade'].id}"
        f"&section={api_env['section'].id}"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["results"] == [
        {
            "id": first.id,
            "full_name": "أحمد المرشح",
            "grade": {"id": api_env["grade"].id, "name": "الأول الثانوي"},
            "section": {"id": api_env["section"].id, "name": "1"},
        }
    ]
    # لا هوية ولا رقم طالب ولا بيانات ولي أمر في استجابة المعلم.
    assert set(body["results"][0]) == {"id", "full_name", "grade", "section"}


@pytest.mark.django_db
def test_counselor_cannot_open_teacher_referral_student_search(api_env):
    assert api_env["counselor_client"].get(f"{BASE}students/").status_code == 403


@pytest.mark.django_db
def test_teacher_cannot_assign_counselor_on_create(api_env):
    response = create_referral(
        api_env["teacher_client"],
        api_env["students"][0].id,
        assigned_counselor_id=api_env["counselor_membership"].id,
    )
    assert response.status_code == 403
    assert response.json()["code"] == "REFERRAL_PERMISSION_DENIED"


@pytest.mark.django_db
def test_vice_attendance_referral_carries_snapshot(api_env):
    response = create_referral(
        api_env["vice_client"],
        api_env["students"][0].id,
        category=ReferralCategory.ATTENDANCE,
        reason_code=ReferralReason.REPEATED_ABSENCE,
        description="غياب متكرر.",
    )
    assert response.status_code == 201
    body = response.json()
    assert body["snapshot_at_referral"]["student_name"]
    assert "unexcused_full_absence_days" in body["snapshot_at_referral"]
    # المؤشرات الحالية تُعرض منفصلة عن اللقطة
    assert body["current_metrics"] is not None


@pytest.mark.django_db
def test_close_and_cancel(api_env):
    student = api_env["students"][0]
    first = create_referral(api_env["teacher_client"], student.id).json()
    closed = api_env["vice_client"].post(
        f"{BASE}{first['id']}/close/",
        {"reason": "تمت المتابعة مع ولي الأمر."},
        content_type="application/json",
    )
    assert closed.status_code == 200
    assert closed.json()["status"] == "CLOSED"

    second = create_referral(api_env["teacher_client"], student.id).json()
    cancelled = api_env["teacher_client"].post(
        f"{BASE}{second['id']}/cancel/",
        {"reason": "أنشئت بالخطأ."},
        content_type="application/json",
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "CANCELLED"


@pytest.mark.django_db
def test_counselor_list_and_no_counselor_error(
    api_env, role_client, make_user, make_membership
):
    listed = api_env["vice_client"].get(f"{BASE}counselors/").json()
    assert listed["has_counselors"] is True
    assert any(c["id"] == api_env["counselor_membership"].id for c in listed["counselors"])

    # مدرسة بلا مرشد: التعيين يرد رمزًا واضحًا لا فشلًا صامتًا
    other_client, other_school, _ = role_client(["SCHOOL_MANAGER"])
    other_env = build_school_env(
        other_school, make_user, make_membership, prefix="60200", tag="2"
    )
    other_env["counselor"].delete()
    referral = create_referral(other_client, other_env["students"][0].id).json()
    response = other_client.post(
        f"{BASE}{referral['id']}/assign/",
        {"counselor_membership_id": 999999},
        content_type="application/json",
    )
    assert response.status_code == 409
    assert response.json()["code"] == "NO_ACTIVE_COUNSELOR_AVAILABLE"


# ---------- خصوصية المعلم (البنود 109-111) ----------


@pytest.mark.django_db
def test_teacher_sees_only_own_referrals_via_api(api_env, role_client):
    mine = create_referral(api_env["teacher_client"], api_env["students"][0].id).json()
    other_teacher, _, _ = role_client(["TEACHER"], school=api_env["school"])
    theirs = create_referral(other_teacher, api_env["students"][1].id).json()

    listed = api_env["teacher_client"].get(BASE).json()
    assert [row["id"] for row in listed["results"]] == [mine["id"]]

    mine_page = api_env["teacher_client"].get(f"{BASE}mine/").json()
    assert [row["id"] for row in mine_page["results"]] == [mine["id"]]

    # قراءة حالة زميله ممنوعة (404 لا 403 — لا تسريب وجود)
    assert api_env["teacher_client"].get(f"{BASE}{theirs['id']}/").status_code == 404
    assert api_env["teacher_client"].get(
        f"{BASE}{theirs['id']}/contributions/"
    ).status_code == 404

    # ولا يضيف ملاحظة بمعرف حر: لو سُمح بذلك لصار الإرسال بوابة قراءة لكل حالة
    # مفتوحة في المدرسة (تعداد بالمعرفات ثم قراءة ملاحظات الزملاء)
    assert api_env["teacher_client"].post(
        f"{BASE}{theirs['id']}/contributions/",
        {"observation_type": "OTHER_OBSERVATION", "notes": "محاولة"},
        content_type="application/json",
    ).status_code == 404


@pytest.mark.django_db
def test_teacher_contributes_to_open_case_by_student_and_category(api_env, role_client):
    """البديل الآمن عن التكرار: الخادم يحل الحالة من (الطالب، الفئة)."""
    other_teacher, _, _ = role_client(["TEACHER"], school=api_env["school"])
    student = api_env["students"][0]
    referral = create_referral(other_teacher, student.id).json()

    duplicate = create_referral(api_env["teacher_client"], student.id)
    assert duplicate.status_code == 409
    assert duplicate.json()["details"]["existing_referral_id"] == referral["id"]

    added = api_env["teacher_client"].post(
        f"{BASE}contribute/",
        {
            "student_id": student.id,
            "category": ReferralCategory.ACADEMIC,
            "observation_type": "CLASSROOM_OBSERVATION",
            "notes": "نفس الملاحظة في حصتي.",
        },
        content_type="application/json",
    )
    assert added.status_code == 201
    assert added.json()["referral_id"] == referral["id"]
    # صار يرى الحالة لأنه ساهم فيها فعلًا
    assert api_env["teacher_client"].get(f"{BASE}{referral['id']}/").status_code == 200


@pytest.mark.django_db
def test_contribute_endpoint_requires_open_case_and_allowed_category(api_env):
    student = api_env["students"][0]
    missing = api_env["teacher_client"].post(
        f"{BASE}contribute/",
        {
            "student_id": student.id,
            "category": ReferralCategory.ACADEMIC,
            "observation_type": "OTHER_OBSERVATION",
            "notes": "لا حالة",
        },
        content_type="application/json",
    )
    assert missing.status_code == 404
    assert missing.json()["code"] == "REFERRAL_NOT_FOUND"

    # فئة المواظبة ليست للمعلم — لا يضيف فيها ملاحظة أيضًا
    create_referral(
        api_env["vice_client"], student.id,
        category=ReferralCategory.ATTENDANCE,
        reason_code=ReferralReason.REPEATED_ABSENCE,
        description="غياب.",
    )
    denied = api_env["teacher_client"].post(
        f"{BASE}contribute/",
        {
            "student_id": student.id,
            "category": ReferralCategory.ATTENDANCE,
            "observation_type": "ATTENDANCE_OBSERVATION",
            "notes": "محاولة",
        },
        content_type="application/json",
    )
    assert denied.status_code == 403
    assert denied.json()["code"] == "INVALID_REFERRAL_CATEGORY"


@pytest.mark.django_db
def test_creator_cannot_cancel_after_acknowledge(api_env):
    student = api_env["students"][0]
    referral = create_referral(api_env["teacher_client"], student.id).json()
    api_env["vice_client"].post(
        f"{BASE}{referral['id']}/assign/",
        {"counselor_membership_id": api_env["counselor_membership"].id},
        content_type="application/json",
    )
    api_env["counselor_client"].post(f"{BASE}{referral['id']}/acknowledge/")

    denied = api_env["teacher_client"].post(
        f"{BASE}{referral['id']}/cancel/",
        {"reason": "تراجعت"},
        content_type="application/json",
    )
    assert denied.status_code == 409
    assert denied.json()["code"] == "REFERRAL_ALREADY_ACKNOWLEDGED"

    # مدير المدرسة يستطيع سحبها بعد انتقال المسؤولية للمرشد.
    assert api_env["manager_client"].post(
        f"{BASE}{referral['id']}/cancel/",
        {"reason": "سُحبت إداريًا"},
        content_type="application/json",
    ).status_code == 200


@pytest.mark.django_db
def test_invalid_status_filter_is_rejected(api_env):
    response = api_env["vice_client"].get(f"{BASE}?status=NOPE")
    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_ERROR"


@pytest.mark.django_db
def test_teacher_cannot_manage(api_env):
    referral = create_referral(api_env["teacher_client"], api_env["students"][0].id).json()
    assert api_env["teacher_client"].post(
        f"{BASE}{referral['id']}/assign/",
        {"counselor_membership_id": api_env["counselor_membership"].id},
        content_type="application/json",
    ).status_code == 403
    assert api_env["teacher_client"].post(f"{BASE}{referral['id']}/acknowledge/").status_code == 403
    assert api_env["teacher_client"].get(f"{BASE}counselors/").status_code == 403


# ---------- المرشد ----------


@pytest.mark.django_db
def test_counselor_scope_and_acknowledge_policy(api_env, role_client, make_user, make_membership):
    student = api_env["students"][0]
    mine = create_referral(api_env["teacher_client"], student.id).json()
    api_env["vice_client"].post(
        f"{BASE}{mine['id']}/assign/",
        {"counselor_membership_id": api_env["counselor_membership"].id},
        content_type="application/json",
    )
    second_counselor_client, _, second_user = role_client(
        ["COUNSELOR"], school=api_env["school"]
    )
    # المرشد الآخر لا يرى الحالة المعينة لزميله ولا يستلمها
    assert second_counselor_client.get(f"{BASE}{mine['id']}/").status_code == 404
    assert second_counselor_client.post(
        f"{BASE}{mine['id']}/acknowledge/"
    ).status_code == 404
    # المرشد المعيَّن يستلمها
    assert api_env["counselor_client"].post(
        f"{BASE}{mine['id']}/acknowledge/"
    ).status_code == 200


@pytest.mark.django_db
def test_counselor_cannot_create_or_assign(api_env):
    created = create_referral(api_env["counselor_client"], api_env["students"][0].id)
    assert created.status_code == 403
    assert created.json()["code"] == "REFERRAL_PERMISSION_DENIED"
    assert api_env["counselor_client"].get(f"{BASE}counselors/").status_code == 403


# ---------- العزل بين المدارس / IDOR (البنود 82-84) ----------


@pytest.mark.django_db
def test_tenant_isolation(api_env, role_client, make_user, make_membership):
    other_client, other_school, _ = role_client(["SCHOOL_MANAGER"])
    other_env = build_school_env(
        other_school, make_user, make_membership, prefix="60300", tag="3"
    )
    foreign = create_referral(other_client, other_env["students"][0].id).json()

    vice = api_env["vice_client"]
    assert vice.get(f"{BASE}{foreign['id']}/").status_code == 404
    assert vice.post(
        f"{BASE}{foreign['id']}/assign/",
        {"counselor_membership_id": api_env["counselor_membership"].id},
        content_type="application/json",
    ).status_code == 404
    assert vice.post(
        f"{BASE}{foreign['id']}/close/", {"reason": "x"}, content_type="application/json"
    ).status_code == 404
    assert vice.get(f"{BASE}{foreign['id']}/contributions/").status_code == 404

    # طالب مدرسة أخرى لا يُحال من هنا
    assert create_referral(vice, other_env["students"][0].id).status_code == 404

    # مرشد مدرسة أخرى لا يُعيَّن على إحالة هذه المدرسة
    local = create_referral(vice, api_env["students"][0].id).json()
    assert vice.post(
        f"{BASE}{local['id']}/assign/",
        {"counselor_membership_id": other_env["counselor"].id},
        content_type="application/json",
    ).status_code == 400


@pytest.mark.django_db
def test_multi_school_role_scope(api_env, make_school, make_membership):
    """معلم في A ومرشد في B: صلاحياته تتبع المدرسة النشطة (بند 116)."""
    school_b = make_school()
    teacher_user = api_env["teacher"].user
    make_membership(teacher_user, school_b, ["COUNSELOR"])
    client = api_env["teacher_client"]

    # في A: ينشئ كمعلم ولا يملك أدوات المرشد
    assert create_referral(client, api_env["students"][0].id).status_code == 201
    assert client.get(f"{BASE}counselors/").status_code == 403

    switched = client.post(
        "/api/v1/session/active-school/", {"school_id": school_b.id},
        content_type="application/json",
    )
    assert switched.status_code == 200
    # في B: مرشد — لا يرى بيانات A ولا ينشئ إحالة كمعلم
    assert client.get(BASE).json()["count"] == 0
    assert create_referral(client, api_env["students"][0].id).status_code == 404


# ---------- Mass assignment (بند 75) ----------


@pytest.mark.django_db
def test_create_ignores_server_owned_fields(api_env):
    response = create_referral(
        api_env["teacher_client"],
        api_env["students"][0].id,
        status="CLOSED",
        school=999,
        created_by_membership=1,
        accepted_at="2026-01-01T00:00:00Z",
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "PENDING_VICE"
    assert body["accepted_at"] is None
    assert StudentReferral.objects.get(id=body["id"]).school_id == api_env["school"].id


@pytest.mark.django_db
def test_student_referrals_tab_endpoint(api_env):
    student = api_env["students"][0]
    created = create_referral(api_env["teacher_client"], student.id).json()
    listed = api_env["vice_client"].get(f"/api/v1/students/{student.id}/referrals/")
    assert listed.status_code == 200
    assert [row["id"] for row in listed.json()["results"]] == [created["id"]]
    # المعلم لا يملك هذا المسار (ملف الطالب إداري)
    assert api_env["teacher_client"].get(
        f"/api/v1/students/{student.id}/referrals/"
    ).status_code == 403
