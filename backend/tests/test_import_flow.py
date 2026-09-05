"""اختبارات مسار الاستيراد كاملًا عبر API — ملفات xlsx حقيقية وCelery eager."""

from datetime import date

import pytest

from academics.models import AcademicYear, AcademicYearStatus
from students.models import EnrollmentStatus, Student, StudentEnrollment
from tests.xlsx_helper import (
    build_noor_report_upload,
    build_official_noor_upload,
    build_xlsx_upload,
    noor_row,
)

IMPORTS_URL = "/api/v1/student-imports/"


@pytest.fixture
def import_manager(role_client):
    """مدير مدرسة + عام دراسي نشط — الأساس لكل اختبارات الاستيراد."""
    client, school, user = role_client(["SCHOOL_MANAGER"])
    year = AcademicYear.objects.create(
        school=school, name="2026/2027",
        start_date=date(2026, 8, 23), end_date=date(2027, 6, 25),
        status=AcademicYearStatus.ACTIVE,
    )
    return client, school, year


def upload(client, rows, **kwargs):
    return client.post(IMPORTS_URL, {"file": build_xlsx_upload(rows, **kwargs)})


def process(client, job_id, mapping=None):
    body = {"mapping": mapping} if mapping else {}
    return client.post(
        f"{IMPORTS_URL}{job_id}/process/", body, content_type="application/json"
    )


def run_import(client, rows):
    """upload → process (eager) → commit — يعيد job النهائي."""
    job = upload(client, rows).json()
    process(client, job["id"])
    response = client.post(f"{IMPORTS_URL}{job['id']}/commit/")
    return response


@pytest.mark.django_db
def test_upload_suggests_mapping_from_noor_headers(import_manager):
    client, _, _ = import_manager
    response = upload(client, [noor_row("1012345678", "أحمد محمد")])
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "UPLOADED"
    suggested = body["suggested_mapping"]
    assert suggested["national_id"] == 0
    assert suggested["full_name"] == 1
    assert suggested["grade"] == 2
    assert suggested["section"] == 3


@pytest.mark.django_db
def test_noor_report_discovers_header_row_and_imports_data(import_manager):
    client, school, year = import_manager
    rows = [
        noor_row("1012345678", "أحمد محمد", "الأول الثانوي", "1", "S-1001"),
        noor_row("1012345679", "خالد سعد", "الأول الثانوي", "2", "S-1002"),
    ]
    response = client.post(IMPORTS_URL, {"file": build_noor_report_upload(rows)})

    assert response.status_code == 201
    job = response.json()
    assert job["header_row"] == 12
    assert job["suggested_mapping"] == {
        "national_id": 7,
        "full_name": 5,
        "grade": 1,
        "section": 3,
        "student_number": 9,
        "guardian_name": 11,
        "guardian_mobile": 13,
    }

    assert process(client, job["id"]).status_code == 202
    preview = client.get(f"{IMPORTS_URL}{job['id']}/preview/").json()["results"]
    assert [row["row_number"] for row in preview] == [13, 14]

    committed = client.post(f"{IMPORTS_URL}{job['id']}/commit/")
    assert committed.status_code == 200
    assert Student.objects.filter(school=school).count() == 2
    assert StudentEnrollment.objects.filter(
        school=school, academic_year=year, status=EnrollmentStatus.ACTIVE
    ).count() == 2


