from concurrent.futures import ThreadPoolExecutor
from datetime import date
from threading import Barrier

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connections
from django.test import Client
from django.utils import timezone
from redis.exceptions import ConnectionError as RedisConnectionError

from academics.models import AcademicYear, AcademicYearStatus
from attendance.models import AttendanceSession
from common.cache import ResilientRedisCache
from common.errors import ApiError
from documents.services import generation as document_generation
from excuses.models import AbsenceExcuse, AbsenceExcuseAttachment
from excuses.services.excuses import add_attachment
from memberships.models import SchoolMembership, SchoolRole
from staff.models import StaffImportJob, StaffImportRow, StaffImportStatus, StaffRowStatus
from staff.services.imports.commit import commit_import as commit_staff_import
from students.models import (
    ImportJobStatus,
    ImportRowStatus,
    Student,
    StudentImportJob,
    StudentImportRow,
)
from students.services.imports.commit import commit_import
from subscriptions.models import EntitlementKey
from subscriptions.services import plans as plan_service
from subscriptions.services import subscriptions as subscription_service
from tests.attendance_helpers import setup_attendance_env

PASSWORD = "Phase19-Synthetic-Only-2026"


def test_performance_cache_fails_open_on_redis_outage(monkeypatch):
    from django.core.cache.backends.redis import RedisCache

    backend = ResilientRedisCache("redis://127.0.0.1:1/0", {})
    monkeypatch.setattr(
        RedisCache,
        "get",
        lambda *args, **kwargs: (_ for _ in ()).throw(RedisConnectionError()),
    )

    assert backend.get("missing", "fallback") == "fallback"


def test_pdf_admission_control_rejects_before_render(monkeypatch, settings):
    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def execute(self, query, params):
            self.result = (False,)

        def fetchone(self):
            return self.result

    called = False

    def render():
        nonlocal called
        called = True

    settings.PDF_RENDER_CONCURRENCY = 2
    monkeypatch.setattr(document_generation.connection, "vendor", "postgresql")
    monkeypatch.setattr(document_generation.connection, "cursor", Cursor)

    with pytest.raises(ApiError) as exc:
        document_generation._with_render_slot(render)()

    assert exc.value.code == "PDF_GENERATION_BUSY"
    assert exc.value.status_code == 429
    assert called is False


def _login_client(user) -> Client:
    client = Client()
    response = client.post(
        "/api/v1/auth/login/",
        {"mobile": user.mobile, "password": PASSWORD},
        content_type="application/json",
    )
    assert response.status_code == 200
    return client


@pytest.mark.django_db(transaction=True)
def test_attendance_start_is_idempotent_under_concurrency(
    make_school, make_user, make_membership
):
    school = make_school("Phase 19 attendance race")
    first_teacher = make_user("0550190011")
    second_teacher = make_user("0550190012")
    make_membership(first_teacher, school, [SchoolRole.TEACHER])
    make_membership(second_teacher, school, [SchoolRole.TEACHER])
    environment = setup_attendance_env(school)
    for user in (first_teacher, second_teacher):
        user.set_password(PASSWORD)
        user.save(update_fields=["password"])
    barrier = Barrier(2)

    def start_session(user) -> tuple[int, int]:
        connections.close_all()
        try:
            client = _login_client(user)
            barrier.wait(timeout=5)
            response = client.post(
                "/api/v1/attendance/sessions/start/",
                {"section_id": environment["section"].id},
                content_type="application/json",
            )
            return response.status_code, response.json()["id"]
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(start_session, (first_teacher, second_teacher)))

    assert sorted(status for status, _ in results) == [200, 201]
    assert len({session_id for _, session_id in results}) == 1
    assert AttendanceSession.objects.filter(school=school).count() == 1


