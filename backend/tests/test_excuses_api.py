"""اختبارات API الأعذار (م10): سير العمل، الصلاحيات، العزل بين المدارس، المرفقات."""

import io
from datetime import datetime, time, timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from PIL import Image

from academics.models import (
    AcademicYear,
    AcademicYearStatus,
    BellPeriod,
    BellSchedule,
    SchoolWeekDay,
    Weekday,
)
from attendance.models import AttendanceMark, AttendanceMarkStatus, DailyAttendanceSummary
from attendance.services.day_context import get_or_create_attendance_day_context
from attendance.services.sessions import get_roster, roster_fingerprint, submit_session
from audit.models import AuditAction, AuditLog
from excuses.models import AbsenceExcuseAttachment, AbsenceExcuseCoverage
from students.models import Grade, Section, StudentEnrollment
from tests.attendance_helpers import make_students
from tests.test_excuses import (
    DAY,
    PERIOD_COUNT,
    full_day_absent,
    make_session,
)

BASE = "/api/v1/excuses/"

VALID_PDF = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n%%EOF\n"


def _image_bytes(fmt: str) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (12, 12), "white").save(buffer, format=fmt)
    return buffer.getvalue()


def _build_env(school, make_user, make_membership, prefix="40100"):
    year = AcademicYear.objects.create(
        school=school, name="2026/2027", start_date=datetime(2026, 8, 1).date(),
        end_date=datetime(2027, 6, 25).date(), status=AcademicYearStatus.ACTIVE,
    )
    schedule = BellSchedule.objects.create(school=school, name="سبع حصص")
    for i in range(PERIOD_COUNT):
        BellPeriod.objects.create(
            school=school, bell_schedule=schedule, sequence=i + 1,
            name=f"الحصة {i + 1}", start_time=time(7 + i, 0), end_time=time(7 + i, 45),
        )
    SchoolWeekDay.objects.create(
        school=school, weekday=Weekday.SUNDAY, is_school_day=True, bell_schedule=schedule
    )
    grade = Grade.objects.create(school=school, name="الأول الثانوي", code="G1", sequence=1)
    section = Section.objects.create(school=school, grade=grade, code="1", name="1")
    students = make_students(school, section, year, 2, prefix=prefix)
    teacher = make_membership(make_user(f"055000{prefix[:4]}"), school, ["TEACHER"])
    return {
        "school": school, "year": year, "grade": grade, "section": section,
        "students": students, "teacher": teacher,
    }


@pytest.fixture(autouse=True)
def _isolated_media(tmp_path, settings):
    """مرفقات الاختبارات في مجلد مؤقت — لا تلوث backend/mediafiles."""
    settings.MEDIA_ROOT = tmp_path / "media"
    return settings.MEDIA_ROOT


@pytest.fixture
def api_env(role_client, make_user, make_membership):
    client, school, user = role_client(["VICE_PRINCIPAL"])
    env = _build_env(school, make_user, make_membership)
    env["client"] = client
    env["vice"] = user.memberships.get(school=school)
    return env


def _create_excuse(client, student, targets=None, reason="MEDICAL_REPORT"):
    return client.post(
        BASE,
        {
            "student_id": student.id,
            "reason_type": reason,
            "notes": "",
            "targets": targets or [{"attendance_date": DAY.isoformat()}],
        },
        content_type="application/json",
    )


def _approve(client, excuse_id):
    preview = client.post(f"{BASE}{excuse_id}/preview/")
    assert preview.status_code == 200
    return client.post(
        f"{BASE}{excuse_id}/approve/",
        {"preview_hash": preview.json()["preview_hash"]},
        content_type="application/json",
    )


# ---------- سير العمل الكامل ----------


