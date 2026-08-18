"""تطبيع بيانات ملف نور — غير مدمر للأسماء، حاسم للرموز."""

import re
import unicodedata

_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
_ZERO_WIDTH = re.compile(r"[​‌‍‎‏﻿]")
_MULTI_SPACE = re.compile(r"\s+")


def normalize_text(value) -> str:
    """تنظيف عام: NFKC + إزالة محارف العرض الصفرية + ضغط المسافات. غير مدمر للاسم."""
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value))
    text = _ZERO_WIDTH.sub("", text)
    return _MULTI_SPACE.sub(" ", text).strip()


def normalize_digits(value) -> str:
    return normalize_text(value).translate(_ARABIC_DIGITS)


def _normalize_arabic_key(text: str) -> str:
    """مفتاح مقارنة عربي: توحيد الهمزات والتاء المربوطة وإزالة ال التعريف والمسافات."""
    key = normalize_text(text)
    key = key.translate(_ARABIC_DIGITS)
    key = re.sub(r"[أإآ]", "ا", key)
    key = key.replace("ة", "ه").replace("ى", "ي")
    key = re.sub(r"\bال", "", key)
    return re.sub(r"\s+", "", key)


# خرائط الصفوف الشائعة في ملفات نور → (code, name, sequence)
_GRADE_PATTERNS: list[tuple[re.Pattern, str, str, int]] = [
    (re.compile(r"(اول|أول|1).*(ابتدائي)"), "ELEM_1", "الأول الابتدائي", 1),
    (re.compile(r"(ثاني|2).*(ابتدائي)"), "ELEM_2", "الثاني الابتدائي", 2),
    (re.compile(r"(ثالث|3).*(ابتدائي)"), "ELEM_3", "الثالث الابتدائي", 3),
    (re.compile(r"(رابع|4).*(ابتدائي)"), "ELEM_4", "الرابع الابتدائي", 4),
    (re.compile(r"(خامس|5).*(ابتدائي)"), "ELEM_5", "الخامس الابتدائي", 5),
    (re.compile(r"(سادس|6).*(ابتدائي)"), "ELEM_6", "السادس الابتدائي", 6),
    (re.compile(r"(اول|أول|1).*(متوسط)"), "MID_1", "الأول المتوسط", 7),
    (re.compile(r"(ثاني|2).*(متوسط)"), "MID_2", "الثاني المتوسط", 8),
    (re.compile(r"(ثالث|3).*(متوسط)"), "MID_3", "الثالث المتوسط", 9),
    (re.compile(r"(اول|أول|1).*(ثانوي)"), "SEC_1", "الأول الثانوي", 10),
    (re.compile(r"(ثاني|2).*(ثانوي)"), "SEC_2", "الثاني الثانوي", 11),
    (re.compile(r"(ثالث|3).*(ثانوي)"), "SEC_3", "الثالث الثانوي", 12),
]


def normalize_grade_label(raw) -> tuple[str, str, int]:
    """(code, display_name, sequence) — الصيغ «الأول الثانوي/اول ثانوي/1 ثانوي» تتوحد.

    غير المعروف لا يخمن Stage: code مشتق من النص نفسه وsequence=0،
    وواجهة المعاينة تعرضه قبل الاعتماد.
    """
    label = normalize_text(raw)
    key = _normalize_arabic_key(label)
    for pattern, code, name, sequence in _GRADE_PATTERNS:
        if pattern.search(key):
            return code, name, sequence
    fallback_code = _normalize_arabic_key(label).upper()[:50] or "UNKNOWN"
    return fallback_code, label, 0


def normalize_section_label(raw) -> tuple[str, str]:
    """(code, display_name) — «1 / 01 / 1/1 / فصل 1» تتوحد إلى code واحد."""
    label = normalize_digits(raw)
    label = re.sub(r"^فصل\s*", "", label).strip()
    # صيغة 1/3 → الجزء الأخير هو الفصل
    if "/" in label:
        label = label.split("/")[-1].strip()
    # أرقام: إزالة الأصفار البادئة
    if label.isdigit():
        code = str(int(label))
        return code, code
    code = _normalize_arabic_key(label)[:50] or "UNKNOWN"
    return code, label or "غير محدد"


def normalize_student_number(raw) -> str | None:
    value = normalize_digits(raw)
    return value or None


def normalize_guardian_mobile(raw) -> str:
    """جوال ولي الأمر يطبع إن أمكن؛ القيمة غير الصالحة تترك فارغة (ليست إلزامية)."""
    from django.core.exceptions import ValidationError

    from accounts.mobile import normalize_mobile

    value = normalize_digits(raw)
    if not value:
        return ""
    try:
        return normalize_mobile(value)
    except ValidationError:
        return ""