@pytest.mark.django_db
def test_official_noor_report_combines_all_sheets_and_extracts_page_grade(import_manager):
    client, school, year = import_manager
    upload_file = build_official_noor_upload(
        [
            {
                "grade": "الأول الثانوي",
                "section": "1",
                "rows": [
                    noor_row("1012345678", "طالب أول", section="1", guardian="ولي أول"),
                    noor_row("1012345679", "طالب ثان", section="1", guardian="ولي ثان"),
                ],
            },
            {
                "grade": "الأول الثانوي",
                "section": "1",
                "rows": [noor_row("1012345680", "طالب ثالث", section="1")],
            },
            {
                "grade": "الثاني الثانوي",
                "section": "2",
                "section_metadata": False,
                "department": "المسار العام",
                "rows": [noor_row("2012345678", "طالب رابع", section="2")],
            },
        ]
    )
    response = client.post(IMPORTS_URL, {"file": upload_file})

    assert response.status_code == 201
    job = response.json()
    assert job["import_format"] == "NOOR_OFFICIAL_MULTI_SHEET"
    assert job["source_sheet_count"] == 3
    assert job["detected_rows"] == 4
    assert job["header_row"] == 21
    assert job["suggested_mapping"]["national_id"] == 20
    assert job["suggested_mapping"]["full_name"] == 28
    assert job["suggested_mapping"]["section"] == 18
    assert job["suggested_mapping"]["guardian_name"] == 16
    assert job["suggested_mapping"]["grade"] == 30
    assert job["suggested_mapping"]["guardian_mobile"] is None

    assert process(client, job["id"]).status_code == 202
    status_body = client.get(f"{IMPORTS_URL}{job['id']}/").json()
    assert status_body["status"] == "READY_FOR_REVIEW"
    assert status_body["total_rows"] == 4
    assert status_body["summary"]["new"] == 4
    assert set(status_body["summary"]["will_create_grades"]) == {
        "الأول الثانوي",
        "الثاني الثانوي",
    }

    preview = client.get(f"{IMPORTS_URL}{job['id']}/preview/").json()["results"]
    assert [row["row_number"] for row in preview] == [22, 23, 24, 25]
    assert {row["data"]["grade_name"] for row in preview} == {
        "الأول الثانوي",
        "الثاني الثانوي",
    }

    committed = client.post(f"{IMPORTS_URL}{job['id']}/commit/")
    assert committed.status_code == 200
    committed_job = committed.json()
    assert committed_job["import_format"] == "NOOR_OFFICIAL_MULTI_SHEET"
    assert committed_job["source_sheet_count"] == 3
    assert committed_job["detected_rows"] == 4
    assert Student.objects.filter(school=school).count() == 4
    assert StudentEnrollment.objects.filter(
        school=school, academic_year=year, status=EnrollmentStatus.ACTIVE
    ).count() == 4


@pytest.mark.django_db
def test_upload_requires_active_academic_year(role_client):
    client, _, _ = role_client(["SCHOOL_MANAGER"])  # بلا عام نشط
    response = upload(client, [noor_row("1012345678", "أحمد")])
    assert response.status_code == 409
    assert response.json()["code"] == "ACTIVE_ACADEMIC_YEAR_REQUIRED"


@pytest.mark.django_db
def test_full_import_creates_students_and_enrollments(import_manager):
    client, school, year = import_manager
    rows = [
        noor_row("1012345678", "أحمد محمد", "الأول الثانوي", "1"),
        noor_row("1012345679", "خالد سعد", "الأول الثانوي", "2"),
        noor_row("2098765432", "فهد العتيبي", "الثاني الثانوي", "1"),
    ]
    job = upload(client, rows).json()
    processed = process(client, job["id"])
    assert processed.status_code == 202

    status_body = client.get(f"{IMPORTS_URL}{job['id']}/").json()
    assert status_body["status"] == "READY_FOR_REVIEW"
    assert status_body["summary"]["new"] == 3
    assert "الأول الثانوي" in status_body["summary"]["will_create_grades"]

    commit = client.post(f"{IMPORTS_URL}{job['id']}/commit/")
    assert commit.status_code == 200
    summary = commit.json()["summary"]
    assert summary["created"] == 3

    assert Student.objects.filter(school=school).count() == 3
    assert StudentEnrollment.objects.filter(
        school=school, academic_year=year, status=EnrollmentStatus.ACTIVE
    ).count() == 3
    # الهوية غير مخزنة plaintext
    student = Student.objects.get(full_name="أحمد محمد")
    assert "1012345678" not in student.national_id_encrypted
    assert student.national_id_masked == "******5678"


@pytest.mark.django_db
def test_identical_reimport_is_all_unchanged(import_manager):
    client, school, year = import_manager
    rows = [noor_row("1012345678", "أحمد محمد", "الأول الثانوي", "1")]
    run_import(client, rows)
    enrollment_id = StudentEnrollment.objects.get(school=school).id

    second = run_import(client, rows)
    assert second.status_code == 200
    summary = second.json()["summary"]
    assert summary["unchanged"] == 1
    assert summary["created"] == 0
    assert summary["enrollment_changes"] == 0
    # لا Enrollment جديد لاستيراد مطابق
    assert StudentEnrollment.objects.filter(school=school).count() == 1
    assert StudentEnrollment.objects.get(school=school).id == enrollment_id