@pytest.mark.django_db
def test_create_approves_and_covers_recorded_absence_immediately(api_env):
    client, student = api_env["client"], api_env["students"][0]
    full_day_absent(api_env, student)

    created = _create_excuse(client, student)
    assert created.status_code == 201
    excuse_id = created.json()["id"]
    detail = created.json()
    assert detail["status"] == "APPROVED"
    assert detail["active_coverage_count"] == PERIOD_COUNT
    assert detail["approved_by_name"] is not None
    assert client.post(f"{BASE}{excuse_id}/preview/").status_code == 409

    kpis = client.get(f"{BASE}kpis/").json()
    assert kpis["approved_today_count"] == 1
    assert kpis["pending_count"] == 0

    assert AuditLog.objects.filter(action=AuditAction.EXCUSE_APPROVED).exists()
    assert AuditLog.objects.filter(action=AuditAction.EXCUSE_CREATED).exists()


@pytest.mark.django_db
def test_future_three_day_excuse_covers_absence_when_session_is_submitted(api_env, monkeypatch):
    """إنشاء مسبق لا يغير الحضور؛ اعتماد الحصة لاحقًا يضيف التغطية والملخص."""
    from zoneinfo import ZoneInfo

    monkeypatch.setattr(
        "excuses.services.excuses.school_now",
        lambda _school: datetime(2026, 8, 19, 10, tzinfo=ZoneInfo("Asia/Riyadh")),
    )
    client, student = api_env["client"], api_env["students"][0]
    future_day = DAY + timedelta(days=7)  # الأحد 2026-08-23
    targets = [
        {"attendance_date": (future_day + timedelta(days=offset)).isoformat()}
        for offset in range(3)
    ]
    created = _create_excuse(client, student, targets=targets)
    assert created.status_code == 201, created.content
    excuse_id = created.json()["id"]
    assert created.json()["status"] == "APPROVED"
    assert created.json()["active_coverage_count"] == 0

    session = make_session(api_env, 1, day=future_day, status="IN_PROGRESS")
    session.roster_fingerprint = roster_fingerprint(get_roster(
        school=api_env["school"], section=api_env["section"],
        academic_year=api_env["year"],
    ))
    session.save(update_fields=["roster_fingerprint"])
    submit_session(
        session_id=session.id, school=api_env["school"],
        membership=api_env["teacher"],
        marks=[{"student_id": student.id, "status": "ABSENT"}],
    )

    assert (
        AttendanceMark.objects.get(session=session, student=student).status
        == AttendanceMarkStatus.ABSENT
    )
    assert AbsenceExcuseCoverage.objects.filter(
        excuse_id=excuse_id, attendance_session=session, status="ACTIVE",
    ).exists()
    summary = DailyAttendanceSummary.objects.get(student=student, attendance_date=future_day)
    assert summary.excused_absent_periods == 1
    assert summary.unexcused_absent_periods == 0


@pytest.mark.django_db
def test_overlapping_approved_targets_are_rejected_but_cancelled_targets_can_be_reused(api_env):
    client, student = api_env["client"], api_env["students"][0]
    first = _create_excuse(client, student)
    assert first.status_code == 201
    duplicate = _create_excuse(client, student)
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "EXCUSE_TARGET_ALREADY_COVERED"
    assert client.post(
        f"{BASE}{first.json()['id']}/cancel/", {"reason": "تصحيح"},
        content_type="application/json",
    ).status_code == 200
    assert _create_excuse(client, student).status_code == 201


@pytest.mark.django_db
def test_excuse_date_must_belong_to_school_year_and_student_enrollment(api_env):
    client, student = api_env["client"], api_env["students"][0]
    outside = _create_excuse(
        client, student, targets=[{"attendance_date": "2025-08-16"}],
    )
    assert outside.status_code == 400
    assert outside.json()["code"] == "EXCUSE_DATE_OUTSIDE_ACADEMIC_YEAR"

    student.enrollments.update(enrolled_at=DAY + timedelta(days=1))
    before_enrollment = _create_excuse(client, student)
    assert before_enrollment.status_code == 400
    assert before_enrollment.json()["code"] == "EXCUSE_STUDENT_NOT_ENROLLED_ON_DATE"

    # استيراد الطالب المتأخر لا يمنع عذرًا ليوم غياب مُسجل بالفعل.
    full_day_absent(api_env, student)
    recorded_absence = _create_excuse(client, student)
    assert recorded_absence.status_code == 201, recorded_absence.content
    assert recorded_absence.json()["status"] == "APPROVED"