@pytest.mark.django_db(transaction=True)
def test_student_limit_is_strict_across_concurrent_import_jobs(
    make_school, make_user, make_membership
):
    school = make_school("Phase 19 student race")
    manager = make_user("0550190021")
    make_membership(manager, school, [SchoolRole.SCHOOL_MANAGER])
    platform_admin = make_user("0550190022", is_staff=True, is_superuser=True)
    plan = plan_service.create_plan(
        actor=platform_admin,
        code="phase19-student-race",
        name_ar="Phase 19 student race",
        entitlements={EntitlementKey.MAX_STUDENTS: 1},
    )
    subscription_service.activate(school=school, plan_id=plan.id, actor=platform_admin)
    year = AcademicYear.objects.create(
        school=school,
        name="2026/2027",
        start_date=date(2026, 8, 1),
        end_date=date(2027, 6, 30),
        status=AcademicYearStatus.ACTIVE,
    )

    jobs = []
    for index in range(2):
        job = StudentImportJob.objects.create(
            school=school,
            uploaded_by=manager,
            academic_year=year,
            original_filename=f"phase19-{index}.xlsx",
            status=ImportJobStatus.READY_FOR_REVIEW,
        )
        StudentImportRow.objects.create(
            job=job,
            row_number=2,
            national_id_encrypted=f"phase19-encrypted-{index}",
            national_id_hash=f"phase19-hash-{index}",
            status=ImportRowStatus.NEW,
            data={
                "national_id_masked": f"******00{index}",
                "student_number": f"PH19-{index}",
                "full_name": f"Phase 19 student {index}",
                "guardian_name": "Synthetic guardian",
                "guardian_mobile": "",
                "grade_code": "G1",
                "grade_name": "Grade 1",
                "grade_sequence": 1,
                "section_code": "A",
                "section_name": "Section A",
            },
        )
        jobs.append(job)

    barrier = Barrier(2)

    def commit(job_id: int) -> str:
        connections.close_all()
        try:
            barrier.wait(timeout=5)
            try:
                commit_import(job_id=job_id, actor=manager)
            except ApiError as exc:
                return exc.code
            return "COMPLETED"
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(commit, [job.id for job in jobs]))

    assert sorted(outcomes) == ["COMPLETED", "STUDENT_LIMIT_EXCEEDED"]
    assert Student.objects.filter(school=school).count() == 1


@pytest.mark.django_db(transaction=True)
def test_device_limit_is_strict_under_concurrent_creates(
    make_school, make_user, make_membership
):
    school = make_school("Phase 19 device race")
    manager = make_user("0550190001")
    make_membership(manager, school, [SchoolRole.SCHOOL_MANAGER])
    platform_admin = make_user("0550190002", is_staff=True, is_superuser=True)
    plan = plan_service.create_plan(
        actor=platform_admin,
        code="phase19-device-race",
        name_ar="Phase 19 device race",
        entitlements={EntitlementKey.MAX_DEVICES: 1},
    )
    subscription_service.activate(school=school, plan_id=plan.id, actor=platform_admin)
    manager.set_password(PASSWORD)
    manager.save(update_fields=["password"])
    barrier = Barrier(2)

    def create_device(index: int) -> int:
        connections.close_all()
        try:
            client = Client()
            login = client.post(
                "/api/v1/auth/login/",
                {"mobile": manager.mobile, "password": PASSWORD},
                content_type="application/json",
            )
            assert login.status_code == 200
            barrier.wait(timeout=5)
            response = client.post(
                "/api/v1/devices/",
                {
                    "name": f"Phase 19 device {index}",
                    "serial_number": f"PHASE19-{index}",
                },
                content_type="application/json",
            )
            return response.status_code
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(create_device, range(2)))

    from devices.models import AttendanceDevice

    assert sorted(statuses) == [201, 409]
    assert AttendanceDevice.objects.filter(school=school, is_active=True).count() == 1


