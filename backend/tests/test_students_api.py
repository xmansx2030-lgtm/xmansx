"""اختبارات قوائم الطلاب: البحث، الترقيم، التقنيع، الأدوار، العزل، N+1."""

from datetime import date

import pytest
from django.db import IntegrityError, transaction

from academics.models import AcademicYear, AcademicYearStatus
from common.security.identifiers import (
    decrypt_national_id,
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
        school=school,
        name="ع",
        defaults={
            "start_date": date(2026, 8, 23),
            "end_date": date(2027, 6, 25),
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
        school=school,
        student=student,
        academic_year=year,
        grade=grade,
        section=section,
        enrolled_at=date(2026, 8, 23),
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
            school=a,
            student=student,
            grade=enrollment.grade,
            section=enrollment.section,
            academic_year=enrollment.academic_year,
        )
    assert excinfo.value.code == "INVALID_ENROLLMENT"


# ---------- list & search ----------


@pytest.mark.django_db
def test_manager_creates_student_manually(role_client):
    client, school, _ = role_client(["SCHOOL_MANAGER"])
    existing = _make_student(school, "1012345678", "طالب تمهيدي")
    enrollment = _enroll(school, existing)

    response = client.post(
        STUDENTS_URL,
        {
            "full_name": "طالب يدوي",
            "national_id": "١٠٩٨٧٦٥٤٣٢",
            "student_number": "S-100",
            "guardian_name": "ولي الطالب",
            "guardian_mobile": "0551234567",
            "section_id": enrollment.section_id,
        },
        content_type="application/json",
    )

    assert response.status_code == 201
    assert response.json()["full_name"] == "طالب يدوي"
    assert response.json()["national_id_masked"] == "******5432"
    created = Student.objects.get(full_name="طالب يدوي", school=school)
    assert created.guardian_mobile == "+966551234567"
    assert created.enrollments.get().section_id == enrollment.section_id


@pytest.mark.django_db
def test_manual_student_rejects_duplicate_and_non_manager(role_client, make_school):
    school = make_school()
    manager, _, _ = role_client(["SCHOOL_MANAGER"], school=school)
    vice, _, _ = role_client(["VICE_PRINCIPAL"], school=school)
    enrollment = _enroll(school, _make_student(school, "1012345678", "موجود"))
    payload = {
        "full_name": "مكرر",
        "national_id": "1012345678",
        "section_id": enrollment.section_id,
    }
    assert manager.post(STUDENTS_URL, payload, content_type="application/json").status_code == 409
    assert (
        vice.post(
            STUDENTS_URL,
            {**payload, "national_id": "1098765432"},
            content_type="application/json",
        ).status_code
        == 403
    )


@pytest.mark.django_db
def test_manager_corrects_student_identity_profile_and_section(role_client):
    from audit.models import AuditAction, AuditLog

    client, school, _ = role_client(["SCHOOL_MANAGER"])
    student = _make_student(school, "1012345678", "اسم قديم", "S-1")
    old_enrollment = _enroll(school, student, code="1")
    new_section = Section.objects.create(
        school=school,
        grade=old_enrollment.grade,
        code="2",
        name="2",
    )

    response = client.patch(
        f"{STUDENTS_URL}{student.id}/",
        {
            "full_name": "اسم مصحح",
            "national_id": "٢٠٩٨٧٦٥٤٣٢",
            "student_number": "S-2",
            "guardian_name": "ولي مصحح",
            "guardian_mobile": "0551234567",
            "section_id": new_section.id,
        },
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.json()["national_id_masked"] == "******5432"
    assert response.json()["section"]["id"] == new_section.id
    student.refresh_from_db()
    assert decrypt_national_id(student.national_id_encrypted) == "2098765432"
    assert student.guardian_mobile == "+966551234567"
    old_enrollment.refresh_from_db()
    assert old_enrollment.status == "TRANSFERRED"
    assert student.enrollments.get(status="ACTIVE").section_id == new_section.id
    audit = AuditLog.objects.filter(
        action=AuditAction.STUDENT_UPDATED, target_id=str(student.id)
    ).latest("id")
    assert "national_id" in audit.metadata["changed_fields"]
    assert "2098765432" not in str(audit.metadata)


@pytest.mark.django_db
def test_student_correction_rejects_invalid_duplicate_and_non_manager(role_client, make_school):
    school = make_school()
    manager, _, _ = role_client(["SCHOOL_MANAGER"], school=school)
    vice, _, _ = role_client(["VICE_PRINCIPAL"], school=school)
    first = _make_student(school, "1012345678", "الأول")
    second = _make_student(school, "1098765432", "الثاني")

    invalid = manager.patch(
        f"{STUDENTS_URL}{first.id}/",
        {"national_id": "123"},
        content_type="application/json",
    )
    assert invalid.status_code == 400
    assert "10 أرقام" in str(invalid.json())

    duplicate = manager.patch(
        f"{STUDENTS_URL}{first.id}/",
        {"national_id": "1098765432"},
        content_type="application/json",
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "STUDENT_ALREADY_EXISTS"

    denied = vice.patch(
        f"{STUDENTS_URL}{second.id}/",
        {"full_name": "تعديل غير مسموح"},
        content_type="application/json",
    )
    assert denied.status_code == 403


@pytest.mark.django_db
def test_student_correction_is_tenant_isolated(role_client, make_school):
    school_a = make_school()
    school_b = make_school()
    manager, _, _ = role_client(["SCHOOL_MANAGER"], school=school_a)
    foreign = _make_student(school_b, "1012345678", "طالب مدرسة أخرى")

    response = manager.patch(
        f"{STUDENTS_URL}{foreign.id}/",
        {"full_name": "محاولة تعديل"},
        content_type="application/json",
    )

    assert response.status_code == 404
    foreign.refresh_from_db()
    assert foreign.full_name == "طالب مدرسة أخرى"


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
def test_manager_creates_grade_and_section_from_settings(role_client):
    manager, school, _ = role_client(["SCHOOL_MANAGER"])
    grade_response = manager.post(
        "/api/v1/grades/",
        {"name": "الثالث المتوسط", "code": "MID-3", "sequence": 3},
        content_type="application/json",
    )
    assert grade_response.status_code == 201
    section_response = manager.post(
        "/api/v1/sections/",
        {"grade_id": grade_response.json()["id"], "name": "أ", "code": "A"},
        content_type="application/json",
    )
    assert section_response.status_code == 201
    assert section_response.json()["grade"]["name"] == "الثالث المتوسط"
    assert Grade.objects.filter(school=school, code="MID-3").exists()
    assert Section.objects.filter(school=school, code="A").exists()


@pytest.mark.django_db
def test_only_manager_can_create_structure_and_codes_are_unique(role_client):
    school = role_client(["SCHOOL_MANAGER"])[1]
    manager, _, _ = role_client(["SCHOOL_MANAGER"], school=school)
    vice, _, _ = role_client(["VICE_PRINCIPAL"], school=school)
    payload = {"name": "الأول المتوسط", "code": "MID-1", "sequence": 1}
    assert (
        manager.post("/api/v1/grades/", payload, content_type="application/json").status_code == 201
    )
    duplicate = manager.post("/api/v1/grades/", payload, content_type="application/json")
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "GRADE_CODE_ALREADY_EXISTS"
    assert (
        vice.post(
            "/api/v1/grades/", {**payload, "code": "MID-2"}, content_type="application/json"
        ).status_code
        == 403
    )


@pytest.mark.django_db
def test_tenant_isolation_students_and_imports(role_client):
    from datetime import date as d

    manager_a, school_a, _ = role_client(["SCHOOL_MANAGER"])
    manager_b, school_b, _ = role_client(["SCHOOL_MANAGER"])
    AcademicYear.objects.create(
        school=school_b,
        name="ع",
        start_date=d(2026, 8, 23),
        end_date=d(2027, 6, 25),
        status=AcademicYearStatus.ACTIVE,
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