@pytest.mark.django_db
def test_old_year_context_does_not_inherit_active_year_schedule(api_env):
    prior_year = AcademicYear.objects.create(
        school=api_env["school"], name="2025/2026",
        start_date=datetime(2025, 8, 1).date(),
        end_date=datetime(2026, 6, 25).date(),
        status=AcademicYearStatus.CLOSED,
    )
    context = get_or_create_attendance_day_context(
        school=api_env["school"], attendance_date=datetime(2025, 8, 17).date(),
    )
    assert context.academic_year_id == prior_year.id
    assert context.attendance_periods == []


@pytest.mark.django_db
def test_past_excuse_is_allowed_for_student_historical_enrollment(api_env):
    prior_year = AcademicYear.objects.create(
        school=api_env["school"], name="2025/2026",
        start_date=datetime(2025, 8, 1).date(),
        end_date=datetime(2026, 6, 25).date(),
        status=AcademicYearStatus.CLOSED,
    )
    student = api_env["students"][0]
    StudentEnrollment.objects.create(
        school=api_env["school"], student=student, academic_year=prior_year,
        grade=api_env["grade"], section=api_env["section"],
        status="COMPLETED", enrolled_at=datetime(2025, 8, 1).date(),
        ended_at=datetime(2026, 6, 25).date(),
    )
    created = _create_excuse(
        api_env["client"], student,
        targets=[{"attendance_date": "2025-08-17"}],
    )
    assert created.status_code == 201, created.content
    assert created.json()["status"] == "APPROVED"
    assert created.json()["active_coverage_count"] == 0


@pytest.mark.django_db
def test_list_filters(api_env):
    client = api_env["client"]
    s1, s2 = api_env["students"]
    full_day_absent(api_env, s1)
    _create_excuse(client, s1)
    _create_excuse(client, s2, reason="FAMILY")

    all_rows = client.get(BASE).json()
    assert all_rows["count"] == 2

    by_student = client.get(f"{BASE}?student={s1.id}").json()
    assert by_student["count"] == 1
    assert by_student["results"][0]["student"]["id"] == s1.id

    by_reason = client.get(f"{BASE}?reason_type=FAMILY").json()
    assert by_reason["count"] == 1

    by_status = client.get(f"{BASE}?status=APPROVED").json()
    assert by_status["count"] == 2

    by_grade = client.get(f"{BASE}?grade={api_env['grade'].id}").json()
    assert by_grade["count"] == 2


@pytest.mark.django_db
def test_patch_pending_only(api_env):
    client, student = api_env["client"], api_env["students"][0]
    full_day_absent(api_env, student)
    from excuses.services.excuses import create_excuse

    excuse_id = create_excuse(
        school=api_env["school"], membership=api_env["vice"], student=student,
        reason_type="MEDICAL_REPORT", notes="", targets=[{"attendance_date": DAY}],
    ).id

    patched = client.patch(
        f"{BASE}{excuse_id}/", {"notes": "ملاحظة"}, content_type="application/json"
    )
    assert patched.status_code == 200
    assert patched.json()["notes"] == "ملاحظة"

    assert _approve(client, excuse_id).status_code == 200
    denied = client.patch(
        f"{BASE}{excuse_id}/", {"notes": "بعد الاعتماد"}, content_type="application/json"
    )
    assert denied.status_code == 409
    assert denied.json()["code"] == "EXCUSE_ALREADY_APPROVED"


