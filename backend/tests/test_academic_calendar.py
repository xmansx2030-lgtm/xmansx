"""اختبارات العام الدراسي والفصول: القيود، التفعيل الذري، العزل."""

from datetime import date

import pytest
from django.db import IntegrityError, transaction

from academics.models import AcademicYear, AcademicYearStatus, Semester

YEARS_URL = "/api/v1/school/academic-years/"


def _create_year(client, name="2026/2027", start="2026-08-23", end="2027-06-25"):
    return client.post(
        YEARS_URL,
        {"name": name, "start_date": start, "end_date": end},
        content_type="application/json",
    )


@pytest.mark.django_db
def test_create_year_and_list(role_client):
    client, _, _ = role_client(["SCHOOL_MANAGER"])
    response = _create_year(client)
    assert response.status_code == 201
    assert response.json()["status"] == "UPCOMING"
    assert len(client.get(YEARS_URL).json()) == 1


@pytest.mark.django_db
def test_invalid_year_range_rejected(role_client):
    client, _, _ = role_client(["SCHOOL_MANAGER"])
    response = _create_year(client, start="2027-06-25", end="2026-08-23")
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_ACADEMIC_YEAR_RANGE"


@pytest.mark.django_db
def test_activate_year_demotes_previous_active(role_client):
    client, _, _ = role_client(["SCHOOL_MANAGER"])
    y1 = _create_year(client, name="سنة 1").json()
    y2 = _create_year(client, name="سنة 2", start="2027-08-22", end="2028-06-20").json()

    assert client.post(f"{YEARS_URL}{y1['id']}/activate/").status_code == 200
    assert client.post(f"{YEARS_URL}{y2['id']}/activate/").status_code == 200

    years = {y["name"]: y["status"] for y in client.get(YEARS_URL).json()}
    assert years["سنة 2"] == "ACTIVE"
    assert years["سنة 1"] == "CLOSED"


@pytest.mark.django_db
def test_activate_already_active_year_conflict(role_client):
    client, _, _ = role_client(["SCHOOL_MANAGER"])
    year = _create_year(client).json()
    client.post(f"{YEARS_URL}{year['id']}/activate/")
    response = client.post(f"{YEARS_URL}{year['id']}/activate/")
    assert response.status_code == 409
    assert response.json()["code"] == "ACADEMIC_YEAR_ALREADY_ACTIVE"


