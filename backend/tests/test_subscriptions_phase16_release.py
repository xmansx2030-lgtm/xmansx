from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from threading import Event

import pytest
from django.core.exceptions import ObjectDoesNotExist
from django.db import connection, connections, transaction
from django.db.models.deletion import ProtectedError
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from academics.models import AcademicYear, AcademicYearStatus
from attendance.models import AttendanceMark
from common.errors import ApiError
from counseling.models import CounselorCase
from devices.models import AttendanceDevice
from documents.models import DocumentStatus, DocumentType, GeneratedDocument
from documents.services.generation import generate_document
from excuses.models import AbsenceExcuse
from memberships.models import SchoolMembership, SchoolRole
from referrals.models import (
    ReferralCategory,
    ReferralReason,
    ReferralSourceType,
    StudentReferral,
)
from schools.models import School
from student_actions.models import StudentAction, StudentActionType
from student_warnings.models import (
    StudentWarning,
    WarningLevel,
    WarningRuleType,
    WarningStatus,
)
from students.models import Student, StudentEnrollment, StudentStatus
from subscriptions.access import (
    BLOCKED,
    FULL,
    READ_ONLY,
    effective_status,
    get_school_access_mode,
)
from subscriptions.entitlements import get_limit, has_entitlement, require_capacity
from subscriptions.models import (
    EntitlementKey,
    PlanEntitlement,
    SaaSPlan,
    SchoolSubscription,
    SubscriptionEvent,
    SubscriptionEventType,
    SubscriptionStatus,
)
from subscriptions.services import plans as plan_service
from subscriptions.services import provisioning as provisioning_service
from subscriptions.services import subscriptions as subscription_service
from subscriptions.usage import BYTES_PER_GB, count_active_staff, get_school_usage
from tests.excuse_env import DAY, build_env, make_session, mark
from tests.xlsx_helper import build_xlsx_upload, noor_row


@pytest.fixture
def platform_admin(make_user):
    return make_user("0550001690", is_staff=True, is_superuser=True)


def make_plan(
    actor,
    *,
    code="release-plan",
    students=100,
    staff=10,
    devices=2,
    storage=10,
    counseling=True,
):
    return plan_service.create_plan(
        actor=actor,
        code=code,
        name_ar=f"باقة {code}",
        entitlements={
            EntitlementKey.MAX_STUDENTS: students,
            EntitlementKey.MAX_STAFF: staff,
            EntitlementKey.MAX_DEVICES: devices,
            EntitlementKey.MAX_STORAGE_GB: storage,
            EntitlementKey.COUNSELING: counseling,
        },
    )


def create_student(school, index=1, *, status=StudentStatus.ACTIVE):
    return Student.objects.create(
        school=school,
        national_id_encrypted=f"enc-release-{school.id}-{index}",
        national_id_lookup_hash=f"hash-release-{school.id}-{index}",
        national_id_masked="**********",
        student_number=f"REL-{school.id}-{index}",
        full_name=f"طالب الإصدار {index}",
        status=status,
    )


@pytest.mark.django_db
def test_plan_api_create_edit_disable_and_historical_protection(
    client, platform_admin, make_school
):
    client.force_login(platform_admin)
    created = client.post(
        "/api/v1/platform/plans/",
        {
            "code": "professional",
            "name_ar": "الاحترافية",
            "entitlements": {"MAX_STUDENTS": 1000, "COUNSELING": False},
        },
        content_type="application/json",
    )
    assert created.status_code == 201
    plan_id = created.json()["id"]
    assert created.json()["entitlements"]["MAX_STUDENTS"] == 1000
    assert created.json()["entitlements"]["COUNSELING"] is False

    edited = client.patch(
        f"/api/v1/platform/plans/{plan_id}/",
        {"name_ar": "الاحترافية المحدثة", "entitlements": {"MAX_STUDENTS": 1500}},
        content_type="application/json",
    )
    assert edited.status_code == 200
    assert edited.json()["entitlements"]["MAX_STUDENTS"] == 1500

    plan = SaaSPlan.objects.get(id=plan_id)
    subscription_service.activate(
        school=make_school(), plan_id=plan.id, actor=platform_admin
    )
    with pytest.raises(ProtectedError):
        plan.delete()

    disabled = client.delete(f"/api/v1/platform/plans/{plan_id}/")
    assert disabled.status_code == 200
    assert disabled.json()["is_active"] is False
    assert SaaSPlan.objects.filter(id=plan_id).exists()


@pytest.mark.django_db
def test_snapshot_keeps_existing_value_and_new_contract_gets_edited_default(
    make_school, platform_admin
):
    plan = make_plan(platform_admin, students=1000)
    school_a = make_school("مدرسة أ")
    school_b = make_school("مدرسة ب")
    subscription_service.activate(school=school_a, plan_id=plan.id, actor=platform_admin)

    plan_service.update_plan(
        plan=plan,
        actor=platform_admin,
        entitlements={EntitlementKey.MAX_STUDENTS: 1500},
    )
    subscription_service.activate(school=school_b, plan_id=plan.id, actor=platform_admin)

    assert get_limit(school_a, EntitlementKey.MAX_STUDENTS) == 1000
    assert get_limit(school_b, EntitlementKey.MAX_STUDENTS) == 1500


