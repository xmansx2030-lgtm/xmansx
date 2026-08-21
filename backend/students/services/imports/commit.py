"""اعتماد الاستيراد — ذري، Idempotent، محمي من stale preview.

السياسة (UPDATE_OR_CREATE):
- جديد → إنشاء طالب + قيد. موجود بتغير بيانات → تحديث + Audit. انتقال فصل/صف →
  إنهاء القيد القديم (ended_at + TRANSFERRED) وإنشاء قيد جديد — التاريخ لا يحذف.
- المفقودون من الملف: عرض في الملخص فقط — لا حذف ولا تعطيل تلقائي.
- الحماية: select_for_update على الـ Job + حالة gate + إعادة مقارنة كاملة ضد
  قاعدة البيانات الحالية؛ أي اختلاف عن المعاينة المخزنة → IMPORT_PREVIEW_STALE
  مع إعادة بناء المعاينة (الصفوف المخزنة تحدث) ليراجعها المستخدم من جديد.
- بعد النجاح: حذف صفوف الـ staging وملف Excel (PII مؤقت).
"""

from datetime import date

from django.db import transaction
from django.utils import timezone

from academics.models import AcademicYearStatus
from audit.models import AuditAction
from audit.services import record_event
from common.errors import ApiError
from students.models import (
    EnrollmentStatus,
    Grade,
    ImportJobStatus,
    ImportRowStatus,
    Section,
    Student,
    StudentEnrollment,
    StudentImportJob,
)
from students.services.imports.comparison import categorize_rows

_APPLY_STATUSES = {
    ImportRowStatus.NEW,
    ImportRowStatus.EXISTING_UPDATED,
    ImportRowStatus.SECTION_CHANGED,
    ImportRowStatus.GRADE_CHANGED,
}


def _rows_to_normalized(rows) -> list[dict]:
    """صفوف الـ staging → صيغة normalized rows لإعادة المقارنة."""
    normalized = []
    for row in rows:
        data = dict(row.data)
        data["row_number"] = row.row_number
        data["national_id_encrypted"] = row.national_id_encrypted
        data["national_id_hash"] = row.national_id_hash
        data["errors"] = list(row.error_codes)
        normalized.append(data)
    return normalized


def commit_import(*, job_id: int, actor, request=None) -> StudentImportJob:
    """غلاف: كتابات الفشل/تحديث المعاينة تثبت داخل الـ transaction،
    والخطأ يرفع بعد خروجها بنجاح — لا rollback لتلك الكتابات."""
    with transaction.atomic():
        job, deferred_error = _commit_locked(job_id=job_id, actor=actor, request=request)
    if deferred_error is not None:
        raise deferred_error
    return job