@pytest.mark.django_db
def test_db_constraint_one_active_year_per_school(make_school):
    """القيد في قاعدة البيانات نفسها — الحكم النهائي ضد التزامن (البند 36)."""
    school = make_school()
    AcademicYear.objects.create(
        school=school, name="أ", start_date=date(2026, 8, 1), end_date=date(2027, 6, 1),
        status=AcademicYearStatus.ACTIVE,
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        AcademicYear.objects.create(
            school=school, name="ب", start_date=date(2027, 8, 1), end_date=date(2028, 6, 1),
            status=AcademicYearStatus.ACTIVE,
        )


@pytest.mark.django_db
def test_two_schools_can_each_have_active_year(make_school):
    a, b = make_school(), make_school()
    for school in (a, b):
        AcademicYear.objects.create(
            school=school, name="نشط", start_date=date(2026, 8, 1),
            end_date=date(2027, 6, 1), status=AcademicYearStatus.ACTIVE,
        )
    assert AcademicYear.objects.filter(status="ACTIVE").count() == 2


@pytest.mark.django_db
def test_foreign_school_year_ids_return_404(role_client):
    """IDOR: معرفات عام مدرسة أخرى — قراءة وتعديل وتفعيل كلها 404."""
    manager_a, _, _ = role_client(["SCHOOL_MANAGER"])
    manager_b, _, _ = role_client(["SCHOOL_MANAGER"])
    foreign_year = _create_year(manager_b).json()

    assert manager_a.patch(
        f"{YEARS_URL}{foreign_year['id']}/", {"name": "اختراق"},
        content_type="application/json",
    ).status_code == 404
    assert manager_a.post(f"{YEARS_URL}{foreign_year['id']}/activate/").status_code == 404
    assert manager_a.post(
        f"{YEARS_URL}{foreign_year['id']}/semesters/",
        {"name": "ف1", "sequence": 1, "start_date": "2026-09-01", "end_date": "2026-12-01"},
        content_type="application/json",
    ).status_code == 404


@pytest.mark.django_db
def test_vice_can_read_years_but_not_create(role_client, make_school):
    school = make_school()
    manager, _, _ = role_client(["SCHOOL_MANAGER"], school=school)
    _create_year(manager)
    vice, _, _ = role_client(["VICE_PRINCIPAL"], school=school)
    assert vice.get(YEARS_URL).status_code == 200
    assert _create_year(vice, name="آخر").status_code == 403


# ---------- Semesters ----------


@pytest.mark.django_db
def test_semester_created_inside_year(role_client):
    client, school, _ = role_client(["SCHOOL_MANAGER"])
    year = _create_year(client).json()
    response = client.post(
        f"{YEARS_URL}{year['id']}/semesters/",
        {"name": "الفصل الأول", "sequence": 1, "start_date": "2026-08-23",
         "end_date": "2026-12-10"},
        content_type="application/json",
    )
    assert response.status_code == 201
    semester = Semester.objects.get(id=response.json()["id"])
    assert semester.school_id == school.id  # school من الخادم لا من العميل


@pytest.mark.django_db
def test_semester_outside_year_rejected(role_client):
    client, _, _ = role_client(["SCHOOL_MANAGER"])
    year = _create_year(client).json()
    response = client.post(
        f"{YEARS_URL}{year['id']}/semesters/",
        {"name": "خارج", "sequence": 1, "start_date": "2026-01-01", "end_date": "2026-05-01"},
        content_type="application/json",
    )
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_SEMESTER_RANGE"


@pytest.mark.django_db
def test_semester_invalid_dates_rejected(role_client):
    client, _, _ = role_client(["SCHOOL_MANAGER"])
    year = _create_year(client).json()
    response = client.post(
        f"{YEARS_URL}{year['id']}/semesters/",
        {"name": "مقلوب", "sequence": 1, "start_date": "2026-12-01", "end_date": "2026-09-01"},
        content_type="application/json",
    )
    assert response.json()["code"] == "INVALID_SEMESTER_RANGE"


@pytest.mark.django_db
def test_semester_duplicate_sequence_rejected(role_client):
    client, _, _ = role_client(["SCHOOL_MANAGER"])
    year = _create_year(client).json()
    payload = {"name": "ف", "sequence": 1, "start_date": "2026-09-01", "end_date": "2026-11-01"}
    assert client.post(
        f"{YEARS_URL}{year['id']}/semesters/", payload, content_type="application/json"
    ).status_code == 201
    response = client.post(
        f"{YEARS_URL}{year['id']}/semesters/",
        {**payload, "name": "مكرر", "start_date": "2026-11-02", "end_date": "2026-12-01"},
        content_type="application/json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_semester_activation_demotes_and_db_constraint(role_client, make_school):
    client, school, _ = role_client(["SCHOOL_MANAGER"])
    year = _create_year(client).json()
    s1 = client.post(
        f"{YEARS_URL}{year['id']}/semesters/",
        {"name": "ف1", "sequence": 1, "start_date": "2026-08-23", "end_date": "2026-12-10"},
        content_type="application/json",
    ).json()
    s2 = client.post(
        f"{YEARS_URL}{year['id']}/semesters/",
        {"name": "ف2", "sequence": 2, "start_date": "2026-12-11", "end_date": "2027-03-10"},
        content_type="application/json",
    ).json()

    assert client.post(f"/api/v1/school/semesters/{s1['id']}/activate/").status_code == 200
    assert client.post(f"/api/v1/school/semesters/{s2['id']}/activate/").status_code == 200
    statuses = {s.name: s.status for s in Semester.objects.filter(school=school)}
    assert statuses == {"ف1": "CLOSED", "ف2": "ACTIVE"}

    # القيد المباشر في قاعدة البيانات
    with pytest.raises(IntegrityError), transaction.atomic():
        Semester.objects.filter(id=s1["id"]).update(status="ACTIVE")