@pytest.mark.django_db
def test_trial_extension_activation_and_history(make_school, platform_admin):
    school = make_school()
    plan = make_plan(platform_admin)
    trial = subscription_service.start_trial(
        school=school, plan_id=plan.id, actor=platform_admin, trial_days=7
    )
    old_end = trial.trial_ends_at
    extended = subscription_service.extend_trial(
        school=school,
        extra_days=3,
        actor=platform_admin,
        reason="اعتماد إضافي",
    )
    event = SubscriptionEvent.objects.get(
        subscription=trial, event_type=SubscriptionEventType.TRIAL_EXTENDED
    )
    assert extended.trial_ends_at == old_end + timedelta(days=3)
    assert event.actor == platform_admin
    assert event.reason == "اعتماد إضافي"
    assert event.metadata["old_end"] == old_end.isoformat()
    assert event.metadata["new_end"] == extended.trial_ends_at.isoformat()

    active = subscription_service.activate(
        school=school, plan_id=plan.id, actor=platform_admin
    )
    trial.refresh_from_db()
    assert trial.status == SubscriptionStatus.EXPIRED
    assert active.status == SubscriptionStatus.ACTIVE
    assert SchoolSubscription.objects.filter(school=school).count() == 2


@pytest.mark.django_db
def test_effective_status_and_access_policy_for_every_state(make_school, platform_admin):
    plan = make_plan(platform_admin)
    now = timezone.now()
    scenarios = [
        (SubscriptionStatus.TRIAL, now + timedelta(days=2), None, SubscriptionStatus.TRIAL, FULL),
        (SubscriptionStatus.ACTIVE, now + timedelta(days=2), None, SubscriptionStatus.ACTIVE, FULL),
        (
            SubscriptionStatus.ACTIVE,
            now - timedelta(days=1),
            now + timedelta(days=2),
            SubscriptionStatus.GRACE_PERIOD,
            FULL,
        ),
        (
            SubscriptionStatus.ACTIVE,
            now - timedelta(days=2),
            now - timedelta(days=1),
            SubscriptionStatus.EXPIRED,
            READ_ONLY,
        ),
        (
            SubscriptionStatus.SUSPENDED,
            now + timedelta(days=2),
            None,
            SubscriptionStatus.SUSPENDED,
            BLOCKED,
        ),
        (
            SubscriptionStatus.CANCELLED,
            now + timedelta(days=2),
            None,
            SubscriptionStatus.CANCELLED,
            READ_ONLY,
        ),
    ]
    for index, (stored, end, grace_end, expected, mode) in enumerate(scenarios, 1):
        school = make_school(f"حالة {index}")
        kwargs = {}
        if stored == SubscriptionStatus.SUSPENDED:
            kwargs = {"suspended_at": now, "suspension_reason": "اختبار"}
        if stored == SubscriptionStatus.CANCELLED:
            kwargs = {"cancelled_at": now, "cancel_reason": "اختبار"}
        subscription = SchoolSubscription.objects.create(
            school=school,
            plan=plan,
            status=stored,
            starts_at=now - timedelta(days=30),
            ends_at=end,
            trial_started_at=(
                now - timedelta(days=5)
                if stored == SubscriptionStatus.TRIAL
                else None
            ),
            trial_ends_at=end if stored == SubscriptionStatus.TRIAL else None,
            grace_ends_at=grace_end,
            created_by=platform_admin,
            updated_by=platform_admin,
            **kwargs,
        )
        assert effective_status(subscription, now=now) == expected
        assert get_school_access_mode(school, now=now) == mode


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("operation", "expected_status"),
    [
        ("trial_end", SubscriptionStatus.EXPIRED),
        ("expire", SubscriptionStatus.EXPIRED),
        ("suspend", SubscriptionStatus.SUSPENDED),
        ("cancel", SubscriptionStatus.CANCELLED),
        ("downgrade", SubscriptionStatus.ACTIVE),
    ],
)
def test_subscription_operations_preserve_cross_feature_data(
    operation,
    expected_status,
    make_school,
    make_user,
    make_membership,
    platform_admin,
):
    school = make_school()
    teacher = make_membership(make_user("0550001611"), school, [SchoolRole.TEACHER])
    vice = make_membership(make_user("0550001612"), school, [SchoolRole.VICE_PRINCIPAL])
    counselor = make_membership(make_user("0550001613"), school, [SchoolRole.COUNSELOR])
    manager = make_membership(make_user("0550001614"), school, [SchoolRole.SCHOOL_MANAGER])
    env = build_env(
        school=school,
        teacher_membership=teacher,
        vice_membership=vice,
        prefix="31610",
    )
    student = env["students"][0]
    session = make_session(env, 1)
    mark(env, session, student, "ABSENT")
    excuse = AbsenceExcuse.objects.create(
        school=school,
        student=student,
        reason_type="MEDICAL_REPORT",
        notes="",
        recorded_by_membership=vice,
        recorded_at=timezone.now(),
    )
    warning = StudentWarning.objects.create(
        school=school,
        student=student,
        academic_year=env["year"],
        warning_type=WarningRuleType.UNEXCUSED_FULL_DAY_ABSENCE,
        level=WarningLevel.LEVEL_1,
        status=WarningStatus.ISSUED,
        threshold_at_issue=1,
        metric_value_at_issue=1,
        student_name_snapshot=student.full_name,
        issued_by_membership=vice,
        issued_at=timezone.now(),
    )
    action = StudentAction.objects.create(
        school=school,
        student=student,
        warning=warning,
        action_type=StudentActionType.PARENT_CONTACT,
        performed_by_membership=vice,
        performed_at=timezone.now(),
    )
    document = GeneratedDocument.objects.create(
        school=school,
        student=student,
        warning=warning,
        action=action,
        document_type=DocumentType.WARNING_LEVEL_1,
        template_key="warning_level_1",
        template_version="1",
        status=DocumentStatus.PENDING,
        generated_by_membership=vice,
    )
    referral = StudentReferral.objects.create(
        school=school,
        student=student,
        source_type=ReferralSourceType.VICE_PRINCIPAL,
        category=ReferralCategory.ATTENDANCE,
        reason_code=ReferralReason.REPEATED_ABSENCE,
        created_by_membership=vice,
        assigned_counselor_membership=counselor,
    )
    case = CounselorCase.objects.create(
        school=school,
        student=student,
        primary_referral=referral,
        assigned_counselor_membership=counselor,
        opened_by_membership=counselor,
        opened_at=timezone.now(),
        last_activity_at=timezone.now(),
    )
    device = AttendanceDevice.objects.create(
        school=school, name="جهاز الحفظ", vendor="ZKTeco", serial_number="PRESERVE-1"
    )
    before = {
        Student: Student.objects.filter(school=school).count(),
        StudentEnrollment: StudentEnrollment.objects.filter(school=school).count(),
        AttendanceMark: AttendanceMark.objects.filter(school=school).count(),
        AbsenceExcuse: AbsenceExcuse.objects.filter(school=school).count(),
        StudentWarning: StudentWarning.objects.filter(school=school).count(),
        StudentAction: StudentAction.objects.filter(school=school).count(),
        GeneratedDocument: GeneratedDocument.objects.filter(school=school).count(),
        StudentReferral: StudentReferral.objects.filter(school=school).count(),
        CounselorCase: CounselorCase.objects.filter(school=school).count(),
        AttendanceDevice: AttendanceDevice.objects.filter(school=school).count(),
    }
    assert all((excuse.id, document.id, case.id, device.id))

    high = make_plan(
        platform_admin, code="preserve-high", students=500, devices=5
    )
    if operation == "trial_end":
        subscription = subscription_service.start_trial(
            school=school, plan_id=high.id, actor=platform_admin
        )
    else:
        subscription = subscription_service.activate(
            school=school, plan_id=high.id, actor=platform_admin
        )

    if operation in {"trial_end", "expire"}:
        now = timezone.now()
        subscription.starts_at = now - timedelta(days=30)
        subscription.ends_at = now - timedelta(days=1)
        if operation == "trial_end":
            subscription.trial_started_at = subscription.starts_at
            subscription.trial_ends_at = subscription.ends_at
        subscription.save()
        subscription_service.sync_expirations(now=now)
    elif operation == "suspend":
        subscription_service.suspend(
            school=school, actor=platform_admin, reason="اختبار حفظ البيانات"
        )
    elif operation == "cancel":
        subscription_service.cancel(
            school=school, actor=platform_admin, reason="اختبار حفظ البيانات"
        )
    else:
        low = make_plan(
            platform_admin, code="preserve-low", students=1, devices=0
        )
        subscription_service.change_plan(
            school=school, plan_id=low.id, actor=platform_admin, reason="downgrade"
        )

    subscription.refresh_from_db()
    assert subscription.status == expected_status
    for model, count in before.items():
        assert model.objects.filter(school=school).count() == count
    assert SchoolMembership.objects.filter(id=manager.id).exists()


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("status_value", "code"),
    [
        (SubscriptionStatus.EXPIRED, "SUBSCRIPTION_EXPIRED"),
        (SubscriptionStatus.SUSPENDED, "SCHOOL_SUSPENDED"),
        (SubscriptionStatus.CANCELLED, "SUBSCRIPTION_CANCELLED"),
    ],
)
def test_write_block_returns_specific_subscription_error(
    status_value, code, role_client, platform_admin
):
    client, school, _ = role_client([SchoolRole.SCHOOL_MANAGER])
    plan = make_plan(platform_admin)
    subscription = subscription_service.activate(
        school=school, plan_id=plan.id, actor=platform_admin
    )
    now = timezone.now()
    if status_value == SubscriptionStatus.EXPIRED:
        subscription.status = status_value
    elif status_value == SubscriptionStatus.SUSPENDED:
        subscription.status = status_value
        subscription.suspended_at = now
        subscription.suspension_reason = "اختبار"
    else:
        subscription.status = status_value
        subscription.cancelled_at = now
        subscription.cancel_reason = "اختبار"
    subscription.save()

    response = client.post(
        "/api/v1/devices/",
        {"name": "جهاز", "vendor": "ZKTeco", "serial_number": "BLOCKED"},
        content_type="application/json",
    )
    assert response.status_code == 403
    assert response.json()["code"] == code
    assert client.get("/api/v1/auth/me/").status_code == 200
    assert client.get("/api/v1/school/subscription/").status_code == 200