@pytest.mark.django_db
def test_reject_requires_reason(api_env):
    client, student = api_env["client"], api_env["students"][0]
    from excuses.services.excuses import create_excuse

    excuse_id = create_excuse(
        school=api_env["school"], membership=api_env["vice"], student=student,
        reason_type="MEDICAL_REPORT", notes="", targets=[{"attendance_date": DAY}],
    ).id
    missing = client.post(f"{BASE}{excuse_id}/reject/", {}, content_type="application/json")
    assert missing.status_code == 400
    rejected = client.post(
        f"{BASE}{excuse_id}/reject/", {"reason": "بلا مستند"},
        content_type="application/json",
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "REJECTED"
    assert rejected.json()["rejection_reason"] == "بلا مستند"


@pytest.mark.django_db
def test_cancel_endpoint(api_env):
    client, student = api_env["client"], api_env["students"][0]
    full_day_absent(api_env, student)
    excuse_id = _create_excuse(client, student).json()["id"]
    cancelled = client.post(
        f"{BASE}{excuse_id}/cancel/", {"reason": "خطأ"}, content_type="application/json"
    )
    assert cancelled.status_code == 200
    body = cancelled.json()
    assert body["status"] == "CANCELLED"
    assert body["active_coverage_count"] == 0
    assert all(c["status"] == "VOIDED" for c in body["coverages"])


# ---------- الصلاحيات (البنود 144-148) ----------


@pytest.mark.django_db
def test_manager_full_access(role_client, make_user, make_membership):
    client, school, _ = role_client(["SCHOOL_MANAGER"])
    env = _build_env(school, make_user, make_membership, prefix="40200")
    student = env["students"][0]
    full_day_absent(env, student)
    excuse_id = _create_excuse(client, student).json()["id"]
    assert client.get(f"{BASE}{excuse_id}/").json()["status"] == "APPROVED"


@pytest.mark.django_db
def test_counselor_read_only(role_client, make_user, make_membership):
    client, school, _ = role_client(["COUNSELOR"])
    env = _build_env(school, make_user, make_membership, prefix="40300")
    student = env["students"][0]

    assert client.get(BASE).status_code == 200
    assert client.get(f"{BASE}kpis/").status_code == 200
    denied = _create_excuse(client, student)
    assert denied.status_code == 403
    assert client.post(f"{BASE}1/preview/").status_code == 403
    assert client.post(
        f"{BASE}1/approve/", {"preview_hash": "x"}, content_type="application/json"
    ).status_code == 403


@pytest.mark.django_db
def test_teacher_denied(role_client):
    client, _, _ = role_client(["TEACHER"])
    assert client.get(BASE).status_code == 403
    assert client.get(f"{BASE}kpis/").status_code == 403
    assert client.post(BASE, {}, content_type="application/json").status_code == 403


@pytest.mark.django_db
def test_multi_school_role(api_env, make_school, make_membership, make_user):
    """‏VP في مدرسة A ومعلم في B: الإدارة في A فقط (بند 148)."""
    client = api_env["client"]
    school_b = make_school()
    user = api_env["vice"].user
    make_membership(user, school_b, ["TEACHER"])

    assert client.get(BASE).status_code == 200  # في A
    switched = client.post(
        "/api/v1/session/active-school/", {"school_id": school_b.id},
        content_type="application/json",
    )
    assert switched.status_code == 200
    assert client.get(BASE).status_code == 403  # في B معلم — لا وصول


# ---------- العزل بين المدارس / IDOR (البنود 149-150) ----------


@pytest.mark.django_db
def test_tenant_isolation(api_env, role_client, make_user, make_membership):
    client_a = api_env["client"]
    client_b, school_b, _ = role_client(["SCHOOL_MANAGER"])
    env_b = _build_env(school_b, make_user, make_membership, prefix="40400")
    student_b = env_b["students"][0]
    full_day_absent(env_b, student_b)
    excuse_b_id = _create_excuse(client_b, student_b).json()["id"]

    # مدير A لا يرى ولا يدير عذر B — ‏404 دائمًا لا 403 (لا تسريب وجود)
    assert client_a.get(f"{BASE}{excuse_b_id}/").status_code == 404
    assert client_a.post(f"{BASE}{excuse_b_id}/preview/").status_code == 404
    assert client_a.post(
        f"{BASE}{excuse_b_id}/approve/", {"preview_hash": "x"},
        content_type="application/json",
    ).status_code == 404
    assert client_a.post(
        f"{BASE}{excuse_b_id}/reject/", {"reason": "x"}, content_type="application/json"
    ).status_code == 404
    assert client_a.post(
        f"{BASE}{excuse_b_id}/cancel/", {"reason": "x"}, content_type="application/json"
    ).status_code == 404

    # إنشاء عذر لطالب من مدرسة أخرى → 404
    cross = _create_excuse(client_a, student_b)
    assert cross.status_code == 404


# ---------- المرفقات (البنود 141-143) ----------


def _upload(client, excuse_id, name, content):
    return client.post(
        f"{BASE}{excuse_id}/attachments/",
        {"file": SimpleUploadedFile(name, content)},
    )


@pytest.mark.django_db
def test_attachment_valid_types(api_env):
    client, student = api_env["client"], api_env["students"][0]
    excuse_id = _create_excuse(client, student).json()["id"]

    for name, content, mime in [
        ("report.pdf", VALID_PDF, "application/pdf"),
        ("photo.jpg", _image_bytes("JPEG"), "image/jpeg"),
        ("scan.png", _image_bytes("PNG"), "image/png"),
    ]:
        response = _upload(client, excuse_id, name, content)
        assert response.status_code == 201, response.content
        assert response.json()["mime_type"] == mime
        assert response.json()["original_filename"] == name

    detail = client.get(f"{BASE}{excuse_id}/").json()
    assert len(detail["attachments"]) == 3
    assert AuditLog.objects.filter(
        action=AuditAction.EXCUSE_ATTACHMENT_UPLOADED
    ).count() == 3


@pytest.mark.django_db
def test_attachment_invalid_files(api_env):
    client, student = api_env["client"], api_env["students"][0]
    excuse_id = _create_excuse(client, student).json()["id"]

    cases = [
        ("note.txt", b"plain text"),                     # امتداد غير مدعوم
        ("fake.pdf", b"this is not a pdf at all"),       # ‏PDF مزيف
        ("broken.png", b"\x89PNG\r\n\x1a\nbroken"),      # صورة تالفة
        ("bmp.png", _bmp_bytes()),                        # محتوى لا يطابق الامتداد
        ("script.gif", _image_bytes("PNG")),             # امتداد ممنوع
    ]
    for name, content in cases:
        response = _upload(client, excuse_id, name, content)
        assert response.status_code == 400, name
        assert response.json()["code"] == "EXCUSE_ATTACHMENT_INVALID", name
    assert not AbsenceExcuseAttachment.objects.exists()


def _bmp_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (5, 5)).save(buffer, format="BMP")
    return buffer.getvalue()


