"""اختبارات المرحلة 4.1: دورة الحياة، الحذف النهائي الفردي والجماعي، الخصوصية."""

from datetime import date

import pytest

from academics.models import AcademicYear, AcademicYearStatus
from audit.models import AuditLog
from common.security.identifiers import (
    encrypt_national_id,
    mask_national_id,
    national_id_lookup_hash,
)
from students.models import (
    EnrollmentStatus,
    Grade,
    PurgeJobStatus,
    Section,
    Student,
    StudentEnrollment,
    StudentPurgeJob,
    StudentStatus,
)
from students.tasks import commit_student_import_job

INACTIVE_URL = "/api/v1/students/inactive/"
BULK_STATUS_URL = "/api/v1/students/bulk-status/"
PREVIEW_URL = "/api/v1/student-purges/preview/"
PURGE_URL = "/api/v1/student-purges/"


def _make_student(school, nid, name, status=StudentStatus.ACTIVE, grade_code="SEC_3"):
    student = Student.objects.create(
        school=school,
        national_id_encrypted=encrypt_national_id(nid),
        national_id_lookup_hash=national_id_lookup_hash(nid),
        national_id_masked=mask_national_id(nid),
        full_name=name,
        status=status,
    )
    year, _ = AcademicYear.objects.get_or_create(
        school=school, name="ع",
        defaults={
            "start_date": date(2026, 8, 23), "end_date": date(2027, 6, 25),
            "status": AcademicYearStatus.ACTIVE,
        },
    )
    grade, _ = Grade.objects.get_or_create(
        school=school, code=grade_code, defaults={"name": grade_code, "sequence": 12}
    )
    section, _ = Section.objects.get_or_create(
        school=school, grade=grade, code="1", defaults={"name": "1"}
    )
    StudentEnrollment.objects.create(
        school=school, student=student, academic_year=year, grade=grade,
        section=section, enrolled_at=date(2026, 8, 23),
        status=EnrollmentStatus.ACTIVE if status == StudentStatus.ACTIVE
        else EnrollmentStatus.COMPLETED,
        ended_at=None if status == StudentStatus.ACTIVE else date.today(),
    )
    return student


# ---------- التصنيف ----------


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("new_status", "expected_enrollment"),
    [
        (StudentStatus.GRADUATED, EnrollmentStatus.COMPLETED),
        (StudentStatus.TRANSFERRED, EnrollmentStatus.TRANSFERRED),
        (StudentStatus.WITHDRAWN, EnrollmentStatus.WITHDRAWN),
    ],
)
def test_status_change_closes_enrollment(role_client, new_status, expected_enrollment):
    client, school, user = role_client(["SCHOOL_MANAGER"])
    student = _make_student(school, "1077000001", "طالب التصنيف")
    response = client.post(
        f"/api/v1/students/{student.id}/status/",
        {"status": new_status, "exit_reason": "اختبار"},
        content_type="application/json",
    )
    assert response.status_code == 200
    student.refresh_from_db()
    assert student.status == new_status
    assert student.exit_date is not None
    assert student.status_changed_by_id == user.id
    enrollment = StudentEnrollment.objects.get(student=student)
    assert enrollment.status == expected_enrollment
    assert enrollment.ended_at is not None
    assert AuditLog.objects.filter(action="STUDENT_STATUS_CHANGED").exists()


@pytest.mark.django_db
def test_graduated_student_leaves_active_lists(role_client):
    client, school, _ = role_client(["SCHOOL_MANAGER"])
    student = _make_student(school, "1077000002", "خريج يختفي")
    client.post(
        f"/api/v1/students/{student.id}/status/",
        {"status": "GRADUATED"},
        content_type="application/json",
    )
    # لا يظهر ضمن النشطين (فلتر status=ACTIVE)
    active = client.get("/api/v1/students/?status=ACTIVE").json()
    assert all(r["id"] != student.id for r in active["results"])
    # يظهر في غير النشطين مع آخر صف/فصل
    inactive = client.get(f"{INACTIVE_URL}?status=GRADUATED").json()
    row = next(r for r in inactive["results"] if r["id"] == student.id)
    assert row["grade"]["name"] == "SEC_3"