@pytest.mark.django_db
def test_active_student_formula_excludes_non_active_states(make_school):
    school = make_school()
    for index, status_value in enumerate(StudentStatus.values, 1):
        create_student(school, index, status=status_value)
    assert get_school_usage(school)["students"]["used"] == 1


@pytest.mark.django_db
def test_staff_limit_counts_memberships_per_school_once(
    make_school, make_user, make_membership, platform_admin
):
    school_a = make_school("طاقم أ")
    school_b = make_school("طاقم ب")
    shared_user = make_user("0550001624")
    make_membership(shared_user, school_a, [SchoolRole.TEACHER])
    make_membership(shared_user, school_b, [SchoolRole.TEACHER])
    plan = make_plan(platform_admin, staff=2)
    subscription_service.activate(school=school_a, plan_id=plan.id, actor=platform_admin)

    assert count_active_staff(school_a) == 1
    require_capacity(
        school_a, EntitlementKey.MAX_STAFF, current=count_active_staff(school_a)
    )
    make_membership(make_user("0550001625"), school_a, [SchoolRole.COUNSELOR])
    with pytest.raises(ApiError) as exc:
        require_capacity(
            school_a, EntitlementKey.MAX_STAFF, current=count_active_staff(school_a)
        )
    assert exc.value.code == "STAFF_LIMIT_EXCEEDED"
    assert count_active_staff(school_b) == 1