@pytest.mark.django_db(transaction=True)
def test_staff_limit_is_strict_across_concurrent_import_jobs(
    make_school, make_user, make_membership
):
    school = make_school("Phase 19 staff race")
    manager = make_user("0550190031")
    make_membership(manager, school, [SchoolRole.SCHOOL_MANAGER])
    platform_admin = make_user("0550190032", is_staff=True, is_superuser=True)
    plan = plan_service.create_plan(
        actor=platform_admin,
        code="phase19-staff-race",
        name_ar="Phase 19 staff race",
        entitlements={EntitlementKey.MAX_STAFF: 2},
    )
    subscription_service.activate(school=school, plan_id=plan.id, actor=platform_admin)

    jobs = []
    for index in range(2):
        mobile = f"055019004{index}"
        job = StaffImportJob.objects.create(
            school=school,
            uploaded_by=manager,
            original_filename=f"phase19-staff-{index}.xlsx",
            status=StaffImportStatus.READY_FOR_REVIEW,
        )
        StaffImportRow.objects.create(
            job=job,
            row_number=2,
            mobile=mobile,
            status=StaffRowStatus.NEW,
            data={
                "full_name": f"Phase 19 teacher {index}",
                "mobile_masked": f"******04{index}",
                "employee_number": f"PH19-{index}",
                "job_title": "Teacher",
            },
        )
        jobs.append(job)

    barrier = Barrier(2)

    def commit(job_id: int) -> str:
        connections.close_all()
        try:
            barrier.wait(timeout=5)
            try:
                commit_staff_import(job_id=job_id, actor=manager)
            except ApiError as exc:
                return exc.code
            return "COMPLETED"
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(commit, [job.id for job in jobs]))

    assert sorted(outcomes) == ["COMPLETED", "STAFF_LIMIT_EXCEEDED"]
    assert SchoolMembership.objects.filter(school=school).count() == 2


@pytest.mark.django_db(transaction=True)
def test_storage_limit_is_strict_across_concurrent_uploads(
    make_school, make_user, make_membership, monkeypatch
):
    from students.models import Student
    from subscriptions.usage import BYTES_PER_GB

    school = make_school("Phase 19 storage race")
    manager = make_user("0550190051")
    membership = make_membership(manager, school, [SchoolRole.SCHOOL_MANAGER])
    platform_admin = make_user("0550190052", is_staff=True, is_superuser=True)
    plan = plan_service.create_plan(
        actor=platform_admin,
        code="phase19-storage-race",
        name_ar="Phase 19 storage race",
        entitlements={EntitlementKey.MAX_STORAGE_GB: 1},
    )
    subscription_service.activate(school=school, plan_id=plan.id, actor=platform_admin)
    student = Student.objects.create(
        school=school,
        national_id_encrypted="phase19-storage-encrypted",
        national_id_lookup_hash="phase19-storage-hash",
        national_id_masked="**********",
        student_number="PH19-STORAGE",
        full_name="Phase 19 storage student",
    )
    excuses = [
        AbsenceExcuse.objects.create(
            school=school,
            student=student,
            reason_type="MEDICAL",
            notes="",
            recorded_by_membership=membership,
            recorded_at=timezone.now(),
        )
        for _ in range(2)
    ]
    payload = b"%PDF-1.4\n" + (b"x" * 64) + b"\n%%EOF"

    def storage_near_limit(target_school) -> int:
        committed = sum(
            AbsenceExcuseAttachment.objects.filter(school=target_school).values_list(
                "size_bytes", flat=True
            )
        )
        return BYTES_PER_GB - 100 + committed

    monkeypatch.setattr("subscriptions.usage.storage_used_bytes", storage_near_limit)
    barrier = Barrier(2)

    def upload(index: int) -> str:
        connections.close_all()
        try:
            barrier.wait(timeout=5)
            try:
                add_attachment(
                    excuse=excuses[index],
                    school=school,
                    membership=membership,
                    uploaded_file=SimpleUploadedFile(
                        f"phase19-{index}.pdf", payload, content_type="application/pdf"
                    ),
                )
            except ApiError as exc:
                return exc.code
            return "CREATED"
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(upload, range(2)))

    assert sorted(outcomes) == ["CREATED", "STORAGE_LIMIT_EXCEEDED"]
    assert AbsenceExcuseAttachment.objects.filter(school=school).count() == 1


