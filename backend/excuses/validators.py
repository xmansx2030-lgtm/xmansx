"""تحقق مرفقات الأعذار — لا ثقة بالامتداد ولا بـContent-Type المرسل من العميل.

‏PDF: توقيع %PDF- في أول 1024 بايت + ‏%%EOF قرب النهاية — بلا تنفيذ ولا parsing
لمحتوى تفاعلي. الصور: تحقق Pillow فعلي مع مطابقة الصيغة للامتداد.
"""

from pathlib import Path

from django.conf import settings
from PIL import Image, UnidentifiedImageError

from common.errors import ApiError

ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}
_IMAGE_FORMAT_BY_EXTENSION = {".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG"}
_MIME_BY_FORMAT = {"JPEG": "image/jpeg", "PNG": "image/png"}

_INVALID = ApiError(
    "EXCUSE_ATTACHMENT_INVALID",
    "الملف غير صالح. المسموح: PDF أو JPG أو PNG بمحتوى سليم.",
)


def _max_bytes() -> int:
    return settings.EXCUSE_ATTACHMENT_MAX_FILE_BYTES


def validate_excuse_attachment(uploaded_file) -> str:
    """يتحقق من الحجم والامتداد والمحتوى الفعلي — يعيد MIME المكتشف من المحتوى."""
    if uploaded_file.size > _max_bytes():
        raise ApiError(
            "EXCUSE_ATTACHMENT_TOO_LARGE",
            f"حجم المرفق يتجاوز الحد المسموح ({_max_bytes() // (1024 * 1024)}MB).",
        )
    if uploaded_file.size == 0:
        raise _INVALID

    extension = Path(uploaded_file.name).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise _INVALID

    try:
        if extension == ".pdf":
            return _validate_pdf(uploaded_file)
        return _validate_image(uploaded_file, extension)
    finally:
        uploaded_file.seek(0)


def _validate_pdf(uploaded_file) -> str:
    uploaded_file.seek(0)
    head = uploaded_file.read(1024)
    # في البداية تحديدًا: البحث في أول 1KB يقبل ملف HTML/SVG يحوي السلسلة عرضًا
    # ثم يخزن بـmime نوعه PDF كذبًا
    if not head.startswith(b"%PDF-"):
        raise _INVALID
    # ‏%%EOF في آخر 2KB — يرفض الملفات المبتورة/المزيفة البدائية
    uploaded_file.seek(max(uploaded_file.size - 2048, 0))
    tail = uploaded_file.read(2048)
    if b"%%EOF" not in tail:
        raise _INVALID
    return "application/pdf"


def _validate_image(uploaded_file, extension: str) -> str:
    uploaded_file.seek(0)
    try:
        with Image.open(uploaded_file) as image:
            image.verify()
            detected = image.format
    except (UnidentifiedImageError, OSError) as exc:
        raise _INVALID from exc
    if detected != _IMAGE_FORMAT_BY_EXTENSION[extension]:
        raise _INVALID
    return _MIME_BY_FORMAT[detected]