@pytest.mark.django_db
def test_section_change_creates_history_not_edit(import_manager):
    client, school, year = import_manager
    run_import(client, [noor_row("1012345678", "أحمد محمد", "الأول الثانوي", "1")])

    second = run_import(client, [noor_row("1012345678", "أحمد محمد", "الأول الثانوي", "3")])
    assert second.json()["summary"]["enrollment_changes"] == 1

    enrollments = StudentEnrollment.objects.filter(school=school).order_by("id")
    assert enrollments.count() == 2
    old, new = enrollments
    assert old.status == EnrollmentStatus.TRANSFERRED
    assert old.ended_at is not None
    assert old.section.code == "1"
    assert new.status == EnrollmentStatus.ACTIVE
    assert new.section.code == "3"


@pytest.mark.django_db
def test_missing_students_are_reported_not_deleted(import_manager):
    client, school, _ = import_manager
    run_import(client, [
        noor_row("1012345678", "أحمد محمد"),
        noor_row("1012345679", "خالد سعد"),
    ])
    # الملف الجديد بلا خالد
    job = upload(client, [noor_row("1012345678", "أحمد محمد")]).json()
    process(client, job["id"])
    preview = client.get(f"{IMPORTS_URL}{job['id']}/").json()
    assert preview["summary"]["missing_from_file"] == 1
    assert preview["summary"]["missing_names"][0]["name"] == "خالد سعد"

    client.post(f"{IMPORTS_URL}{job['id']}/commit/")
    # خالد لم يحذف ولم يتغير
    khaled = Student.objects.get(full_name="خالد سعد")
    assert khaled.status == "ACTIVE"
    assert khaled.enrollments.filter(status=EnrollmentStatus.ACTIVE).exists()


@pytest.mark.django_db
def test_name_change_detected_and_applied_with_audit(import_manager):
    from audit.models import AuditLog

    client, school, _ = import_manager
    run_import(client, [noor_row("1012345678", "أحمد محمد")])
    job = upload(client, [noor_row("1012345678", "أحمد محمد العتيبي")]).json()
    process(client, job["id"])
    preview = client.get(f"{IMPORTS_URL}{job['id']}/").json()
    assert preview["summary"]["updated"] == 1

    rows = client.get(
        f"{IMPORTS_URL}{job['id']}/preview/?category=EXISTING_UPDATED"
    ).json()["results"]
    assert rows[0]["data"]["changes"]["full_name"] == {
        "from": "أحمد محمد", "to": "أحمد محمد العتيبي"
    }

    client.post(f"{IMPORTS_URL}{job['id']}/commit/")
    assert Student.objects.get(school=school).full_name == "أحمد محمد العتيبي"
    log = AuditLog.objects.get(action="STUDENT_UPDATED")
    assert log.metadata["changed_fields"] == ["full_name"]


@pytest.mark.django_db
def test_row_errors_and_duplicates_categorized(import_manager):
    client, _, _ = import_manager
    rows = [
        noor_row("1012345678", "صالح"),
        noor_row("123", "هوية خاطئة"),            # INVALID_NATIONAL_ID
        noor_row("1012345679", ""),                # MISSING_NAME
        noor_row("1012345680", "مكرر أول"),
        noor_row("١٠١٢٣٤٥٦٨٠", "مكرر ثاني"),      # نفس الهوية بأرقام عربية
    ]
    job = upload(client, rows).json()
    process(client, job["id"])
    body = client.get(f"{IMPORTS_URL}{job['id']}/").json()
    assert body["summary"]["errors"] == 2
    assert body["summary"]["duplicates"] == 2
    assert body["summary"]["new"] == 1

    errors = client.get(f"{IMPORTS_URL}{job['id']}/preview/?category=ERROR").json()["results"]
    codes = {r["error_codes"][0] for r in errors}
    assert codes == {"INVALID_NATIONAL_ID", "MISSING_NAME"}
    # رسالة عربية مع رقم الصف
    assert all(r["error_message"] for r in errors)
    # لا plaintext في بيانات المعاينة
    assert "1012345680" not in str(body)


