"""أمان ملفات Excel المشترك (استيراد الطلاب والمعلمين) — مستخرج في المرحلة 5.

الحماية: امتداد .xlsx فقط (لا xls/xlsm/xlsb) + حد حجم + فحص ZIP ضد القنابل
(عدد المدخلات/الحجم غير المضغوط/بنية xlsx) + قراءة read_only+data_only
(لا تنفيذ صيغ) + حد صفوف.
"""

import zipfile
from pathlib import Path

from django.conf import settings
from openpyxl import load_workbook

from common.errors import ApiError

TOO_LARGE_MESSAGE = "حجم الملف يتجاوز الحد المسموح (10MB)."
UNSUPPORTED_MESSAGE = "صيغة الملف غير مدعومة. المسموح: ملف Excel بامتداد ‎.xlsx فقط."
INVALID_FILE_MESSAGE = "تعذر قراءة الملف. تأكد أنه ملف Excel سليم."


def validate_upload(
    uploaded_file,
    *,
    too_large_code: str = "IMPORT_FILE_TOO_LARGE",
    unsupported_code: str = "UNSUPPORTED_IMPORT_FILE",
    invalid_code: str = "INVALID_IMPORT_FILE",
) -> None:
    """فحوص ما قبل الحفظ — ترفع ApiError برموز قابلة للتخصيص لكل نطاق."""
    if uploaded_file.size > settings.STUDENT_IMPORT_MAX_FILE_BYTES:
        raise ApiError(too_large_code, TOO_LARGE_MESSAGE, status_code=400)

    extension = Path(uploaded_file.name).suffix.lower()
    if extension != ".xlsx":  # يشمل رفض .xls و.xlsm (ماكرو) و.xlsb
        raise ApiError(unsupported_code, UNSUPPORTED_MESSAGE, status_code=400)

    _validate_zip_safety(uploaded_file, invalid_code)
    uploaded_file.seek(0)


def _validate_zip_safety(file_obj, invalid_code: str) -> None:
    try:
        with zipfile.ZipFile(file_obj) as archive:
            infos = archive.infolist()
            if len(infos) > settings.STUDENT_IMPORT_MAX_ZIP_ENTRIES:
                raise ApiError(invalid_code, INVALID_FILE_MESSAGE, status_code=400)
            total_uncompressed = sum(info.file_size for info in infos)
            if total_uncompressed > settings.STUDENT_IMPORT_MAX_UNCOMPRESSED_BYTES:
                raise ApiError(invalid_code, INVALID_FILE_MESSAGE, status_code=400)
            names = {info.filename for info in infos}
            if "[Content_Types].xml" not in names:
                raise ApiError(invalid_code, INVALID_FILE_MESSAGE, status_code=400)
    except zipfile.BadZipFile as exc:
        raise ApiError(invalid_code, INVALID_FILE_MESSAGE, status_code=400) from exc
    finally:
        file_obj.seek(0)


def read_headers(file_obj) -> list[str]:
    workbook = load_workbook(file_obj, read_only=True, data_only=True)
    try:
        sheet = workbook.active
        first_row = next(sheet.iter_rows(min_row=1, max_row=1, values_only=True), ())
        return [str(cell).strip() if cell is not None else "" for cell in first_row]
    finally:
        workbook.close()
        file_obj.seek(0)


def read_rows(
    file_obj, *, too_large_code: str = "IMPORT_FILE_TOO_LARGE"
) -> list[tuple[int, tuple]]:
    workbook = load_workbook(file_obj, read_only=True, data_only=True)
    try:
        sheet = workbook.active
        rows: list[tuple[int, tuple]] = []
        for index, values in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
            if values is None or all(v is None or str(v).strip() == "" for v in values):
                continue
            rows.append((index, values))
            if len(rows) > settings.STUDENT_IMPORT_MAX_ROWS:
                raise ApiError(
                    too_large_code,
                    f"عدد الصفوف يتجاوز الحد المسموح ({settings.STUDENT_IMPORT_MAX_ROWS}).",
                    status_code=400,
                )
        return rows
    finally:
        workbook.close()
        file_obj.seek(0)
