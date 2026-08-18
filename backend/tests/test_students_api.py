"""اختبارات قوائم الطلاب: البحث، الترقيم، التقنيع، الأدوار، العزل، N+1."""

from datetime import date

import pytest
from django.db import IntegrityError, transaction

from academics.models import AcademicYear, AcademicYearStatus
from common.security.identifiers import (
    encrypt_national_id,
    mask_national_id,
    national_id_lookup_hash,
)
from students.models import Grade, Section, Student, StudentEnrollment

STUDENTS_URL = "/api/v1/students/"


def _make_student(school, nid: str, name: str, number: str | None = None) -> Student:
    return Student.objects.create(
        school=school,
        national_id_encrypted=encrypt_national_id(nid),
        national_id_lookup_hash=national_id_lookup_hash(nid),
        national_id_masked=mask_national_id(nid),
        student_number=number,
        full_name=name,
    )


def _enroll(school, student, code="1"):
    year, _ = AcademicYear.objects.get_or_create(
        school=school, name="ع",
        defaults={
            "start_date": date(2026, 8, 23), "end_date": date(2027, 6, 25),
            "status": AcademicYearStatus.ACTIVE,
        },
    )
    grade, _ = Grade.objects.get_or_create(
        school=school, code="SEC_1", defaults={"name": "الأول الثانوي", "sequence": 10}
    )
    section, _ = Section.objects.get_or_create(
        school=school, grade=grade, code=code, defaults={"name": code}
    )
    return StudentEnrollment.objects.create(
        school=school, student=student, academic_year=year,
        grade=grade, section=section, enrolled_at=date(2026, 8, 23),
    )


# ---------- uniqueness ----------


@pytest.mark.django_db
def test_same_national_id_same_school_rejected(make_school):
    school = make_school()
    _make_student(school, "1012345678", "أحمد")
    with pytest.raises(IntegrityError), transaction.atomic():
        _make_student(school, "1012345678", "آخر")


@pytest.mark.django_db
def test_same_national_id_different_school_allowed(make_school):
    a, b = make_school(), make_school()
    _make_student(a, "1012345678", "أحمد في أ")
    student_b = _make_student(b, "1012345678", "أحمد في ب")
    assert student_b.id  # سجلان مستقلان — لا ربط تلقائي بين المدارس


@pytest.mark.django_db
def test_one_active_enrollment_per_year_db_constraint(make_school):
    school = make_school()
    student = _make_student(school, "1012345678", "أحمد")
    _enroll(school, student, code="1")
    with pytest.raises(IntegrityError), transaction.atomic():
        _enroll(school, student, code="2")  # ACTIVE ثانٍ لنفس العام


@pytest.mark.django_db
def test_cross_school_enrollment_blocked(make_school):
    from common.errors import ApiError
    from students.services.enrollments import validate_enrollment_integrity

    a, b = make_school(), make_school()
    student = _make_student(b, "1012345678", "طالب ب")
    enrollment = _enroll(a, _make_student(a, "2098765432", "طالب أ"))
    with pytest.raises(ApiError) as excinfo:
        validate_enrollment_integrity(
            school=a, student=student,
            grade=enrollment.grade, section=enrollment.section,
            academic_year=enrollment.academic_year,
        )
    assert excinfo.value.code == "INVALID_ENROLLMENT"


# ---------- list & search ----------


@pytest.mark.django_db
def test_student_list_masked_and_paginated(role_client):
    client, school, _ = role_client(["SCHOOL_MANAGER"])
    for i in range(30):
        student = _make_student(school, f"10123456{i:02d}", f"طالب {i:02d}")
        _enroll(school, student)
    response = client.get(STUDENTS_URL)
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 30
    assert len(body["results"]) == 25  # page size
    first = body["results"][0]
    assert first["national_id_masked"].startswith("******")
    assert first["grade"]["name"] == "الأول الثانوي"
    # لا رقم هوية كامل في أي مكان بالاستجابة
    assert "10123456" not in str([r["national_id_masked"] for r in body["results"]])


