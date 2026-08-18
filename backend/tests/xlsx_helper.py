"""بناء ملفات xlsx حقيقية للاختبارات (openpyxl) — ليست mock dictionaries."""

import io

from django.core.files.uploadedfile import SimpleUploadedFile
from openpyxl import Workbook

NOOR_HEADERS = [
    "رقم الهوية", "اسم الطالب", "الصف", "الفصل",
    "رقم الطالب", "اسم ولي الأمر", "جوال ولي الأمر",
]


def build_xlsx_bytes(rows: list[list], headers: list[str] | None = None) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(headers if headers is not None else NOOR_HEADERS)
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def build_xlsx_upload(rows: list[list], headers: list[str] | None = None,
                      filename: str = "noor.xlsx") -> SimpleUploadedFile:
    return SimpleUploadedFile(
        filename,
        build_xlsx_bytes(rows, headers),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def noor_row(nid: str, name: str, grade: str = "الأول الثانوي", section: str = "1",
             number: str = "", guardian: str = "", mobile: str = "") -> list:
    return [nid, name, grade, section, number, guardian, mobile]
