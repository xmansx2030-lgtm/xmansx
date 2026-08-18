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
                raw_rows = parser.read_rows(file_obj)

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
            job.total_rows = len(result["rows"])
            job.valid_rows = job.total_rows - summary["errors"] - summary["duplicates"]
            job.invalid_rows = summary["errors"]
            job.duplicate_rows = summary["duplicates"]
            job.summary = {**summary, "missing_names": result["missing"]}
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