@pytest.mark.django_db
def test_search_by_name(role_client):
    client, school, _ = role_client(["SCHOOL_MANAGER"])
    _make_student(school, "1012345678", "أحمد العتيبي")
    _make_student(school, "1012345679", "خالد الشمري")
    body = client.get(f"{STUDENTS_URL}?search=العتيبي").json()
    assert body["count"] == 1
    assert body["results"][0]["full_name"] == "أحمد العتيبي"


@pytest.mark.django_db
def test_search_by_national_id_exact_via_hmac(role_client):
    client, school, _ = role_client(["SCHOOL_MANAGER"])
    _make_student(school, "1012345678", "أحمد")
    _make_student(school, "1012345679", "خالد")
    # بأي صيغة إدخال (أرقام عربية) — مطابقة دقيقة عبر HMAC
    body = client.get(f"{STUDENTS_URL}?national_id=١٠١٢٣٤٥٦٧٨").json()
    assert body["count"] == 1
    assert body["results"][0]["full_name"] == "أحمد"
    # جزء من الرقم لا يطابق (لا contains على قيمة مشفرة)
    assert client.get(f"{STUDENTS_URL}?national_id=10123456").json()["count"] == 0


@pytest.mark.django_db
def test_student_list_query_count_bounded(role_client, django_assert_max_num_queries):
    client, school, _ = role_client(["SCHOOL_MANAGER"])
    for i in range(40):
        _enroll(school, _make_student(school, f"10123456{i:02d}", f"طالب {i}"))
    with django_assert_max_num_queries(10):
        response = client.get(STUDENTS_URL)
    assert response.status_code == 200


# ---------- roles & isolation ----------


@pytest.mark.django_db
def test_roles_matrix_for_students(role_client, make_school):
    school = make_school()
    manager, _, _ = role_client(["SCHOOL_MANAGER"], school=school)
    vice, _, _ = role_client(["VICE_PRINCIPAL"], school=school)
    counselor, _, _ = role_client(["COUNSELOR"], school=school)
    teacher, _, _ = role_client(["TEACHER"], school=school)

    assert manager.get(STUDENTS_URL).status_code == 200
    assert vice.get(STUDENTS_URL).status_code == 200
    assert counselor.get(STUDENTS_URL).status_code == 200
    assert teacher.get(STUDENTS_URL).status_code == 403  # لا قائمة عامة للمعلم

    # الاستيراد للمدير فقط
    from tests.xlsx_helper import build_xlsx_upload, noor_row

    upload = {"file": build_xlsx_upload([noor_row("1012345678", "أحمد")])}
    assert vice.post("/api/v1/student-imports/", upload).status_code == 403
    assert teacher.post("/api/v1/student-imports/", upload).status_code == 403


@pytest.mark.django_db
def test_tenant_isolation_students_and_imports(role_client):
    from datetime import date as d

    manager_a, school_a, _ = role_client(["SCHOOL_MANAGER"])
    manager_b, school_b, _ = role_client(["SCHOOL_MANAGER"])
    AcademicYear.objects.create(
        school=school_b, name="ع", start_date=d(2026, 8, 23),
        end_date=d(2027, 6, 25), status=AcademicYearStatus.ACTIVE,
    )
    foreign_student = _make_student(school_b, "1012345678", "طالب ب")
    _enroll(school_b, foreign_student)

    from tests.xlsx_helper import build_xlsx_upload, noor_row

    foreign_job = manager_b.post(
        "/api/v1/student-imports/", {"file": build_xlsx_upload([noor_row("2098765432", "س")])}
    ).json()

    # كل معرفات B ترجع 404 لمدير A
    assert manager_a.get(f"{STUDENTS_URL}{foreign_student.id}/").status_code == 404
    assert manager_a.get(f"/api/v1/student-imports/{foreign_job['id']}/").status_code == 404
    assert manager_a.post(f"/api/v1/student-imports/{foreign_job['id']}/commit/").status_code == 404
    # والقوائم لا تسرب
    assert manager_a.get(STUDENTS_URL).json()["count"] == 0
    grade_b = Grade.objects.get(school=school_b)
    section_b = Section.objects.get(school=school_b)
    a_grades = [g["id"] for g in manager_a.get("/api/v1/grades/").json()]
    a_sections = [s["id"] for s in manager_a.get("/api/v1/sections/").json()]
    assert grade_b.id not in a_grades
    assert section_b.id not in a_sections
