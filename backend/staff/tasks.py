"""مهمة Celery لتحليل ملف المعلمين — tenant من الـ Job (لا school_id خام)."""

import logging

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from audit.models import AuditAction
from audit.services import record_event

logger = logging.getLogger("xmansx.imports")


@shared_task(name="staff.process_import_job")
def process_staff_import_job(job_id: int) -> str:
    from common.errors import ApiError
    from common.excel_security import read_rows
    from common.tenant_rls import tenant_context
    from staff.models import StaffImportJob, StaffImportRow, StaffImportStatus
    from staff.services.imports import pipeline

    with tenant_context(bypass=True):
        school_id = StaffImportJob.objects.filter(id=job_id).values_list(
            "school_id", flat=True
        ).first()
    if school_id is None:
        return "skipped"

    with tenant_context(school_id=school_id), transaction.atomic():
        job = (
            StaffImportJob.objects.select_for_update()
            .select_related("school")
            .filter(id=job_id)
            .first()
        )
        if job is None or job.status != StaffImportStatus.PROCESSING:
            return "skipped"

        try:
            with job.file.open("rb") as file_obj:
                header_row = int(job.summary.get("header_row", 1))
                raw_rows = read_rows(file_obj, start_row=header_row + 1)

            normalized = [
                pipeline.build_normalized_row(number, values, job.column_mapping)
                for number, values in raw_rows
            ]
            pipeline.mark_duplicates_in_file(normalized)
            result = pipeline.categorize_rows(job.school, normalized)

            job.rows.all().delete()
            StaffImportRow.objects.bulk_create(
                StaffImportRow(
                    job=job,
                    row_number=row["row_number"],
                    mobile=row["mobile"],
                    data={
                        k: v for k, v in row.items()
                        if k not in ("mobile", "errors", "row_number")
                    },
                    status=row["status"],
                    error_codes=row["errors"],
                    error_message=pipeline.error_message_for(row["errors"]),
                )
                for row in result["rows"]
            )

            summary = result["summary"]
            job.total_rows = len(result["rows"])
            job.invalid_rows = summary["errors"]
            job.duplicate_rows = summary["duplicates"]
            job.valid_rows = job.total_rows - job.invalid_rows - job.duplicate_rows
            job.summary = {**job.summary, **summary}
            job.status = StaffImportStatus.READY_FOR_REVIEW
            job.validated_at = timezone.now()
            job.save()

            record_event(
                AuditAction.STAFF_IMPORT_VALIDATED,
                school=job.school,
                actor=job.uploaded_by,
                target_type="StaffImportJob",
                target_id=job.id,
                metadata={"total_rows": job.total_rows, "errors": job.invalid_rows},
            )
            return "ready"

        except ApiError as exc:
            _fail(job, exc.code)
            return "failed"
        except Exception:
            logger.exception("staff import job %s parsing failed", job.id)
            _fail(job, "STAFF_IMPORT_INVALID_FILE")
            return "failed"


def _fail(job, error_code: str) -> None:
    from staff.models import StaffImportStatus

    job.status = StaffImportStatus.FAILED
    job.error_code = error_code
    job.failed_at = timezone.now()
    job.save(update_fields=["status", "error_code", "failed_at", "updated_at"])
    record_event(
        AuditAction.STAFF_IMPORT_FAILED,
        school=job.school,
        actor=job.uploaded_by,
        target_type="StaffImportJob",
        target_id=job.id,
        metadata={"error_code": error_code},
    )
