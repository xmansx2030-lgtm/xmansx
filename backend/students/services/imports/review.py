"""تصحيح صفوف معاينة الاستيراد وإعادة حسابها دون كشف بيانات حساسة."""

from django.core.exceptions import ValidationError

from common.errors import ApiError
from common.security.identifiers import (
    encrypt_national_id,
    mask_national_id,
    national_id_lookup_hash,
    normalize_national_id,
)
from students.models import Section, StudentImportJob, StudentImportRow
from students.services.imports import comparison, validation
from students.services.imports.normalization import normalize_student_number, normalize_text

_DERIVED_FIELDS = {
    "status", "matched_student_id", "changes", "needs_enrollment",
    "previous_section", "auto_resolved_duplicate",
}


def _normalized_from_staged(row: StudentImportRow) -> dict:
    data = {key: value for key, value in dict(row.data).items() if key not in _DERIVED_FIELDS}
    data.update(
        row_number=row.row_number,
        national_id_encrypted=row.national_id_encrypted,
        national_id_hash=row.national_id_hash,
        errors=[code for code in row.error_codes if code != "DUPLICATE_IN_FILE"],
    )
    return data


def recalculate_preview(job: StudentImportJob) -> dict:
    """يعيد تصنيف كل الصفوف بعد التصحيح حتى تُكتشف التكرارات الجديدة فورًا."""
    staged = list(job.rows.all())
    normalized = [_normalized_from_staged(row) for row in staged]
    validation.mark_duplicates_in_file(normalized)
    result = comparison.categorize_rows(job.school, job.academic_year, normalized)

    for staged_row, fresh in zip(staged, result["rows"], strict=True):
        staged_row.national_id_encrypted = fresh["national_id_encrypted"]
        staged_row.national_id_hash = fresh["national_id_hash"]
        staged_row.data = {
            key: value for key, value in fresh.items()
            if key not in ("national_id_encrypted", "national_id_hash", "errors", "row_number")
        }
        staged_row.status = fresh["status"]
        staged_row.error_codes = fresh["errors"]
        staged_row.error_message = validation.error_message_for(fresh["errors"])
    StudentImportRow.objects.bulk_update(
        staged,
        [
            "national_id_encrypted", "national_id_hash", "data", "status",
            "error_codes", "error_message",
        ],
    )

    summary = result["summary"]
    from subscriptions.usage import student_capacity_preview

    summary["student_capacity"] = student_capacity_preview(
        job.school, adding=summary["new"]
    )
    auto_resolved = summary["auto_resolved_duplicates"]
    job.total_rows = len(staged)
    job.invalid_rows = summary["errors"]
    job.duplicate_rows = summary["duplicates"]
    job.valid_rows = job.total_rows - job.invalid_rows - job.duplicate_rows - auto_resolved
    job.summary = {**job.summary, **summary, "missing_names": result["missing"]}
    job.error_code = ""
    job.save(
        update_fields=[
            "total_rows", "invalid_rows", "duplicate_rows", "valid_rows",
            "summary", "error_code", "updated_at",
        ]
    )
    return result


def correct_row(
    *, job: StudentImportJob, row: StudentImportRow, corrections: dict
) -> list[str]:
    """يطبّق حقولًا مصححة ثم يعيد بناء المعاينة كاملة داخل transaction المستدعي."""
    data = dict(row.data)
    errors = set(row.error_codes)
    changed_fields: list[str] = []

    if "national_id" in corrections:
        try:
            national_id = normalize_national_id(
                validation.normalize_import_national_id(corrections["national_id"])
            )
        except ValidationError as exc:
            raise ApiError("INVALID_NATIONAL_ID", "رقم الهوية غير صالح.") from exc
        row.national_id_encrypted = encrypt_national_id(national_id)
        row.national_id_hash = national_id_lookup_hash(national_id)
        data["national_id_masked"] = mask_national_id(national_id)
        errors.difference_update(
            {"INVALID_NATIONAL_ID", "MISSING_NATIONAL_ID", "MISSING_IDENTITY"}
        )
        changed_fields.append("national_id")

    if "student_number" in corrections:
        student_number = normalize_student_number(corrections["student_number"])
        data["student_number"] = student_number
        if student_number:
            errors.discard("MISSING_IDENTITY")
        changed_fields.append("student_number")

    if "full_name" in corrections:
        full_name = normalize_text(corrections["full_name"])
        if len(full_name) < 2:
            raise ApiError("VALIDATION_ERROR", "أدخل اسم الطالب الصحيح.")
        data["full_name"] = full_name
        errors.discard("MISSING_NAME")
        changed_fields.append("full_name")

    if "section_id" in corrections:
        section = (
            Section.objects.select_related("grade")
            .filter(
                id=corrections["section_id"], school=job.school,
                is_active=True, grade__is_active=True,
            )
            .first()
        )
        if section is None:
            raise ApiError("VALIDATION_ERROR", "الفصل المحدد غير متاح لهذه المدرسة.")
        data.update(
            grade_code=section.grade.code,
            grade_name=section.grade.name,
            grade_sequence=section.grade.sequence,
            section_code=section.code,
            section_name=section.name,
        )
        errors.difference_update({"MISSING_GRADE", "MISSING_SECTION"})
        changed_fields.append("section")

    if "section_code" in corrections:
        candidate = next(
            (
                item for item in job.summary.get("section_candidates", [])
                if item["grade_code"] == data.get("grade_code")
                and item["section_code"] == corrections["section_code"]
            ),
            None,
        )
        if candidate is None:
            raise ApiError(
                "VALIDATION_ERROR",
                "الفصل المحدد غير موجود ضمن الصفوف الموثوقة في ملف نور.",
            )
        data.update(
            section_code=candidate["section_code"],
            section_name=candidate["section_name"],
        )
        errors.discard("MISSING_SECTION")
        changed_fields.append("section")

    if not changed_fields:
        raise ApiError("VALIDATION_ERROR", "أرسل تصحيحًا واحدًا على الأقل.")

    row.data = data
    row.error_codes = sorted(errors)
    row.error_message = validation.error_message_for(row.error_codes)
    row.save(
        update_fields=[
            "national_id_encrypted", "national_id_hash", "data",
            "error_codes", "error_message",
        ]
    )
    recalculate_preview(job)
    return changed_fields