@pytest.mark.django_db(transaction=True)
def test_attendance_submit_creates_one_submission_under_concurrency(
    make_school, make_user, make_membership
):
    school = make_school("Phase 19 attendance submit race")
    teacher = make_user("0550190061")
    make_membership(teacher, school, [SchoolRole.TEACHER])
    environment = setup_attendance_env(school)
    teacher.set_password(PASSWORD)
    teacher.save(update_fields=["password"])
    owner = _login_client(teacher)
    started = owner.post(
        "/api/v1/attendance/sessions/start/",
        {"section_id": environment["section"].id},
        content_type="application/json",
    )
    assert started.status_code == 201
    session_id = started.json()["id"]
    barrier = Barrier(2)

    def submit() -> tuple[int, str]:
        connections.close_all()
        try:
            client = _login_client(teacher)
            barrier.wait(timeout=5)
            response = client.post(
                f"/api/v1/attendance/sessions/{session_id}/submit/",
                {"marks": []},
                content_type="application/json",
            )
            return response.status_code, response.json().get("code", "SUBMITTED")
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _index: submit(), range(2)))

    assert sorted(status for status, _code in outcomes) == [200, 409]
    assert {code for status, code in outcomes if status == 409} == {
        "ATTENDANCE_SESSION_ALREADY_SUBMITTED"
    }
    assert AttendanceSession.objects.get(id=session_id).status == "SUBMITTED"


@pytest.mark.django_db(transaction=True)
def test_excuse_approval_creates_one_coverage_set_under_concurrency(
    make_school, make_user, make_membership
):
    from excuses.models import AbsenceExcuseCoverage
    from excuses.services.coverage import approve_excuse, resolve_coverage_plan
    from tests.excuse_env import build_env, excuse_for, full_day_absent

    school = make_school("Phase 19 excuse approval race")
    teacher_membership = make_membership(
        make_user("0550190071"), school, [SchoolRole.TEACHER]
    )
    vice_membership = make_membership(
        make_user("0550190072"), school, [SchoolRole.VICE_PRINCIPAL]
    )
    environment = build_env(
        school=school,
        teacher_membership=teacher_membership,
        vice_membership=vice_membership,
        prefix="39001",
    )
    student = environment["students"][0]
    full_day_absent(environment, student)
    excuse = excuse_for(
        environment,
        student,
        [{"attendance_date": environment["year"].start_date.replace(day=16)}],
    )
    preview_hash = resolve_coverage_plan(excuse)["preview_hash"]
    barrier = Barrier(2)

    def approve() -> str:
        from memberships.models import SchoolMembership
        from schools.models import School

        connections.close_all()
        try:
            local_school = School.objects.get(id=school.id)
            local_membership = SchoolMembership.objects.select_related("user").get(
                id=vice_membership.id
            )
            barrier.wait(timeout=5)
            try:
                approve_excuse(
                    excuse_id=excuse.id,
                    school=local_school,
                    membership=local_membership,
                    preview_hash=preview_hash,
                )
            except ApiError as exc:
                return exc.code
            return "APPROVED"
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _index: approve(), range(2)))

    assert outcomes.count("APPROVED") == 1
    assert len([code for code in outcomes if code != "APPROVED"]) == 1
    assert AbsenceExcuseCoverage.objects.filter(excuse=excuse).count() == 7


