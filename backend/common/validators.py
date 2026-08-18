"""تحقق الملفات المرفوعة — لا ثقة باسم الملف ولا بامتداده وحده."""

from pathlib import Path

from django.core.exceptions import ValidationError
from PIL import Image, UnidentifiedImageError

LOGO_MAX_BYTES = 2 * 1024 * 1024  # 2MB
LOGO_ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
LOGO_ALLOWED_FORMATS = {"PNG", "JPEG", "WEBP"}  # صيغة Pillow الفعلية للمحتوى


def validate_logo_image(uploaded_file) -> None:
    """حجم + امتداد + محتوى صورة فعلي (Pillow) — يرفض الامتداد المزيف والملف التالف."""
    if uploaded_file.size > LOGO_MAX_BYTES:
        raise ValidationError("حجم الشعار يتجاوز الحد المسموح (2MB).", code="logo_too_large")

    extension = Path(uploaded_file.name).suffix.lower()
    if extension not in LOGO_ALLOWED_EXTENSIONS:
        raise ValidationError(
            "صيغة الشعار غير مدعومة. المسموح: PNG أو JPG أو WEBP.", code="logo_bad_extension"
        )

    try:
        with Image.open(uploaded_file) as image:
            image.verify()
            detected = image.format
    except (UnidentifiedImageError, OSError) as exc:
        raise ValidationError("الملف ليس صورة صالحة.", code="logo_not_image") from exc
    finally:
        uploaded_file.seek(0)

    if detected not in LOGO_ALLOWED_FORMATS:
        raise ValidationError(
            "محتوى الملف لا يطابق صيغة صورة مدعومة.", code="logo_content_mismatch"
        )