def _commit_locked(
    *, job_id: int, actor, request=None
) -> tuple[StudentImportJob, ApiError | None]:
    job = (
        StudentImportJob.objects.select_for_update()
        .select_related("school", "academic_year")
        .get(id=job_id)
    )

    # حالة الـ Job — حماية double-commit والتزامن (لا كتابات → raise مباشر آمن)
    if job.status == ImportJobStatus.COMPLETED:
        raise ApiError("IMPORT_ALREADY_COMMITTED", "تم اعتماد هذا الاستيراد مسبقاً.", 409)
    if job.status in (ImportJobStatus.PROCESSING, ImportJobStatus.IMPORTING):
        raise ApiError("IMPORT_ALREADY_RUNNING", "الاستيراد قيد التنفيذ حالياً.", 409)
    if job.status != ImportJobStatus.READY_FOR_REVIEW:
        raise ApiError("IMPORT_NOT_READY", "الاستيراد غير جاهز للاعتماد.", 409)

    # العام الدراسي وقت الإنشاء يجب أن يظل هو النشط (لا استخدام صامت لعام جديد)
    if job.academic_year.status != AcademicYearStatus.ACTIVE:
        job.status = ImportJobStatus.FAILED
        job.error_code = "ACTIVE_ACADEMIC_YEAR_REQUIRED"
        job.failed_at = timezone.now()
        job.save(update_fields=["status", "error_code", "failed_at", "updated_at"])
        return job, ApiError(
            "ACTIVE_ACADEMIC_YEAR_REQUIRED",
            "تغير العام الدراسي النشط منذ رفع الملف. أعد الاستيراد من جديد.",
            409,
        )

    staged = list(job.rows.all())
    stored_statuses = {row.row_number: row.status for row in staged}

    # إعادة المقارنة ضد قاعدة البيانات الحالية (stale preview protection)
    result = categorize_rows(job.school, job.academic_year, _rows_to_normalized(staged))
    fresh_by_number = {r["row_number"]: r for r in result["rows"]}
    stale = any(
        fresh_by_number[num]["status"] != status for num, status in stored_statuses.items()
    )
    if stale:
        for row in staged:
            fresh = fresh_by_number[row.row_number]
            row.status = fresh["status"]
            row.data = {
                k: v for k, v in fresh.items()
                if k not in ("national_id_encrypted", "national_id_hash", "errors", "row_number")
            }
            row.save(update_fields=["status", "data"])
        from subscriptions.usage import student_capacity_preview

        refreshed_summary = result["summary"]
        refreshed_summary["student_capacity"] = student_capacity_preview(
            job.school, adding=refreshed_summary["new"]
        )
        job.summary = {**job.summary, **refreshed_summary, "missing_names": result["missing"]}
        job.save(update_fields=["summary", "updated_at"])
        return job, ApiError(
            "IMPORT_PREVIEW_STALE",
            "تغيرت بيانات الطلاب منذ إنشاء المعاينة. راجع المعاينة المحدثة ثم أعد الاعتماد.",
            409,
        )

    job.status = ImportJobStatus.IMPORTING
    job.save(update_fields=["status", "updated_at"])

    apply_rows = [r for r in result["rows"] if r["status"] in _APPLY_STATUSES]

    # حد الباقة يُفحص عند الاعتماد لا عند المعاينة — المعاينة تُظهر التجاوز (بند 64)
    new_students = sum(1 for r in apply_rows if r["status"] == ImportRowStatus.NEW)
    if new_students:
        from subscriptions.entitlements import lock_school_capacity, require_capacity
        from subscriptions.models import EntitlementKey
        from subscriptions.usage import count_active_students

        try:
            lock_school_capacity(job.school)
            require_capacity(
                job.school,
                EntitlementKey.MAX_STUDENTS,
                current=count_active_students(job.school),
                adding=new_students,
            )
        except ApiError as exc:
            job.status = ImportJobStatus.READY_FOR_REVIEW
            job.error_code = exc.code
            job.save(update_fields=["status", "error_code", "updated_at"])
            return job, exc

    # 1) الصفوف والفصول المطلوبة (get_or_create — تنشأ عند الاعتماد فقط)
    grades: dict[str, Grade] = {}
    sections: dict[tuple[str, str], Section] = {}
    created_grades: list[str] = []
    created_sections: list[str] = []
    for row in apply_rows:
        gcode = row["grade_code"]
        if gcode not in grades:
            grade, created = Grade.objects.get_or_create(
                school=job.school,
                code=gcode,
                defaults={"name": row["grade_name"], "sequence": row["grade_sequence"]},
            )
            grades[gcode] = grade
            if created:
                created_grades.append(grade.name)
                record_event(
                    AuditAction.GRADE_CREATED, request=request, actor=actor,
                    school=job.school, target_type="Grade", target_id=grade.id,
                    metadata={"name": grade.name},
                )
        skey = (gcode, row["section_code"])
        if skey not in sections:
            section, created = Section.objects.get_or_create(
                school=job.school,
                grade=grades[gcode],
                code=row["section_code"],
                defaults={"name": row["section_name"]},
            )
            sections[skey] = section
            if created:
                created_sections.append(str(section))
                record_event(
                    AuditAction.SECTION_CREATED, request=request, actor=actor,
                    school=job.school, target_type="Section", target_id=section.id,
                    metadata={"name": str(section)},
                )

    today = date.today()
    created_students = 0
    updated_students = 0
    enrollment_changes = 0

    existing_enrollments = {
        e.student_id: e
        for e in StudentEnrollment.objects.select_for_update().filter(
            school=job.school,
            academic_year=job.academic_year,
            status=EnrollmentStatus.ACTIVE,
        )
    }

    for row in apply_rows:
        section = sections[(row["grade_code"], row["section_code"])]
        grade = grades[row["grade_code"]]

        if row["status"] == ImportRowStatus.NEW:
            student = Student.objects.create(
                school=job.school,
                national_id_encrypted=row["national_id_encrypted"],
                national_id_lookup_hash=row["national_id_hash"],
                national_id_masked=row["national_id_masked"],
                student_number=row["student_number"],
                full_name=row["full_name"],
                guardian_name=row["guardian_name"],
                guardian_mobile=row["guardian_mobile"],
            )
            StudentEnrollment.objects.create(
                school=job.school, student=student, academic_year=job.academic_year,
                grade=grade, section=section, enrolled_at=today,
            )
            created_students += 1
            continue

        student = Student.objects.get(id=row["matched_student_id"])
        changes = row.get("changes") or {}
        if changes:
            if "full_name" in changes:
                student.full_name = row["full_name"]
            if "guardian_name" in changes:
                student.guardian_name = row["guardian_name"]
            if "guardian_mobile" in changes:
                student.guardian_mobile = row["guardian_mobile"]
            student.save()
            updated_students += 1
            record_event(
                AuditAction.STUDENT_UPDATED, request=request, actor=actor,
                school=job.school, target_type="Student", target_id=student.id,
                metadata={"changed_fields": sorted(changes.keys())},  # بلا قيم حساسة
            )

        if row["status"] in (ImportRowStatus.SECTION_CHANGED, ImportRowStatus.GRADE_CHANGED):
            old = existing_enrollments.get(student.id)
            if old is not None:
                old.status = EnrollmentStatus.TRANSFERRED
                old.ended_at = today
                old.save(update_fields=["status", "ended_at", "updated_at"])
            StudentEnrollment.objects.create(
                school=job.school, student=student, academic_year=job.academic_year,
                grade=grade, section=section, enrolled_at=today,
            )
            enrollment_changes += 1

    job.status = ImportJobStatus.COMPLETED
    job.committed_at = timezone.now()
    job.summary = {
        **result["summary"],
        "created": created_students,
        "updated": updated_students,
        "enrollment_changes": enrollment_changes,
        "created_grades": created_grades,
        "created_sections": created_sections,
        "missing_names": result["missing"],
    }
    job.save(update_fields=["status", "committed_at", "summary", "updated_at"])

    record_event(
        AuditAction.STUDENT_IMPORT_COMMITTED,
        request=request, actor=actor, school=job.school,
        target_type="StudentImportJob", target_id=job.id,
        metadata={
            "created": created_students,
            "updated": updated_students,
            "enrollment_changes": enrollment_changes,
            "unchanged": result["summary"]["unchanged"],
            "errors": result["summary"]["errors"],
            "missing_from_file": result["summary"]["missing_from_file"],
        },
    )

    # تنظيف PII المؤقت: صفوف staging + ملف Excel
    job.rows.all().delete()
    if job.file:
        job.file.delete(save=False)
        job.file = None
        job.save(update_fields=["file"])

    return job, None