@pytest.mark.django_db
def test_device_limit_denies_third_device_without_removing_two_existing(
    role_client, platform_admin
):
    client, school, _ = role_client([SchoolRole.SCHOOL_MANAGER])
    plan = make_plan(platform_admin, devices=2)
    subscription_service.activate(school=school, plan_id=plan.id, actor=platform_admin)
    for index in range(2):
        AttendanceDevice.objects.create(
            school=school,
            name=f"جهاز {index}",
            vendor="ZKTeco",
            serial_number=f"LIMIT-{index}",
        )
    response = client.post(
        "/api/v1/devices/",
        {"name": "الثالث", "vendor": "ZKTeco", "serial_number": "LIMIT-3"},
        content_type="application/json",
    )
    assert response.status_code == 409
    assert response.json()["code"] == "DEVICE_LIMIT_EXCEEDED"
    assert AttendanceDevice.objects.filter(school=school).count() == 2


@pytest.mark.django_db
def test_generated_document_storage_limit_marks_attempt_failed(
    make_school, make_user, make_membership, platform_admin, monkeypatch
):
    from schools.models import SchoolSettings

    school = make_school()
    vice = make_membership(make_user("0550001626"), school, [SchoolRole.VICE_PRINCIPAL])
    teacher = make_membership(make_user("0550001627"), school, [SchoolRole.TEACHER])
    env = build_env(
        school=school,
        teacher_membership=teacher,
        vice_membership=vice,
        prefix="31620",
    )
    SchoolSettings.objects.create(
        school=school,
        ministry_school_number="1600",
        city="الرياض",
        official_principal_name="مدير الاختبار",
    )
    plan = make_plan(platform_admin, code="storage-zero", storage=0)
    subscription_service.activate(school=school, plan_id=plan.id, actor=platform_admin)
    monkeypatch.setattr("documents.services.generation._render", lambda **_kwargs: b"pdf")

    with pytest.raises(ApiError) as exc:
        generate_document(
            school=school,
            membership=vice,
            student=env["students"][0],
            document_type=DocumentType.ATTENDANCE_COMMITMENT,
            from_date=DAY,
            to_date=DAY,
        )
    assert exc.value.code == "STORAGE_LIMIT_EXCEEDED"
    attempt = GeneratedDocument.objects.get(school=school)
    assert attempt.status == DocumentStatus.FAILED
    assert attempt.error_code == "STORAGE_LIMIT_EXCEEDED"
    assert not attempt.file


