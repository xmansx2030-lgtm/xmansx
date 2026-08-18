"""قراءة ملف نور xlsx بأمان.

الحماية:
- امتداد .xlsx فقط (لا .xls ولا .xlsm — الماكرو مرفوض) + حد حجم 10MB.
- xlsx = ZIP: فحص عدد المدخلات والحجم غير المضغوط (zip bomb) قبل الفتح.
- openpyxl بـ read_only + data_only: لا تنفيذ صيغ (formula injection) وذاكرة محدودة.
- حد أقصى لعدد الصفوف.
"""

import zipfile
from pathlib import Path

from django.conf import settings
from openpyxl import load_workbook

from common.errors import ApiError

TOO_LARGE_MESSAGE = "حجم الملف يتجاوز الحد المسموح (10MB)."
UNSUPPORTED_MESSAGE = "صيغة الملف غير مدعومة. المسموح: ملف Excel بامتداد ‎.xlsx فقط."
INVALID_FILE_MESSAGE = "تعذر قراءة الملف. تأكد أنه ملف Excel سليم من نظام نور."


def validate_upload(uploaded_file) -> None:
    """فحوص ما قبل الحفظ — ترفع ApiError برموز واضحة."""
    if uploaded_file.size > settings.STUDENT_IMPORT_MAX_FILE_BYTES:
        raise ApiError("IMPORT_FILE_TOO_LARGE", TOO_LARGE_MESSAGE, status_code=400)

    extension = Path(uploaded_file.name).suffix.lower()
    if extension in {".xls", ".xlsm", ".xlsb"}:
        raise ApiError("UNSUPPORTED_IMPORT_FILE", UNSUPPORTED_MESSAGE, status_code=400)
    if extension != ".xlsx":
        raise ApiError("UNSUPPORTED_IMPORT_FILE", UNSUPPORTED_MESSAGE, status_code=400)

    _validate_zip_safety(uploaded_file)
    uploaded_file.seek(0)


def _validate_zip_safety(file_obj) -> None:
    """xlsx ملف ZIP — نفحص بنيته ضد القنابل قبل أي parsing."""
    try:
        with zipfile.ZipFile(file_obj) as archive:
            infos = archive.infolist()
            if len(infos) > settings.STUDENT_IMPORT_MAX_ZIP_ENTRIES:
                raise ApiError("INVALID_IMPORT_FILE", INVALID_FILE_MESSAGE, status_code=400)
            total_uncompressed = sum(info.file_size for info in infos)
            if total_uncompressed > settings.STUDENT_IMPORT_MAX_UNCOMPRESSED_BYTES:
                raise ApiError("INVALID_IMPORT_FILE", INVALID_FILE_MESSAGE, status_code=400)
            # ملف xlsx حقيقي يحتوي [Content_Types].xml
            names = {info.filename for info in infos}
            if "[Content_Types].xml" not in names:
                raise ApiError("INVALID_IMPORT_FILE", INVALID_FILE_MESSAGE, status_code=400)
    except zipfile.BadZipFile as exc:
        raise ApiError("INVALID_IMPORT_FILE", INVALID_FILE_MESSAGE, status_code=400) from exc
    finally:
        file_obj.seek(0)


def read_headers(file_obj) -> list[str]:
    """رؤوس الأعمدة من الصف الأول — للاقتراح وواجهة الـ Mapping."""
    workbook = load_workbook(file_obj, read_only=True, data_only=True)
    try:
        sheet = workbook.active
        first_row = next(sheet.iter_rows(min_row=1, max_row=1, values_only=True), ())
        return [str(cell).strip() if cell is not None else "" for cell in first_row]
    finally:
        workbook.close()
        file_obj.seek(0)


def read_rows(file_obj) -> list[tuple[int, tuple]]:
    """كل صفوف البيانات (بعد الرأس) كقيم فقط — [(رقم الصف في الملف، القيم)]."""
    workbook = load_workbook(file_obj, read_only=True, data_only=True)
    try:
        sheet = workbook.active
        rows: list[tuple[int, tuple]] = []
        for index, values in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
            if values is None or all(v is None or str(v).strip() == "" for v in values):
                continue  # صفوف فارغة تتجاهل
            rows.append((index, values))
            if len(rows) > settings.STUDENT_IMPORT_MAX_ROWS:
                raise ApiError(
                    "IMPORT_FILE_TOO_LARGE",
                    f"عدد الصفوف يتجاوز الحد المسموح ({settings.STUDENT_IMPORT_MAX_ROWS}).",
                    status_code=400,
                )
        return rows
    finally:
        workbook.close()
        file_obj.seek(0)