@pytest.mark.django_db
def test_bulk_graduate_only_selected_grade(role_client):
    """تخريج دفعة: طلاب الصف المحدد فقط — الآخرون لا يتأثرون."""
    client, school, _ = role_client(["SCHOOL_MANAGER"])
    seniors = [
        _make_student(school, f"10770001{i:02d}", f"ثالث {i}", grade_code="SEC_3")
        for i in range(5)
    ]
    junior = _make_student(school, "1077000299", "أول ثانوي", grade_code="SEC_1")

    response = client.post(
        BULK_STATUS_URL,
        {"student_ids": [s.id for s in seniors], "status": "GRADUATED"},
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json()["updated"] == 5
    for s in seniors:
        s.refresh_from_db()
        assert s.status == StudentStatus.GRADUATED
        assert StudentEnrollment.objects.get(student=s).status == EnrollmentStatus.COMPLETED
    junior.refresh_from_db()
    assert junior.status == StudentStatus.ACTIVE


@pytest.mark.django_db
def test_bulk_status_mixed_tenant_rejected_entirely(role_client):
    """معرف أجنبي واحد في التحديد → العملية كلها ترفض (البند 33)."""
    manager_a, school_a, _ = role_client(["SCHOOL_MANAGER"])
    _, school_b, _ = role_client(["SCHOOL_MANAGER"])
    mine = _make_student(school_a, "1077000301", "طالبي")
    foreign = _make_student(school_b, "1077000302", "أجنبي")

    response = manager_a.post(
        BULK_STATUS_URL,
        {"student_ids": [mine.id, foreign.id], "status": "TRANSFERRED"},
        content_type="application/json",
    )
    assert response.status_code == 404
    assert response.json()["code"] == "STUDENT_NOT_FOUND"
    mine.refresh_from_db()
    assert mine.status == StudentStatus.ACTIVE  # لم يتغير شيء


@pytest.mark.django_db
def test_missing_last_import_filter(role_client):
    from tests.xlsx_helper import build_xlsx_upload, noor_row

    client, school, _ = role_client(["SCHOOL_MANAGER"])
    AcademicYear.objects.create(
        school=school, name="سنة", start_date=date(2026, 8, 23),
        end_date=date(2027, 6, 25), status=AcademicYearStatus.ACTIVE,
    )
    # استيراد طالبين ثم ملف جديد بواحد فقط
    job1 = client.post(
        "/api/v1/student-imports/",
        {"file": build_xlsx_upload([
            noor_row("1077000401", "باقٍ في الملف"),
            noor_row("1077000402", "مفقود من الملف"),
        ])},
    ).json()
    client.post(f"/api/v1/student-imports/{job1['id']}/process/", {},
                content_type="application/json")
    client.post(f"/api/v1/student-imports/{job1['id']}/commit/")
    commit_student_import_job(job1["id"])
    job2 = client.post(
        "/api/v1/student-imports/",
        {"file": build_xlsx_upload([noor_row("1077000401", "باقٍ في الملف")])},
    ).json()
    client.post(f"/api/v1/student-imports/{job2['id']}/process/", {},
                content_type="application/json")
    client.post(f"/api/v1/student-imports/{job2['id']}/commit/")
    commit_student_import_job(job2["id"])

    body = client.get(f"{INACTIVE_URL}?missing_last_import=1").json()
    names = [r["full_name"] for r in body["results"]]
    assert "مفقود من الملف" in names
    assert "باقٍ في الملف" not in names
    # ولم يحذف أحد
    assert Student.objects.filter(school=school).count() == 2


@pytest.mark.django_db
def test_missing_last_import_filter_is_not_truncated(role_client):
    """قائمة الأسماء تقتطع للعرض؛ الفلتر يعتمد المعرفات الكاملة.

    الاعتماد على القائمة المقتطعة كان يخفي طلابًا فعليين في مدرسة يتجاوز فيها
    المفقودون حد الاقتطاع (ظهر في مدرسة تطوير تجاوزت 500 طالب).
    """
    from students.models import ImportJobStatus, StudentImportJob

    client, school, _ = role_client(["SCHOOL_MANAGER"])
    year = AcademicYear.objects.create(
        school=school, name="سنة الاقتطاع", start_date=date(2026, 8, 23),
        end_date=date(2027, 6, 25), status=AcademicYearStatus.ACTIVE,
    )
    student = Student.objects.create(
        school=school,
        full_name="طالب خارج حد الاقتطاع",
        national_id_encrypted="x",
        national_id_lookup_hash="h-truncation",
        national_id_masked="******9999",
        status=StudentStatus.ACTIVE,
    )
    StudentImportJob.objects.create(
        school=school,
        status=ImportJobStatus.COMPLETED,
        original_filename="noor.xlsx",
        uploaded_by=school.memberships.first().user,
        academic_year=year,
        summary={
            # الأسماء مقتطعة ولا تحوي الطالب — المعرفات الكاملة تحويه
            "missing_names": [{"student_id": student.id + 10_000, "name": "طالب آخر"}],
            "missing_ids": [student.id],
        },
    )

    body = client.get(f"{INACTIVE_URL}?missing_last_import=1").json()
    assert [r["full_name"] for r in body["results"]] == ["طالب خارج حد الاقتطاع"]


# ---------- الحذف الفردي ----------


@pytest.mark.django_db
def test_individual_purge_deletes_everything(role_client):
    client, school, _ = role_client(["SCHOOL_MANAGER"])
    student = _make_student(school, "1077000501", "محذوف", status=StudentStatus.GRADUATED)
    student_id = student.id
    response = client.post(f"/api/v1/students/{student_id}/purge/")
    assert response.status_code == 200
    body = response.json()
    assert body["deleted"] is True
    assert body["database_records"] >= 2  # الطالب + قيده
    assert not Student.objects.filter(id=student_id).exists()
    assert not StudentEnrollment.objects.filter(student_id=student_id).exists()
    # Audit بلا PII
    log = AuditLog.objects.get(action="STUDENT_PERMANENTLY_PURGED")
    text = str(log.metadata)
    assert "محذوف" not in text
    assert "1077000501" not in text
    assert log.target_id == ""  # لا معرف قابل للربط


@pytest.mark.django_db
def test_active_student_cannot_be_purged(role_client):
    client, school, _ = role_client(["SCHOOL_MANAGER"])
    student = _make_student(school, "1077000502", "نشط محمي")
    response = client.post(f"/api/v1/students/{student.id}/purge/")
    assert response.status_code == 409
    assert response.json()["code"] == "STUDENT_ACTIVE_CANNOT_PURGE"
    assert Student.objects.filter(id=student.id).exists()


@pytest.mark.django_db
def test_purge_permissions_matrix(role_client, make_school):
    school = make_school()
    manager, _, _ = role_client(["SCHOOL_MANAGER"], school=school)
    student = _make_student(school, "1077000503", "للحذف", status=StudentStatus.GRADUATED)
    for roles in (["VICE_PRINCIPAL"], ["COUNSELOR"], ["TEACHER"]):
        client, _, _ = role_client(roles, school=school)
        assert client.post(f"/api/v1/students/{student.id}/purge/").status_code == 403
        assert client.post(
            PREVIEW_URL, {"student_ids": [student.id]}, content_type="application/json"
        ).status_code == 403
    assert manager.post(f"/api/v1/students/{student.id}/purge/").status_code == 200


@pytest.mark.django_db
def test_purge_tenant_isolation(role_client):
    manager_a, _, _ = role_client(["SCHOOL_MANAGER"])
    _, school_b, _ = role_client(["SCHOOL_MANAGER"])
    foreign = _make_student(school_b, "1077000504", "أجنبي", status=StudentStatus.GRADUATED)
    assert manager_a.post(f"/api/v1/students/{foreign.id}/purge/").status_code == 404
    preview = manager_a.post(
        PREVIEW_URL, {"student_ids": [foreign.id]}, content_type="application/json"
    )
    assert preview.status_code == 404
    assert Student.objects.filter(id=foreign.id).exists()


# ---------- الحذف الجماعي ----------


def _bulk_purge_flow(client, student_ids, reason=""):
    preview = client.post(
        PREVIEW_URL, {"student_ids": student_ids}, content_type="application/json"
    )
    assert preview.status_code == 200
    token = preview.json()["confirmation_token"]
    return preview.json(), client.post(
        PURGE_URL,
        {"confirmation_token": token, "reason": reason},
        content_type="application/json",
    )


@pytest.mark.django_db
def test_bulk_purge_graduated_and_transferred_only(role_client):
    """تحديد GRADUATED+TRANSFERRED يحذفهم فقط — المنسحبون يبقون (البند 51)."""
    client, school, _ = role_client(["SCHOOL_MANAGER"])
    graduated = [
        _make_student(school, f"10770006{i:02d}", f"خريج {i}", StudentStatus.GRADUATED)
        for i in range(4)
    ]
    transferred = [
        _make_student(school, f"10770007{i:02d}", f"منتقل {i}", StudentStatus.TRANSFERRED)
        for i in range(2)
    ]
    withdrawn = _make_student(school, "1077000801", "منسحب باقٍ", StudentStatus.WITHDRAWN)

    ids = [s.id for s in graduated + transferred]
    preview_body, response = _bulk_purge_flow(client, ids, reason="GRADUATED+TRANSFERRED")
    assert preview_body["summary"]["students"] == 6
    assert preview_body["summary"]["database_records"] >= 12
    assert response.status_code == 202

    job = StudentPurgeJob.objects.get(school=school)
    # CELERY_TASK_ALWAYS_EAGER: نفذت فورًا
    job.refresh_from_db()
    assert job.status == PurgeJobStatus.COMPLETED
    assert job.deleted_students == 6
    assert job.student_ids == []  # الخصوصية: المعرفات مسحت
    assert Student.objects.filter(id__in=ids).count() == 0
    assert Student.objects.filter(id=withdrawn.id).exists()

    log = AuditLog.objects.get(action="STUDENT_BULK_PURGE_COMPLETED")
    assert log.metadata["students"] == 6
    assert "خريج" not in str(log.metadata)


@pytest.mark.django_db
def test_purge_preview_stale_on_status_change(role_client):
    client, school, _ = role_client(["SCHOOL_MANAGER"])
    student = _make_student(school, "1077000901", "متقلب", StudentStatus.GRADUATED)
    preview = client.post(
        PREVIEW_URL, {"student_ids": [student.id]}, content_type="application/json"
    ).json()

    # الحالة تتغير بعد المعاينة
    student.status = StudentStatus.ACTIVE
    student.save(update_fields=["status"])

    response = client.post(
        PURGE_URL,
        {"confirmation_token": preview["confirmation_token"]},
        content_type="application/json",
    )
    assert response.status_code == 409
    assert response.json()["code"] == "PURGE_PREVIEW_STALE"
    assert Student.objects.filter(id=student.id).exists()


@pytest.mark.django_db
def test_purge_token_single_use_and_invalid(role_client):
    client, school, _ = role_client(["SCHOOL_MANAGER"])
    student = _make_student(school, "1077000902", "مرة واحدة", StudentStatus.GRADUATED)
    _, first = _bulk_purge_flow(client, [student.id])
    assert first.status_code == 202
    # نفس الـ token مرة ثانية → مرفوض (استخدم ومسح)
    second = client.post(
        PURGE_URL,
        {"confirmation_token": "invalid-or-used-token"},
        content_type="application/json",
    )
    assert second.status_code == 409
    assert second.json()["code"] == "PURGE_PREVIEW_STALE"


@pytest.mark.django_db
def test_purge_idempotency_after_deletion(role_client):
    """حذف طالب محذوف: لا أخطاء غير مضبوطة ولا مساس بمستأجر آخر."""
    client, school, _ = role_client(["SCHOOL_MANAGER"])
    student = _make_student(school, "1077000903", "محذوف مسبقًا", StudentStatus.GRADUATED)
    student_id = student.id
    client.post(f"/api/v1/students/{student_id}/purge/")
    again = client.post(f"/api/v1/students/{student_id}/purge/")
    assert again.status_code == 404  # غير موجود — رد مضبوط


@pytest.mark.django_db
def test_storage_cleanup_mechanism_and_failure_handling(role_client, monkeypatch):
    """آلية حذف التخزين: نجاح يحسب، وفشل → PARTIALLY_FAILED (لا ادعاء COMPLETED)."""
    from students.services import purge as purge_service

    client, school, _ = role_client(["SCHOOL_MANAGER"])
    ok_student = _make_student(school, "1077001001", "ملفاته سليمة", StudentStatus.GRADUATED)
    bad_student = _make_student(school, "1077001002", "ملفاته عالقة", StudentStatus.GRADUATED)

    class FakeFile:
        def __init__(self, fail: bool):
            self.fail = fail
            self.deleted = False

        def delete(self, save=False):
            if self.fail:
                raise OSError("storage unavailable")
            self.deleted = True

    files = {ok_student.id: FakeFile(fail=False), bad_student.id: FakeFile(fail=True)}

    def collector(student):
        f = files.get(student.id)
        return [f] if f else []

    monkeypatch.setattr(purge_service, "PURGE_STORAGE_COLLECTORS", [collector])

    _, response = _bulk_purge_flow(client, [ok_student.id, bad_student.id])
    assert response.status_code == 202
    job = StudentPurgeJob.objects.get(school=school)
    assert job.status == PurgeJobStatus.PARTIALLY_FAILED  # ملف لم ينظف
    assert job.storage_objects_deleted == 1
    assert job.storage_objects_failed == 1
    assert files[ok_student.id].deleted is True
    # صفوف DB حذفت رغم فشل ملف (يتنظف لاحقًا — موثق)
    assert not Student.objects.filter(
        id__in=[ok_student.id, bad_student.id]
    ).exists()


@pytest.mark.django_db
def test_concurrent_purge_job_blocked(role_client):
    client, school, _ = role_client(["SCHOOL_MANAGER"])
    s1 = _make_student(school, "1077001101", "أول", StudentStatus.GRADUATED)
    StudentPurgeJob.objects.create(
        school=school, created_by=school.memberships.first().user,
        status=PurgeJobStatus.RUNNING, student_ids=[999], total_students=1,
    )
    response = client.post(
        PREVIEW_URL, {"student_ids": [s1.id]}, content_type="application/json"
    )
    assert response.status_code == 409
    assert response.json()["code"] == "PURGE_ALREADY_RUNNING"