@pytest.mark.django_db
def test_storage_usage_warns_when_near_limit(make_school, platform_admin, monkeypatch):
    school = make_school()
    plan = make_plan(platform_admin, code="storage-warning", storage=1)
    subscription_service.activate(school=school, plan_id=plan.id, actor=platform_admin)
    monkeypatch.setattr(
        "subscriptions.usage.storage_used_bytes", lambda _school: int(BYTES_PER_GB * 0.9)
    )

    storage = get_school_usage(school)["storage"]

    assert storage["near_limit"] is True
    assert storage["over_limit"] is False


@pytest.mark.django_db
def test_counseling_entitlement_true_allows_backend_endpoint(role_client, platform_admin):
    client, school, _ = role_client([SchoolRole.COUNSELOR])
    plan = make_plan(platform_admin, counseling=True)
    subscription_service.activate(school=school, plan_id=plan.id, actor=platform_admin)
    assert client.get("/api/v1/counselor/dashboard/").status_code == 200


@pytest.mark.django_db
def test_extending_expired_contract_renews_from_now(make_school, platform_admin):
    school = make_school()
    plan = make_plan(platform_admin)
    subscription = subscription_service.activate(
        school=school, plan_id=plan.id, actor=platform_admin
    )
    now = timezone.now()
    subscription.starts_at = now - timedelta(days=60)
    subscription.ends_at = now - timedelta(days=30)
    subscription.status = SubscriptionStatus.EXPIRED
    subscription.save()

    renewed = subscription_service.extend(
        school=school, extra_days=30, actor=platform_admin, reason="renewal"
    )
    assert renewed.status == SubscriptionStatus.ACTIVE
    assert renewed.ends_at >= now + timedelta(days=29)
    assert effective_status(renewed) == SubscriptionStatus.ACTIVE


@pytest.mark.django_db
def test_noor_preview_warns_commit_denies_then_upgrade_allows_same_job(
    role_client, platform_admin
):
    client, school, _ = role_client([SchoolRole.SCHOOL_MANAGER])
    AcademicYear.objects.create(
        school=school,
        name="2026/2027",
        start_date=date(2026, 8, 1),
        end_date=date(2027, 6, 25),
        status=AcademicYearStatus.ACTIVE,
    )
    basic = make_plan(platform_admin, code="noor-basic", students=1)
    upgrade = make_plan(platform_admin, code="noor-upgrade", students=5)
    subscription_service.activate(school=school, plan_id=basic.id, actor=platform_admin)
    create_student(school)

    uploaded = client.post(
        "/api/v1/student-imports/",
        {"file": build_xlsx_upload([noor_row("1012345678", "طالب جديد")])},
    )
    assert uploaded.status_code == 201
    job_id = uploaded.json()["id"]
    assert client.post(f"/api/v1/student-imports/{job_id}/process/", {}).status_code == 202
    preview = client.get(f"/api/v1/student-imports/{job_id}/").json()
    assert preview["summary"]["student_capacity"] == {
        "used": 1,
        "adding": 1,
        "projected": 2,
        "limit": 1,
        "over_limit": True,
    }
    denied = client.post(f"/api/v1/student-imports/{job_id}/commit/")
    assert denied.status_code == 409
    assert denied.json()["code"] == "STUDENT_LIMIT_EXCEEDED"

    subscription_service.change_plan(
        school=school, plan_id=upgrade.id, actor=platform_admin, reason="upgrade"
    )
    assert get_limit(school, EntitlementKey.MAX_STUDENTS) == 5
    accepted = client.post(f"/api/v1/student-imports/{job_id}/commit/")
    assert accepted.status_code == 200
    assert Student.objects.filter(school=school, status=StudentStatus.ACTIVE).count() == 2


@pytest.mark.django_db
def test_school_provisioning_password_and_transactionality(client, platform_admin):
    plan = make_plan(platform_admin, code="provision-ok", staff=1)
    result = provisioning_service.create_school(
        actor=platform_admin,
        school_name="مدرسة الإصدار",
        school_type="GIRLS",
        manager_name="مدير الإصدار",
        manager_mobile="0550001620",
        plan_id=plan.id,
    )
    password = result["temporary_password"]
    manager = result["manager_membership"].user
    assert password
    assert manager.check_password(password)
    assert manager.password != password
    assert manager.must_change_password is True
    assert result["subscription"].status == SubscriptionStatus.TRIAL
    assert result["school"].school_type == "GIRLS"

    login = client.post(
        "/api/v1/auth/login/",
        {"mobile": "0550001620", "password": password},
        content_type="application/json",
    )
    assert login.status_code == 200
    assert login.json()["must_change_password"] is True

    blocked_plan = make_plan(platform_admin, code="provision-blocked", staff=0)
    before = School.objects.count()
    with pytest.raises(ApiError) as exc:
        provisioning_service.create_school(
            actor=platform_admin,
            school_name="مدرسة لا تكتمل",
            school_type="BOYS",
            manager_name="مدير",
            manager_mobile="0550001621",
            plan_id=blocked_plan.id,
        )
    assert exc.value.code == "STAFF_LIMIT_EXCEEDED"
    assert School.objects.count() == before
    with pytest.raises(ObjectDoesNotExist):
        School.objects.get(name="مدرسة لا تكتمل")


