"""تحقق صفوف الاستيراد وبناء الصفوف المطبعة."""

import re

from django.core.exceptions import ValidationError

from common.security.identifiers import (
    encrypt_national_id,
    mask_national_id,
    national_id_lookup_hash,
    normalize_student_identifier,
)
from students.services.imports.normalization import (
    normalize_digits,
    normalize_grade_label,
    normalize_guardian_mobile,
    normalize_section_label,
    normalize_student_number,
    normalize_text,
)

ERROR_MESSAGES = {
    "MISSING_NATIONAL_ID": "رقم الطالب مفقود.",
    "INVALID_NATIONAL_ID": "رقم الطالب غير صالح؛ تحقق من رقم الهوية أو الإقامة أو الجواز.",
    "MISSING_NAME": "اسم الطالب مفقود.",
    "MISSING_GRADE": "الصف مفقود.",
    "MISSING_SECTION": "الفصل مفقود.",
    "INVALID_DEPARTMENT": "اسم القسم يتجاوز 100 حرف.",
    "DUPLICATE_IN_FILE": "رقم الطالب أو الرقم الأكاديمي مكرر في الملف ببيانات متعارضة.",
    "IDENTITY_CONFLICT": (
        "المعرّف والرقم الأكاديمي يشيران إلى طالبين مختلفين؛ "
        "صحّح الصف قبل الاعتماد."
    ),
    "AUTO_RESOLVED_DUPLICATE": "صف مطابق تمامًا عولج تلقائيًا دون تكرار الطالب.",
    "MISSING_IDENTITY": "رقم الطالب مفقود — لا يمكن المطابقة.",
}


def normalize_import_national_id(raw_value) -> str:
    """يطبع رقم الهوية دون تخمين: أرقام عربية ومسافات وشرطات عرض فقط.

    إزالة فواصل العرض عملية حتمية لا تغيّر أي رقم. أي نقص أو رقم مختلف يبقى
    خطأً يحتاج مراجعة بشرية ولا تحاول المنصة استنتاجه من الاسم.
    """
    return re.sub(r"[\s\-‐‑‒–—―]+", "", normalize_digits(raw_value))


def build_normalized_row(row_number: int, values: tuple, mapping: dict) -> dict:
    """يحول صف Excel خام إلى صف مطبع مع أخطائه — الهوية تشفر فورًا (لا plaintext)."""

    def cell(field: str):
        index = mapping.get(field)
        if index is None or index >= len(values):
            return None
        return values[index]

    errors: list[str] = []
    full_name = normalize_text(cell("full_name"))
    if not full_name:
        errors.append("MISSING_NAME")

    grade_raw = cell("grade")
    if grade_raw is None or normalize_text(grade_raw) == "":
        errors.append("MISSING_GRADE")
        grade_code, grade_name, grade_seq = "", "", 0
    else:
        grade_code, grade_name, grade_seq = normalize_grade_label(grade_raw)

    section_raw = cell("section")
    if section_raw is None or normalize_text(section_raw) == "":
        errors.append("MISSING_SECTION")
        section_code, section_name = "", ""
    else:
        section_code, section_name = normalize_section_label(section_raw)
    department = normalize_text(cell("department"))
    if len(department) > 100:
        errors.append("INVALID_DEPARTMENT")

    national_id_encrypted = ""
    national_id_hash = ""
    national_id_masked = ""
    raw_nid = cell("national_id")
    student_number = normalize_student_number(cell("student_number"))

    if raw_nid is not None and normalize_digits(raw_nid) != "":
        try:
            normalized = normalize_student_identifier(normalize_import_national_id(raw_nid))
            national_id_encrypted = encrypt_national_id(normalized)
            national_id_hash = national_id_lookup_hash(normalized)
            national_id_masked = mask_national_id(normalized)
        except ValidationError:
            errors.append("INVALID_NATIONAL_ID")
    elif mapping.get("national_id") is not None:
        # العمود موجود لكن الخلية فارغة
        if student_number is None:
            errors.append("MISSING_IDENTITY")
    elif student_number is None:
        errors.append("MISSING_IDENTITY")

    return {
        "row_number": row_number,
        "full_name": full_name,
        "grade_code": grade_code,
        "grade_name": grade_name,
        "grade_sequence": grade_seq,
        "section_code": section_code,
        "section_name": section_name,
        "department": department,
        "student_number": student_number,
        "guardian_name": normalize_text(cell("guardian_name")),
        "guardian_mobile": normalize_guardian_mobile(cell("guardian_mobile")),
        "national_id_encrypted": national_id_encrypted,
        "national_id_hash": national_id_hash,
        "national_id_masked": national_id_masked,
        "errors": errors,
    }


def mark_duplicates_in_file(rows: list[dict]) -> None:
    """يعالج النسخ المتطابقة فقط، ويوقف التكرارات المتعارضة للمراجعة.

    إذا تطابقت كل بيانات الطالب نحتفظ بأول صف ونعلّم البقية كنسخ محلولة
    تلقائيًا. اختلاف أي حقل يعني أن الهوية استُخدمت لبيانات متعارضة؛ عندها لا
    نخمن الصف الصحيح وتبقى المجموعة كلها بحاجة إلى تصحيح يدوي.
    """
    parents = list(range(len(rows)))

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    seen: dict[tuple[str, str], int] = {}
    for index, row in enumerate(rows):
        row.pop("auto_resolved_duplicate", None)
        row["errors"] = [code for code in row["errors"] if code != "DUPLICATE_IN_FILE"]
        for kind, value in (
            ("identity", row["national_id_hash"]),
            ("number", row["student_number"]),
        ):
            if not value:
                continue
            key = (kind, value)
            if key in seen:
                parents[find(index)] = find(seen[key])
            else:
                seen[key] = index

    groups: dict[int, list[dict]] = {}
    for index, row in enumerate(rows):
        groups.setdefault(find(index), []).append(row)
    for group in groups.values():
        if len(group) <= 1:
            continue
        comparison_fields = (
            "national_id_hash", "full_name", "grade_code", "section_code",
            "department", "student_number",
            "guardian_name", "guardian_mobile",
        )
        signatures = {
            tuple(row.get(field) or "" for field in comparison_fields) for row in group
        }
        if len(signatures) == 1:
            for row in group[1:]:
                row["auto_resolved_duplicate"] = True
            continue
        for row in group:
            row["errors"].append("DUPLICATE_IN_FILE")


def error_message_for(codes: list[str]) -> str:
    return " ".join(ERROR_MESSAGES.get(code, code) for code in codes)
