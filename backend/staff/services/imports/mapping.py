"""مطابقة أعمدة ملف المعلمين — الحد الأدنى: الاسم + الجوال."""

from common.errors import ApiError

TARGET_FIELDS = {
    "full_name": "اسم المعلم",
    "mobile": "رقم الجوال",
    "employee_number": "الرقم الوظيفي",
    "job_title": "المسمى الوظيفي",
}

_ALIASES: dict[str, list[str]] = {
    "full_name": ["اسم المعلم", "الاسم", "اسم الموظف", "المعلم"],
    "mobile": ["رقم الجوال", "الجوال", "جوال المعلم", "رقم الهاتف", "الهاتف"],
    "employee_number": ["الرقم الوظيفي", "رقم الموظف", "السجل الوظيفي"],
    "job_title": ["المسمى الوظيفي", "المسمى", "الوظيفة"],
}

REQUIRED_FIELDS = ("full_name", "mobile")


def _clean(header: str) -> str:
    return header.strip().replace("أ", "ا").replace("إ", "ا").replace("ة", "ه")


def suggest_mapping(headers: list[str]) -> dict[str, int | None]:
    cleaned = [_clean(h) for h in headers]
    mapping: dict[str, int | None] = {field: None for field in TARGET_FIELDS}
    for field, aliases in _ALIASES.items():
        for alias in aliases:
            alias_clean = _clean(alias)
            for index, header in enumerate(cleaned):
                if header == alias_clean and index not in mapping.values():
                    mapping[field] = index
                    break
            if mapping[field] is not None:
                break
    return mapping


def validate_mapping(mapping: dict[str, int | None], headers_count: int) -> None:
    for field in REQUIRED_FIELDS:
        if mapping.get(field) is None:
            raise ApiError(
                "IMPORT_MISSING_REQUIRED_COLUMN",
                f"عمود «{TARGET_FIELDS[field]}» مطلوب ولم يتم تحديده.",
                status_code=400,
            )
    used = [i for i in mapping.values() if i is not None]
    if len(used) != len(set(used)):
        raise ApiError(
            "VALIDATION_ERROR", "لا يمكن ربط أكثر من حقل بنفس عمود الملف.", status_code=400
        )
    for index in used:
        if index < 0 or index >= headers_count:
            raise ApiError("VALIDATION_ERROR", "تحديد الأعمدة غير صحيح.", status_code=400)