@pytest.mark.django_db
def test_multi_school_subscription_context_does_not_leak(
    client, make_school, make_user, make_membership, platform_admin
):
    user = make_user("0550001622")
    school_a = make_school("النشطة")
    school_b = make_school("المنتهية")
    make_membership(user, school_a, [SchoolRole.SCHOOL_MANAGER])
    make_membership(user, school_b, [SchoolRole.SCHOOL_MANAGER])
    plan = make_plan(platform_admin)
    subscription_service.activate(school=school_a, plan_id=plan.id, actor=platform_admin)
    expired = subscription_service.activate(
        school=school_b, plan_id=plan.id, actor=platform_admin
    )
    expired.status = SubscriptionStatus.EXPIRED
    expired.save(update_fields=["status", "updated_at"])
    client.force_login(user)

    for school, expected in ((school_a, "ACTIVE"), (school_b, "EXPIRED"), (school_a, "ACTIVE")):
        switched = client.post(
            "/api/v1/session/active-school/",
            {"school_id": school.id},
            content_type="application/json",
        )
        assert switched.status_code == 200
        state = client.get("/api/v1/school/subscription/").json()["subscription"]
        assert state["status"] == expected


@pytest.mark.django_db
@pytest.mark.parametrize(
    "role",
    [
        SchoolRole.SCHOOL_MANAGER,
        SchoolRole.VICE_PRINCIPAL,
        SchoolRole.COUNSELOR,
        SchoolRole.TEACHER,
        SchoolRole.GATE_GUARD,
    ],
)
def test_every_school_role_is_denied_platform_api(role, role_client):
    client, _, _ = role_client([role])
    response = client.get("/api/v1/platform/overview/")
    assert response.status_code == 403
    assert response.json()["code"] == "PERMISSION_DENIED"


@pytest.mark.django_db
def test_platform_overview_uses_latest_effective_contract_and_usage_totals(
    client, make_school, make_user, make_membership, platform_admin
):
    school = make_school()
    plan = make_plan(platform_admin)
    subscription_service.start_trial(school=school, plan_id=plan.id, actor=platform_admin)
    subscription_service.activate(school=school, plan_id=plan.id, actor=platform_admin)
    create_student(school)
    make_membership(make_user("0550001623"), school, [SchoolRole.TEACHER])
    AttendanceDevice.objects.create(
        school=school, name="جهاز", vendor="ZKTeco", serial_number="OVERVIEW-1"
    )
    client.force_login(platform_admin)

    response = client.get("/api/v1/platform/overview/")
    assert response.status_code == 200
    body = response.json()
    assert body["subscriptions"]["active"] == 1
    assert body["subscriptions"]["trial"] == 0
    assert body["usage_totals"] == {
        "active_students": 1,
        "active_staff": 1,
        "active_devices": 1,
    }


@pytest.mark.django_db
def test_platform_school_list_has_manager_usage_filters_privacy_and_constant_queries(
    client, make_school, make_user, make_membership, platform_admin
):
    plan = make_plan(platform_admin, students=0)
    for index in range(12):
        school = make_school(f"مدرسة منصة {index:02d}")
        make_membership(
            make_user(f"055001{index:04d}"), school, [SchoolRole.SCHOOL_MANAGER]
        )
        subscription_service.activate(school=school, plan_id=plan.id, actor=platform_admin)
        if index == 0:
            create_student(school)
    client.force_login(platform_admin)

    with CaptureQueriesContext(connection) as captured:
        response = client.get("/api/v1/platform/schools/?page_size=100")
    assert response.status_code == 200
    assert len(captured) <= 12
    rows = response.json()["results"]
    assert len(rows) == 12
    assert rows[0]["manager"]["name"]
    assert "usage" in rows[0]
    serialized = str(rows).lower()
    for forbidden in ("guardian", "attendance_records", "counselor_notes", "attachments"):
        assert forbidden not in serialized

    over = client.get("/api/v1/platform/schools/?over_limit=1").json()["results"]
    assert len(over) == 1
    assert over[0]["usage"]["students"]["over_limit"] is True
    by_plan = client.get(
        f"/api/v1/platform/schools/?plan={plan.code}"
    ).json()["results"]
    assert len(by_plan) == 12