@pytest.mark.django_db
@override_settings(EXCUSE_ATTACHMENT_MAX_FILE_BYTES=64)
def test_attachment_oversized(api_env):
    client, student = api_env["client"], api_env["students"][0]
    excuse_id = _create_excuse(client, student).json()["id"]
    response = _upload(client, excuse_id, "big.pdf", VALID_PDF + b"x" * 100)
    assert response.status_code == 400
    assert response.json()["code"] == "EXCUSE_ATTACHMENT_TOO_LARGE"


@pytest.mark.django_db
def test_attachment_download_permissions(api_env, role_client, make_user, make_membership):
    client, school, student = api_env["client"], api_env["school"], api_env["students"][0]
    excuse_id = _create_excuse(client, student).json()["id"]
    attachment_id = _upload(client, excuse_id, "report.pdf", VALID_PDF).json()["id"]
    url = f"{BASE}{excuse_id}/attachments/{attachment_id}/"

    # الوكيل (صاحب المدرسة) يفتح المرفق
    download = client.get(url)
    assert download.status_code == 200
    assert b"".join(download.streaming_content) == VALID_PDF
    assert "attachment" in download["Content-Disposition"]

    # المرشد: metadata نعم، تنزيل لا (بند 99)
    counselor, _, _ = role_client(["COUNSELOR"], school=school)
    assert counselor.get(f"{BASE}{excuse_id}/").status_code == 200
    assert counselor.get(url).status_code == 403

    # المعلم: لا شيء
    teacher, _, _ = role_client(["TEACHER"], school=school)
    assert teacher.get(url).status_code == 403

    # مدرسة أجنبية: 404
    foreign, _, _ = role_client(["SCHOOL_MANAGER"])
    assert foreign.get(url).status_code == 404


