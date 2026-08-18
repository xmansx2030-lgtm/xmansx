"""اختبارات أمان ملفات الاستيراد — ملفات خبيثة/مزيفة/ضخمة."""

import io
import zipfile
from datetime import date

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from academics.models import AcademicYear, AcademicYearStatus
from tests.xlsx_helper import build_xlsx_bytes, noor_row

IMPORTS_URL = "/api/v1/student-imports/"


@pytest.fixture
def import_manager(role_client):
    client, school, _ = role_client(["SCHOOL_MANAGER"])
    AcademicYear.objects.create(
        school=school, name="ع", start_date=date(2026, 8, 23),
        end_date=date(2027, 6, 25), status=AcademicYearStatus.ACTIVE,
    )
    return client, school


def _post(client, filename, content, content_type="application/octet-stream"):
    return client.post(
        IMPORTS_URL, {"file": SimpleUploadedFile(filename, content, content_type=content_type)}
    )


@pytest.mark.django_db
def test_text_file_renamed_xlsx_rejected(import_manager):
    client, _ = import_manager
    response = _post(client, "fake.xlsx", b"just plain text, not a zip at all")
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_IMPORT_FILE"


@pytest.mark.django_db
def test_corrupt_zip_rejected(import_manager):
    client, _ = import_manager
    corrupt = build_xlsx_bytes([noor_row("1012345678", "أحمد")])[:200]  # مقطوع
    response = _post(client, "corrupt.xlsx", corrupt)
    assert response.status_code == 400


@pytest.mark.django_db
def test_xlsm_macro_file_rejected(import_manager):
    client, _ = import_manager
    response = _post(client, "macros.xlsm", build_xlsx_bytes([noor_row("1012345678", "أحمد")]))
    assert response.status_code == 400
    assert response.json()["code"] == "UNSUPPORTED_IMPORT_FILE"


@pytest.mark.django_db
def test_legacy_xls_rejected(import_manager):
    client, _ = import_manager
    response = _post(client, "old.xls", b"\xd0\xcf\x11\xe0old-excel")
    assert response.json()["code"] == "UNSUPPORTED_IMPORT_FILE"


@pytest.mark.django_db
def test_oversized_file_rejected(import_manager):
    client, _ = import_manager
    big = build_xlsx_bytes([noor_row("1012345678", "أحمد")]) + b"\x00" * (10 * 1024 * 1024 + 1)
    response = _post(client, "big.xlsx", big)
    assert response.status_code == 400
    assert response.json()["code"] == "IMPORT_FILE_TOO_LARGE"


@pytest.mark.django_db
def test_zip_with_many_entries_rejected(import_manager):
    """حماية zip bomb: عدد مدخلات غير طبيعي يرفض قبل أي parsing."""
    client, _ = import_manager
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        for i in range(250):
            archive.writestr(f"entry_{i}.xml", "x")
    response = _post(client, "bomb.xlsx", buffer.getvalue())
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_IMPORT_FILE"


@pytest.mark.django_db
def test_zip_with_huge_uncompressed_content_rejected(import_manager):
    """محتوى قابل للتوسع لأحجام ضخمة يرفض من فحص الحجم غير المضغوط."""
    client, _ = import_manager
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("huge.xml", b"\x00" * (61 * 1024 * 1024))  # ينضغط لقليل جدًا
    assert len(buffer.getvalue()) < 10 * 1024 * 1024  # يمر فحص الحجم الخام
    response = _post(client, "bomb2.xlsx", buffer.getvalue())
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_IMPORT_FILE"


@pytest.mark.django_db
def test_formula_cells_are_not_executed(import_manager):
    """data_only: الصيغ لا تنفذ — قيمة الخلية الحرفية لا تسبب ضررًا."""
    client, _ = import_manager
    from tests.xlsx_helper import build_xlsx_upload

    rows = [["1012345678", "=cmd|'/c calc'!A1", "الأول الثانوي", "1"]]
    response = client.post(IMPORTS_URL, {"file": build_xlsx_upload(rows)})
    assert response.status_code == 201  # يقبل كنص عادي؛ لا تنفيذ لأي صيغة
