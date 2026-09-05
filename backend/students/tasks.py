"""مهام Celery للاستيراد.

Tenant safety: المهمة تستلم job_id فقط وتستمد المدرسة/العام من الـ Job الموثوق —
لا school_id خام من المستخدم (لا يوجد request.school هنا).
Idempotency: فحص الحالة قبل العمل — إعادة تشغيل المهمة لا تكرر معالجة منتهية.
لا retry تلقائي لأخطاء الملف نفسه (invalid/duplicate) — هي أخطاء مستخدم نهائية.
"""

import logging

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from audit.models import AuditAction
from audit.services import record_event

logger = logging.getLogger("xmansx.imports")


@shared_task(name="students.process_import_job")
def process_import_job(job_id: int) -> str:
    from common.errors import ApiError
    from students.models import ImportJobStatus, StudentImportJob, StudentImportRow
    from students.services.imports import comparison, parser, validation

    with transaction.atomic():
        job = (
            StudentImportJob.objects.select_for_update()
            .select_related("school", "academic_year")
            .filter(id=job_id)
            .first()
        )
        if job is None or job.status != ImportJobStatus.PROCESSING:
            return "skipped"  # idempotent: أعيد تشغيلها أو ألغيت

        try:
            with job.file.open("rb") as file_obj:
                header_row = int(job.summary.get("header_row", 1))
                raw_rows = parser.read_rows(
                    file_obj,
                    start_row=header_row + 1,
                    import_format=job.summary.get("import_format", "TABULAR"),
                )

            normalized = [
                validation.build_normalized_row(number, values, job.column_mapping)
                for number, values in raw_rows
            ]
            validation.mark_duplicates_in_file(normalized)
            result = comparison.categorize_rows(job.school, job.academic_year, normalized)

            job.rows.all().delete()  # idempotency لإعادة المعالجة
            StudentImportRow.objects.bulk_create(
                StudentImportRow(
                    job=job,
                    row_number=row["row_number"],
                    national_id_encrypted=row["national_id_encrypted"],
                    national_id_hash=row["national_id_hash"],
                    data={
                        k: v for k, v in row.items()
                        if k not in (
                            "national_id_encrypted", "national_id_hash",
                            "errors", "row_number",
                        )
                    },
                    status=row["status"],
                    error_codes=row["errors"],
                    error_message=validation.error_message_for(row["errors"]),
                )
                for row in result["rows"]
            )

            summary = result["summary"]
            from subscriptions.usage import student_capacity_preview

            summary["student_capacity"] = student_capacity_preview(
                job.school, adding=summary["new"]
            )
            job.total_rows = len(result["rows"])
            job.valid_rows = job.total_rows - summary["errors"] - summary["duplicates"]
            job.invalid_rows = summary["errors"]
            job.duplicate_rows = summary["duplicates"]
            job.summary = {
                **job.summary,
                **summary,
                "missing_names": result["missing"],
            }
            job.status = ImportJobStatus.READY_FOR_REVIEW
            job.validated_at = timezone.now()
            job.save()

            record_event(
                AuditAction.STUDENT_IMPORT_VALIDATED,
                school=job.school,
                actor=job.uploaded_by,
                target_type="StudentImportJob",
                target_id=job.id,
                metadata={"total_rows": job.total_rows, "errors": job.invalid_rows},
            )
            return "ready"

        except ApiError as exc:
            _fail(job, exc.code)
            return "failed"
        except Exception:
            # Stack trace للسجلات/Sentry فقط — المستخدم يرى رمزًا آمنًا
            logger.exception("import job %s parsing failed", job.id)
            _fail(job, "INVALID_IMPORT_FILE")
            return "failed"


@shared_task(name="students.run_purge_job")
def run_purge_job(job_id: int) -> str:
    """تنفيذ الحذف الجماعي بدفعات — tenant من الـ Job، idempotent بحالة الـ Job."""
    from django.utils import timezone

    from students.models import PurgeJobStatus, Student, StudentPurgeJob
    from students.services.purge import PURGE_BATCH_SIZE, purge_student

    with transaction.atomic():
        job = (
            StudentPurgeJob.objects.select_for_update()
            .select_related("school")
            .filter(id=job_id)
            .first()
        )
        if job is None or job.status != PurgeJobStatus.PENDING:
            return "skipped"  # retry لا يكرر عملية منتهية
        job.status = PurgeJobStatus.RUNNING
        job.started_at = timezone.now()
        job.save(update_fields=["status", "started_at", "updated_at"])

    ids = list(job.student_ids)
    deleted = failed = db_rows = storage_ok = storage_failed = 0

    for start in range(0, len(ids), PURGE_BATCH_SIZE):
        batch = ids[start:start + PURGE_BATCH_SIZE]
        # العزل: الطلاب من مدرسة الـ Job حصرًا (حتى لو تسللت معرفات غريبة)
        students = list(Student.objects.filter(school=job.school, id__in=batch))
        found_ids = {s.id for s in students}
        failed += len([i for i in batch if i not in found_ids])
        for student in students:
            try:
                rows, ok, bad = purge_student(student)
                deleted += 1
                db_rows += rows
                storage_ok += ok
                storage_failed += bad
            except Exception:
                logger.exception("purge job %s: student purge failed", job.id)
                failed += 1
        job.processed_students = min(start + len(batch), len(ids))
        job.deleted_students = deleted
        job.failed_students = failed
        job.db_records_deleted = db_rows
        job.storage_objects_deleted = storage_ok
        job.storage_objects_failed = storage_failed
        job.save(
            update_fields=[
                "processed_students", "deleted_students", "failed_students",
                "db_records_deleted", "storage_objects_deleted",
                "storage_objects_failed", "updated_at",
            ]
        )

    if deleted == 0 and failed > 0:
        job.status = PurgeJobStatus.FAILED
        job.failed_at = timezone.now()
    elif failed > 0 or storage_failed > 0:
        # ملفات لم تنظف/طلاب فشلوا — لا ندعي COMPLETED
        job.status = PurgeJobStatus.PARTIALLY_FAILED
        job.completed_at = timezone.now()
    else:
        job.status = PurgeJobStatus.COMPLETED
        job.completed_at = timezone.now()
    job.student_ids = []  # خصوصية: لا معرفات قابلة للربط بعد الحذف
    job.save(
        update_fields=["status", "completed_at", "failed_at", "student_ids", "updated_at"]
    )

    record_event(
        "STUDENT_BULK_PURGE_COMPLETED",
        school=job.school,
        actor=job.created_by,
        target_type="StudentPurgeJob",
        target_id=job.id,
        metadata={
            "status": job.status,
            "reason": job.reason,
            "students": deleted,
            "failed": failed,
            "database_records": db_rows,
            "storage_objects": storage_ok,
            "storage_objects_failed": storage_failed,
        },  # لا اسم/هوية/جوال — أعداد فقط
    )
    return job.status


def _fail(job, error_code: str) -> None:
    from students.models import ImportJobStatus

    job.status = ImportJobStatus.FAILED
    job.error_code = error_code
    job.failed_at = timezone.now()
    job.save(update_fields=["status", "error_code", "failed_at", "updated_at"])
    record_event(
        AuditAction.STUDENT_IMPORT_FAILED,
        school=job.school,
        actor=job.uploaded_by,
        target_type="StudentImportJob",
        target_id=job.id,
        metadata={"error_code": error_code},
    )