@pytest.mark.django_db
def test_attachment_delete_rules(api_env):
    client, student = api_env["client"], api_env["students"][0]
    full_day_absent(api_env, student)
    excuse_id = _create_excuse(client, student).json()["id"]
    attachment_id = _upload(client, excuse_id, "report.pdf", VALID_PDF).json()["id"]

    deleted = client.delete(f"{BASE}{excuse_id}/attachments/{attachment_id}/")
    assert deleted.status_code == 204
    assert not AbsenceExcuseAttachment.objects.exists()

    # الاعتماد فوري؛ يمكن تصحيح المرفقات حتى الإلغاء.
    attachment_id = _upload(client, excuse_id, "report.pdf", VALID_PDF).json()["id"]
    assert client.delete(f"{BASE}{excuse_id}/attachments/{attachment_id}/").status_code == 204
    attachment_id = _upload(client, excuse_id, "report.pdf", VALID_PDF).json()["id"]
    assert client.post(
        f"{BASE}{excuse_id}/cancel/", {"reason": "خطأ"},
        content_type="application/json",
    ).status_code == 200
    denied = client.delete(f"{BASE}{excuse_id}/attachments/{attachment_id}/")
    assert denied.status_code == 409


@pytest.mark.django_db
def test_purge_removes_attachment_files(api_env):
    from django.core.files.storage import default_storage

    from students.services.purge import purge_student

    client, student = api_env["client"], api_env["students"][0]
    excuse_id = _create_excuse(client, student).json()["id"]
    _upload(client, excuse_id, "report.pdf", VALID_PDF)
    storage_name = AbsenceExcuseAttachment.objects.get().file.name
    assert default_storage.exists(storage_name)

    student.status = "WITHDRAWN"
    student.save(update_fields=["status"])
    _, storage_ok, storage_failed = purge_student(student)
    assert storage_ok == 1
    assert storage_failed == 0
    assert not default_storage.exists(storage_name)
    assert not AbsenceExcuseAttachment.objects.exists()


# ---------- ‏Mass assignment (بند 96) ----------


@pytest.mark.django_db
def test_invalid_date_filter_returns_400_not_500(api_env):
    client = api_env["client"]
    for query in ("?from_date=abc", "?to_date=2026-13-45"):
        response = client.get(f"{BASE}{query}")
        assert response.status_code == 400, query
        assert response.json()["code"] == "VALIDATION_ERROR"


@pytest.mark.django_db
def test_pdf_signature_must_be_at_start(api_env):
    """ملف HTML يحوي %PDF- عرضًا داخل أول كيلوبايت يرفض."""
    client, student = api_env["client"], api_env["students"][0]
    excuse_id = _create_excuse(client, student).json()["id"]
    disguised = b"<html><body>%PDF-1.4 not really</body></html>" + b"x" * 100 + b"%%EOF"
    response = _upload(client, excuse_id, "fake.pdf", disguised)
    assert response.status_code == 400
    assert response.json()["code"] == "EXCUSE_ATTACHMENT_INVALID"


@pytest.mark.django_db
def test_patch_cannot_set_status_or_school(api_env):
    client, student = api_env["client"], api_env["students"][0]
    excuse_id = _create_excuse(client, student).json()["id"]
    response = client.patch(
        f"{BASE}{excuse_id}/",
        {"status": "PENDING", "school": 999, "approved_by_membership": 1},
        content_type="application/json",
    )
    assert response.status_code == 409
    detail = client.get(f"{BASE}{excuse_id}/").json()
    assert detail["status"] == "APPROVED"
