"""مطابقة أعمدة ملف نور مع حقول النظام — اقتراح تلقائي + تأكيد المستخدم."""

from common.errors import ApiError

# الحقول المستهدفة — القيم الإنجليزية ثابتة، العربية للعرض
TARGET_FIELDS = {
    "national_id": "رقم الهوية",
    "full_name": "اسم الطالب",
    "grade": "الصف",
    "section": "الفصل",
    "student_number": "رقم الطالب",
    "guardian_name": "اسم ولي الأمر",
    "guardian_mobile": "جوال ولي الأمر",
}

# أسماء الأعمدة المعروفة في ملفات نور وتنويعاتها
_ALIASES: dict[str, list[str]] = {
    "national_id": [
        "رقم الهوية", "السجل المدني", "هوية الطالب", "رقم الهويه",
        "رقم السجل المدني", "الهوية", "رقم الاقامة", "رقم الإقامة",
    ],
    "full_name": ["اسم الطالب", "الاسم", "اسم الطالب الرباعي", "الطالب"],
    "grade": ["الصف", "المرحلة والصف", "الصف الدراسي"],
    "section": ["الفصل", "الشعبة", "فصل الطالب"],
    "student_number": ["رقم الطالب", "الرقم الأكاديمي", "رقم الملف"],
    "guardian_name": ["اسم ولي الأمر", "ولي الأمر", "اسم ولي الامر"],
    "guardian_mobile": ["جوال ولي الأمر", "رقم جوال ولي الأمر", "جوال ولي الامر", "رقم الجوال"],
}

REQUIRED_FIELDS = ("full_name", "grade", "section")
# سياسة الهوية: national_id مفضل؛ student_number بديل موثوق بتحذير — الاسم وحده مرفوض
IDENTITY_FIELDS = ("national_id", "student_number")


def _clean(header: str) -> str:
    return header.strip().replace("أ", "ا").replace("إ", "ا").replace("ة", "ه")


def suggest_mapping(headers: list[str]) -> dict[str, int | None]:
    """يقترح {field: column_index} من الرؤوس — غير المؤكد يترك None لواجهة المستخدم."""
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
    """يتحقق من اكتمال الحد الأدنى قبل المعالجة."""
    for field in REQUIRED_FIELDS:
        if mapping.get(field) is None:
            raise ApiError(
                "IMPORT_MISSING_REQUIRED_COLUMN",
                f"عمود «{TARGET_FIELDS[field]}» مطلوب ولم يتم تحديده.",
                status_code=400,
            )
    if all(mapping.get(field) is None for field in IDENTITY_FIELDS):
        raise ApiError(
            "IMPORT_MISSING_REQUIRED_COLUMN",
            "يجب تحديد عمود «رقم الهوية» (أو «رقم الطالب» كبديل) للمطابقة الموثوقة.",
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