@pytest.mark.django_db
def test_commit_twice_is_idempotent(import_manager):
    client, school, _ = import_manager
    rows = [noor_row("1012345678", "أحمد محمد")]
    job = upload(client, rows).json()
    process(client, job["id"])
    first = client.post(f"{IMPORTS_URL}{job['id']}/commit/")
    assert first.status_code == 200
    second = client.post(f"{IMPORTS_URL}{job['id']}/commit/")
    assert second.status_code == 409
    assert second.json()["code"] == "IMPORT_ALREADY_COMMITTED"
    assert Student.objects.filter(school=school).count() == 1
    assert StudentEnrollment.objects.filter(school=school).count() == 1


@pytest.mark.django_db
def test_stale_preview_detected_on_commit(import_manager):
    """معاينة قديمة: تغيرت البيانات بين المعاينة والاعتماد → IMPORT_PREVIEW_STALE."""
    client, school, year = import_manager
    run_import(client, [noor_row("1012345678", "أحمد محمد", "الأول الثانوي", "1")])

    # ملف جديد يعيد نفس الطالب في فصله (سيصنف: بلا تغيير)
    job = upload(client, [noor_row("1012345678", "أحمد محمد", "الأول الثانوي", "1")]).json()
    process(client, job["id"])
    assert client.get(f"{IMPORTS_URL}{job['id']}/").json()["summary"]["unchanged"] == 1

    # يتغير الواقع قبل الاعتماد: استيراد آخر ينقل الطالب لفصل 2
    other_job = run_import(client, [noor_row("1012345678", "أحمد محمد", "الأول الثانوي", "2")])
    assert other_job.status_code == 200

    # الاعتماد بالمعاينة القديمة يكتشف التعارض ويعيد بناءها
    commit = client.post(f"{IMPORTS_URL}{job['id']}/commit/")
    assert commit.status_code == 409
    assert commit.json()["code"] == "IMPORT_PREVIEW_STALE"
    refreshed = client.get(f"{IMPORTS_URL}{job['id']}/").json()
    assert refreshed["status"] == "READY_FOR_REVIEW"
    assert refreshed["summary"]["section_changed"] == 1  # المعاينة حدثت

    # الاعتماد بعد المراجعة يعمل — ويعيد الطالب لفصل 1
    final = client.post(f"{IMPORTS_URL}{job['id']}/commit/")
    assert final.status_code == 200
    active = StudentEnrollment.objects.get(school=school, status=EnrollmentStatus.ACTIVE)
    assert active.section.code == "1"


@pytest.mark.django_db
def test_academic_year_change_invalidates_job(import_manager):
    client, school, year = import_manager
    job = upload(client, [noor_row("1012345678", "أحمد")]).json()
    process(client, job["id"])

    # يغلق العام النشط قبل الاعتماد
    year.status = AcademicYearStatus.CLOSED
    year.save(update_fields=["status"])

    commit = client.post(f"{IMPORTS_URL}{job['id']}/commit/")
    assert commit.status_code == 409
    assert commit.json()["code"] == "ACTIVE_ACADEMIC_YEAR_REQUIRED"
    assert Student.objects.filter(school=school).count() == 0


@pytest.mark.django_db
def test_mapping_ui_flow_with_custom_headers(import_manager):
    """رؤوس غير معروفة → اقتراح ناقص → المستخدم يمرر mapping يدويًا."""
    client, school, _ = import_manager
    headers = ["العمود أ", "العمود ب", "العمود ج", "العمود د"]
    rows = [["1012345678", "أحمد محمد", "الأول الثانوي", "1"]]
    job = upload(client, rows, headers=headers).json()
    assert job["suggested_mapping"]["national_id"] is None

    # بلا mapping → رفض واضح
    missing = process(client, job["id"])
    assert missing.status_code == 400
    assert missing.json()["code"] == "IMPORT_MISSING_REQUIRED_COLUMN"

    manual = {"national_id": 0, "full_name": 1, "grade": 2, "section": 3}
    assert process(client, job["id"], mapping=manual).status_code == 202
    assert client.get(f"{IMPORTS_URL}{job['id']}/").json()["summary"]["new"] == 1