@pytest.mark.django_db
def test_plan_change_preview_marks_over_limit_and_never_changes_data(
    client, make_school, platform_admin
):
    school = make_school()
    high = make_plan(platform_admin, code="preview-high", students=500, devices=5)
    low = make_plan(platform_admin, code="preview-low", students=1, devices=1)
    subscription = subscription_service.activate(
        school=school, plan_id=high.id, actor=platform_admin
    )
    for index in range(3):
        create_student(school, index)
        AttendanceDevice.objects.create(
            school=school,
            name=f"جهاز معاينة {index}",
            vendor="ZKTeco",
            serial_number=f"PREVIEW-{index}",
        )
    client.force_login(platform_admin)

    response = client.get(
        f"/api/v1/platform/schools/{school.id}/subscription/plan-preview/?plan_id={low.id}"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["impact"]["students"] == {
        "used": 3,
        "new_limit": 1,
        "over_limit": True,
    }
    assert body["impact"]["devices"]["over_limit"] is True
    assert body["deletes_data"] is False
    subscription.refresh_from_db()
    assert subscription.plan_id == high.id
    assert Student.objects.filter(school=school).count() == 3
    assert AttendanceDevice.objects.filter(school=school).count() == 3


@pytest.mark.django_db(transaction=True)
def test_concurrent_first_activation_creates_one_live_contract(
    make_school, platform_admin
):
    school = make_school()
    plan = make_plan(platform_admin)

    def activate_once():
        connections.close_all()
        try:
            subscription_service.activate(
                school=School.objects.get(id=school.id),
                plan_id=plan.id,
                actor=platform_admin.__class__.objects.get(id=platform_admin.id),
            )
            return "created"
        except ApiError as exc:
            return exc.code
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: activate_once(), range(2)))

    assert sorted(results) == ["SUBSCRIPTION_ALREADY_ACTIVE", "created"]
    assert SchoolSubscription.objects.filter(
        school=school,
        status__in=[
            SubscriptionStatus.TRIAL,
            SubscriptionStatus.ACTIVE,
            SubscriptionStatus.GRACE_PERIOD,
        ],
    ).count() == 1


@pytest.mark.django_db(transaction=True)
def test_concurrent_renewals_serialize_without_lost_updates(make_school, platform_admin):
    school = make_school()
    plan = make_plan(platform_admin)
    subscription = subscription_service.activate(
        school=school, plan_id=plan.id, actor=platform_admin
    )
    original_end = subscription.ends_at

    def renew_once():
        connections.close_all()
        try:
            subscription_service.extend(
                school=School.objects.get(id=school.id),
                extra_days=1,
                actor=platform_admin.__class__.objects.get(id=platform_admin.id),
                reason="concurrent renewal",
            )
            return "extended"
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: renew_once(), range(2)))

    subscription.refresh_from_db()
    assert results == ["extended", "extended"]
    assert subscription.ends_at == original_end + timedelta(days=2)
    assert SubscriptionEvent.objects.filter(
        subscription=subscription, event_type=SubscriptionEventType.EXTENDED
    ).count() == 2


@pytest.mark.django_db(transaction=True)
def test_concurrent_change_to_same_plan_writes_one_event(make_school, platform_admin):
    school = make_school()
    old_plan = make_plan(platform_admin, code="concurrent-old")
    new_plan = make_plan(platform_admin, code="concurrent-new")
    subscription = subscription_service.activate(
        school=school, plan_id=old_plan.id, actor=platform_admin
    )

    def change_once():
        connections.close_all()
        try:
            subscription_service.change_plan(
                school=School.objects.get(id=school.id),
                plan_id=new_plan.id,
                actor=platform_admin.__class__.objects.get(id=platform_admin.id),
                reason="concurrent change",
            )
            return "changed"
        except ApiError as exc:
            return exc.code
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: change_once(), range(2)))

    subscription.refresh_from_db()
    assert sorted(results) == ["INVALID_PLAN_CHANGE", "changed"]
    assert subscription.plan_id == new_plan.id
    assert SubscriptionEvent.objects.filter(
        subscription=subscription, event_type=SubscriptionEventType.PLAN_CHANGED
    ).count() == 1


@pytest.mark.django_db(transaction=True)
def test_overlapping_suspend_then_reactivate_has_deterministic_order(
    make_school, platform_admin
):
    school = make_school()
    plan = make_plan(platform_admin)
    subscription = subscription_service.activate(
        school=school, plan_id=plan.id, actor=platform_admin
    )
    lock_acquired = Event()
    reactivation_started = Event()

    def suspend_while_holding_lock():
        connections.close_all()
        try:
            with transaction.atomic():
                SchoolSubscription.objects.select_for_update().get(id=subscription.id)
                lock_acquired.set()
                assert reactivation_started.wait(timeout=5)
                subscription_service.suspend(
                    school=School.objects.get(id=school.id),
                    actor=platform_admin.__class__.objects.get(id=platform_admin.id),
                    reason="concurrent suspension",
                )
        finally:
            connections.close_all()

    def reactivate_after_lock():
        connections.close_all()
        try:
            assert lock_acquired.wait(timeout=5)
            reactivation_started.set()
            subscription_service.reactivate(
                school=School.objects.get(id=school.id),
                actor=platform_admin.__class__.objects.get(id=platform_admin.id),
                reason="concurrent reactivation",
            )
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(suspend_while_holding_lock),
            pool.submit(reactivate_after_lock),
        ]
        for future in futures:
            future.result()

    subscription.refresh_from_db()
    assert subscription.status == SubscriptionStatus.ACTIVE
    assert list(
        SubscriptionEvent.objects.filter(
            subscription=subscription,
            event_type__in=[
                SubscriptionEventType.SUSPENDED,
                SubscriptionEventType.REACTIVATED,
            ],
        )
        .order_by("id")
        .values_list("event_type", flat=True)
    ) == [SubscriptionEventType.SUSPENDED, SubscriptionEventType.REACTIVATED]
    assert SubscriptionEvent.objects.filter(
        school=school, event_type=SubscriptionEventType.ACTIVATED
    ).count() == 1