@pytest.mark.django_db(transaction=True)
def test_warning_issue_creates_one_row_under_concurrency(
    make_school, make_user, make_membership
):
    from memberships.models import SchoolMembership
    from schools.models import School
    from student_warnings.models import StudentWarning, WarningLevel, WarningRuleType
    from student_warnings.services.issuance import issue_student_warning
    from students.models import Student
    from tests.excuse_env import build_env
    from tests.test_warnings import absence_days, set_rules

    school = make_school("Phase 19 warning issue race")
    teacher_membership = make_membership(
        make_user("0550190081"), school, [SchoolRole.TEACHER]
    )
    vice_membership = make_membership(
        make_user("0550190082"), school, [SchoolRole.VICE_PRINCIPAL]
    )
    environment = build_env(
        school=school,
        teacher_membership=teacher_membership,
        vice_membership=vice_membership,
        prefix="39002",
    )
    student = environment["students"][0]
    warning_type = WarningRuleType.UNEXCUSED_FULL_DAY_ABSENCE
    set_rules(environment, warning_type, 1, 2, 3)
    absence_days(environment, student, 1)
    barrier = Barrier(2)

    def issue() -> str:
        connections.close_all()
        try:
            local_school = School.objects.get(id=school.id)
            local_membership = SchoolMembership.objects.select_related("user").get(
                id=vice_membership.id
            )
            local_student = Student.objects.get(id=student.id)
            barrier.wait(timeout=5)
            try:
                issue_student_warning(
                    school=local_school,
                    membership=local_membership,
                    student=local_student,
                    warning_type=warning_type,
                    level=WarningLevel.LEVEL_1,
                )
            except ApiError as exc:
                return exc.code
            return "ISSUED"
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _index: issue(), range(2)))

    assert sorted(outcomes) == ["ISSUED", "WARNING_ALREADY_ISSUED"]
    assert StudentWarning.objects.filter(student=student).count() == 1


@pytest.mark.django_db(transaction=True)
def test_case_open_creates_one_row_under_concurrency(
    make_school, make_user, make_membership
):
    from counseling.models import CounselorCase
    from counseling.services.cases import open_counselor_case
    from memberships.models import SchoolMembership
    from referrals.models import ReferralCategory, ReferralReason
    from referrals.services.referrals import acknowledge_referral, create_referral
    from schools.models import School
    from tests.excuse_env import build_env

    school = make_school("Phase 19 case open race")
    teacher_membership = make_membership(
        make_user("0550190091"), school, [SchoolRole.TEACHER]
    )
    vice_membership = make_membership(
        make_user("0550190092"), school, [SchoolRole.VICE_PRINCIPAL]
    )
    counselor_membership = make_membership(
        make_user("0550190093"), school, [SchoolRole.COUNSELOR]
    )
    environment = build_env(
        school=school,
        teacher_membership=teacher_membership,
        vice_membership=vice_membership,
        prefix="39003",
    )
    referral = create_referral(
        school=school,
        membership=vice_membership,
        roles=[SchoolRole.VICE_PRINCIPAL],
        student=environment["students"][0],
        category=ReferralCategory.ATTENDANCE,
        reason_code=ReferralReason.REPEATED_ABSENCE,
        description="Phase 19 synthetic concurrency referral.",
        assigned_counselor_id=counselor_membership.id,
    )
    acknowledge_referral(
        referral_id=referral.id,
        school=school,
        membership=counselor_membership,
        roles=[SchoolRole.COUNSELOR],
    )
    barrier = Barrier(2)

    def open_case() -> str:
        connections.close_all()
        try:
            local_school = School.objects.get(id=school.id)
            local_membership = SchoolMembership.objects.select_related("user").get(
                id=counselor_membership.id
            )
            barrier.wait(timeout=5)
            try:
                open_counselor_case(
                    school=local_school,
                    membership=local_membership,
                    roles=[SchoolRole.COUNSELOR],
                    referral_id=referral.id,
                )
            except ApiError as exc:
                return exc.code
            return "OPENED"
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _index: open_case(), range(2)))

    assert sorted(outcomes) == ["CASE_ALREADY_OPEN", "OPENED"]
    assert CounselorCase.objects.filter(primary_referral=referral).count() == 1