@pytest.mark.django_db
def test_all_subscription_events_and_transition_retry_are_idempotent(
    make_school, platform_admin
):
    school = make_school()
    plan_a = make_plan(platform_admin, code="events-a")
    plan_b = make_plan(platform_admin, code="events-b")
    trial = subscription_service.start_trial(
        school=school, plan_id=plan_a.id, actor=platform_admin
    )
    subscription_service.extend_trial(
        school=school, extra_days=1, actor=platform_admin, reason="trial"
    )
    active = subscription_service.activate(
        school=school, plan_id=plan_a.id, actor=platform_admin
    )
    subscription_service.change_plan(
        school=school, plan_id=plan_b.id, actor=platform_admin, reason="change"
    )
    subscription_service.extend(
        school=school, extra_days=1, actor=platform_admin, reason="extend"
    )
    subscription_service.suspend(
        school=school, actor=platform_admin, reason="suspend"
    )
    subscription_service.reactivate(
        school=school, actor=platform_admin, reason="reactivate"
    )
    subscription_service.cancel(
        school=school, actor=platform_admin, reason="cancel"
    )

    grace_school = make_school("مهلة")
    grace = subscription_service.activate(
        school=grace_school, plan_id=plan_a.id, actor=platform_admin
    )
    now = timezone.now()
    grace.starts_at = now - timedelta(days=30)
    grace.ends_at = now - timedelta(days=1)
    grace.grace_ends_at = now + timedelta(days=2)
    grace.save()
    assert subscription_service.sync_expirations(now=now) == {"expired": 0, "grace": 1}
    assert subscription_service.sync_expirations(now=now) == {"expired": 0, "grace": 0}

    event_types = set(SubscriptionEvent.objects.values_list("event_type", flat=True))
    assert {
        SubscriptionEventType.CREATED,
        SubscriptionEventType.TRIAL_STARTED,
        SubscriptionEventType.TRIAL_EXTENDED,
        SubscriptionEventType.ACTIVATED,
        SubscriptionEventType.PLAN_CHANGED,
        SubscriptionEventType.EXTENDED,
        SubscriptionEventType.GRACE_STARTED,
        SubscriptionEventType.SUSPENDED,
        SubscriptionEventType.REACTIVATED,
        SubscriptionEventType.CANCELLED,
    }.issubset(event_types)
    assert SubscriptionEvent.objects.filter(
        subscription=grace, event_type=SubscriptionEventType.GRACE_STARTED
    ).count() == 1
    assert SubscriptionEvent.objects.filter(
        subscription=trial, event_type=SubscriptionEventType.CREATED
    ).count() == 1
    active.refresh_from_db()
    assert active.status == SubscriptionStatus.CANCELLED


@pytest.mark.django_db
def test_entitlement_override_updates_cache_and_keeps_school_identity(
    make_school, platform_admin
):
    school_a = make_school("أ")
    school_b = make_school("ب")
    plan = make_plan(platform_admin, students=100, counseling=False)
    subscription_service.activate(school=school_a, plan_id=plan.id, actor=platform_admin)
    subscription_service.activate(school=school_b, plan_id=plan.id, actor=platform_admin)
    assert get_limit(school_a, EntitlementKey.MAX_STUDENTS) == 100
    assert get_limit(school_b, EntitlementKey.MAX_STUDENTS) == 100

    subscription_service.set_entitlement_override(
        school=school_a,
        key=EntitlementKey.MAX_STUDENTS,
        numeric_value=500,
        actor=platform_admin,
    )
    subscription_service.set_entitlement_override(
        school=school_a,
        key=EntitlementKey.COUNSELING,
        is_enabled=True,
        actor=platform_admin,
    )
    assert get_limit(school_a, EntitlementKey.MAX_STUDENTS) == 500
    assert get_limit(school_b, EntitlementKey.MAX_STUDENTS) == 100
    assert has_entitlement(school_a, EntitlementKey.COUNSELING) is True
    assert has_entitlement(school_b, EntitlementKey.COUNSELING) is False
    assert PlanEntitlement.objects.filter(plan=plan).count() == 5

    with CaptureQueriesContext(connection) as queries:
        for _ in range(10):
            assert get_limit(school_a, EntitlementKey.MAX_STUDENTS) == 500
            assert has_entitlement(school_a, EntitlementKey.COUNSELING) is True
    assert len(queries) == 0
