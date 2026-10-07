"""Real Ministry fixture, explicit +9 rule, atomic activation and roster safety."""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from django.db import DatabaseError, close_old_connections, connection, transaction
from django.test import Client
from django.utils import timezone

from academics.ministry_models import (
    MinistryCalendarSnapshot,
    MinistryCalendarSync,
    SchoolCalendarPolicy,
)
from academics.models import AcademicYear, Semester
from academics.services.ministry_calendar import (
    apply_ministry_calendars,
    apply_school_calendar,
    sync_ministry_calendar,
)
from academics.services.ministry_source import (
    MinistrySourceError,
    _NoRedirect,
    fetch_ministry_calendar,
    normalize_documents,
    read_document,
)
from accounts.models import User
from attendance.models import AttendanceDayContext, AttendanceSession
from audit.models import AuditLog
from common.tenant_rls import clear_tenant_context, tenant_context
from students.models import Grade, Section, Student, StudentEnrollment
from tests.attendance_helpers import setup_attendance_env
from tests.test_import_flow import commit_and_refresh, process
from tests.xlsx_helper import build_xlsx_upload, noor_row


@pytest.fixture
def source_documents():
    return json.loads(
        (Path(__file__).parent / "fixtures/ministry_calendar_20261007.json").read_text(
            encoding="utf-8"
        )
    )


@pytest.fixture
def official_snapshot(db, source_documents):
    return MinistryCalendarSnapshot.objects.create(
        fingerprint="a" * 64,
        documents=source_documents,
        calendars=normalize_documents(source_documents),
    )


def _current(documents):
    return next(c for c in normalize_documents(documents) if c["name"] == "2026/2027")


def _policy(school, profile="NATIONAL"):
    return SchoolCalendarPolicy.objects.create(
        school=school, profile=profile, scope_note="مدرسة حكومية مطابقة للتقويم الوطني"
    )


def _student(school, year=None):
    student = Student.objects.create(
        school=school,
        full_name="طالب تجريبي",
        national_id_encrypted="fixture",
        national_id_lookup_hash="b" * 64,
        national_id_masked="******1234",
    )
    if year:
        grade = Grade.objects.create(school=school, code="G1", name="الأول")
        section = Section.objects.create(school=school, grade=grade, code="A", name="أ")
        StudentEnrollment.objects.create(
            school=school,
            student=student,
            academic_year=year,
            grade=grade,
            section=section,
            enrolled_at=year.start_date,
        )
    return student


def test_live_fixture_combines_adjacent_hijri_lists_and_records_calculation(source_documents):
    calendar = _current(source_documents)
    assert calendar["status"] == "READY"
    assert calendar["dates"] == {
        "year_start": "2026-08-23",
        "year_end": "2027-06-24",
        "semester_1_start": "2026-08-23",
        "semester_1_end": "2027-01-07",
        "semester_2_start": "2027-01-17",
        "semester_2_end": "2027-06-24",
    }
    evidence = calendar["evidence"]
    assert evidence["year_start"]["url"].endswith("Year=1448")
    assert evidence["year_end"]["url"].endswith("Year=1449")
    assert evidence["semester_2_start"]["basis"] == "CALCULATED"
    assert evidence["semester_2_start"]["offset_days"] == 9
    assert evidence["semester_2_start"]["source_date"] == "2027-01-08"
    assert date.fromisoformat(calendar["dates"]["semester_2_start"]).weekday() == 6
    assert evidence["semester_1_end"]["basis"] == "CALCULATED"


def test_explicit_ministry_second_opening_overrides_calculation(source_documents):
    source_documents[3]["rows"].append(
        {"id": "900", "title": "بداية الدراسة للفصل الدراسي الثاني", "dategregorian": "24/01/2027"}
    )
    calendar = _current(source_documents)
    assert calendar["status"] == "READY"
    assert calendar["dates"]["semester_2_start"] == "2027-01-24"
    assert calendar["evidence"]["semester_2_start"]["basis"] == "PUBLISHED"


def test_missing_break_is_not_guessed(source_documents):
    for document in source_documents:
        document["rows"] = [r for r in document["rows"] if r.get("id") != "319"]
    calendar = _current(source_documents)
    assert calendar["status"] == "INCOMPLETE"
    assert calendar["dates"]["semester_2_start"] is None


def test_conflicting_annual_end_blocks_entire_calendar(source_documents):
    source_documents[-1]["rows"].append(
        {"id": "900", "title": "نهاية العام الدراسي نهاية دوام", "dategregorian": "23/06/2027"}
    )
    assert "CONFLICT:year_end" in _current(source_documents)["problems"]
    assert _current(source_documents)["status"] == "INVALID"


def test_third_semester_is_not_silently_applied_as_two(source_documents):
    source_documents[3]["rows"].append(
        {"id": "900", "title": "بداية الدراسة للفصل الدراسي الثالث", "dategregorian": "01/04/2027"}
    )
    assert "UNSUPPORTED_SEMESTER_SYSTEM" in _current(source_documents)["problems"]


def test_calculated_return_requires_sunday(source_documents):
    for document in source_documents:
        for row in document["rows"]:
            if row.get("id") == "319":
                row["dategregorian"] = "07/01/2027"
    assert "CALCULATED_RETURN_NOT_SUNDAY" in _current(source_documents)["problems"]


@pytest.mark.parametrize("raw", ["31/02/2027", "2027-01-08", "8/1/2027"])
def test_malformed_source_dates_rejected(source_documents, raw):
    source_documents[-1]["rows"][0]["dategregorian"] = raw
    with pytest.raises(MinistrySourceError, match="MINISTRY_INVALID_EVENT"):
        normalize_documents(source_documents)


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://www.moe.gov.sa/",
        "https://www.moe.gov.sa.evil.test/",
        "https://example.com/",
    ],
)
def test_source_does_not_accept_other_hosts_or_schemes(url):
    with pytest.raises(MinistrySourceError, match="MINISTRY_URL_REJECTED"):
        read_document(url)


def test_source_redirect_rejected():
    with pytest.raises(MinistrySourceError, match="MINISTRY_REDIRECT_REJECTED"):
        _NoRedirect().redirect_request(None, None, 302, "redirect", {}, "https://example.com/")


def test_fetch_deduplicates_unchanged_events_despite_dynamic_html(source_documents):
    with patch("academics.services.ministry_source.read_document", side_effect=source_documents):
        first = fetch_ministry_calendar()[0]
    for document in source_documents:
        document["sha256"] = "changed-page-state"
        document["rows"].reverse()
    with patch("academics.services.ministry_source.read_document", side_effect=source_documents):
        second = fetch_ministry_calendar()[0]
    assert first == second


@pytest.mark.django_db
def test_sync_is_idempotent_and_failure_retains_snapshot(official_snapshot, source_documents):
    fetch = (official_snapshot.fingerprint, source_documents, official_snapshot.calendars)
    with patch("academics.services.ministry_calendar.fetch_ministry_calendar", return_value=fetch):
        assert sync_ministry_calendar()["status"] == "FETCHED"
        assert sync_ministry_calendar()["status"] == "FETCHED"
    assert MinistryCalendarSnapshot.objects.count() == 1
    succeeded_at = MinistryCalendarSync.objects.get().succeeded_at
    with patch(
        "academics.services.ministry_calendar.fetch_ministry_calendar",
        side_effect=MinistrySourceError("MINISTRY_EMPTY_DOCUMENT"),
    ):
        assert sync_ministry_calendar()["status"] == "SOURCE_ERROR"
    state = MinistryCalendarSync.objects.get()
    assert state.snapshot_id == official_snapshot.pk and state.succeeded_at == succeeded_at
    assert state.error_code == "MINISTRY_EMPTY_DOCUMENT"
    assert apply_ministry_calendars()["status"] == "SOURCE_UNAVAILABLE"


@pytest.mark.django_db
@pytest.mark.parametrize("profile", ["UNCONFIRMED", "EXCEPTION"])
def test_unconfirmed_and_exception_schools_are_not_modified(
    make_school, official_snapshot, profile
):
    school = make_school()
    _policy(school, profile)
    assert (
        apply_school_calendar(school=school, snapshot=official_snapshot) == "SCOPE_NOT_APPLICABLE"
    )
    assert not AcademicYear.objects.filter(school=school).exists()


@pytest.mark.django_db
def test_activation_waits_for_enrollment_and_keeps_existing_roster(make_school, official_snapshot):
    school = make_school()
    _policy(school)
    old = AcademicYear.objects.create(
        school=school,
        name="السابق",
        start_date=date(2025, 8, 24),
        end_date=date(2026, 6, 25),
        status="ACTIVE",
    )
    student = _student(school, old)
    assert (
        apply_school_calendar(school=school, snapshot=official_snapshot, today=date(2026, 10, 7))
        == "ENROLLMENTS_NOT_READY"
    )
    old.refresh_from_db()
    assert old.status == "ACTIVE"
    assert student.enrollments.get(academic_year=old).status == "ACTIVE"
    new = AcademicYear.objects.get(school=school, start_date=date(2026, 8, 23))
    original = student.enrollments.get(academic_year=old)
    StudentEnrollment.objects.create(
        school=school,
        student=student,
        academic_year=new,
        grade=original.grade,
        section=original.section,
        enrolled_at=new.start_date,
    )
    assert (
        apply_school_calendar(school=school, snapshot=official_snapshot, today=date(2026, 10, 7))
        == "APPLIED"
    )
    old.refresh_from_db()
    new.refresh_from_db()
    assert old.status == "CLOSED" and new.status == "ACTIVE"
    assert student.enrollments.get(academic_year=old).pk == original.pk
    assert student.enrollments.get(academic_year=old).status == "ACTIVE"


@pytest.mark.django_db
def test_first_term_closes_for_break_and_second_starts_on_exact_day(make_school, official_snapshot):
    school = make_school()
    _policy(school)
    assert (
        apply_school_calendar(school=school, snapshot=official_snapshot, today=date(2027, 1, 7))
        == "APPLIED"
    )
    assert Semester.objects.get(school=school, status="ACTIVE").sequence == 1
    assert (
        apply_school_calendar(school=school, snapshot=official_snapshot, today=date(2027, 1, 8))
        == "BETWEEN_SEMESTERS"
    )
    assert not Semester.objects.filter(school=school, status="ACTIVE").exists()
    assert (
        apply_school_calendar(school=school, snapshot=official_snapshot, today=date(2027, 1, 16))
        == "BETWEEN_SEMESTERS"
    )
    assert (
        apply_school_calendar(school=school, snapshot=official_snapshot, today=date(2027, 1, 17))
        == "APPLIED"
    )
    assert Semester.objects.get(school=school, status="ACTIVE").sequence == 2


@pytest.mark.django_db
def test_existing_historical_dates_are_not_rewritten(make_school, official_snapshot):
    school = make_school()
    _policy(school)
    year = AcademicYear.objects.create(
        school=school,
        name="قائم",
        start_date=date(2026, 8, 23),
        end_date=date(2027, 6, 25),
        status="ACTIVE",
    )
    term = Semester.objects.create(
        school=school,
        academic_year=year,
        name="الفصل القائم",
        sequence=1,
        start_date=date(2026, 8, 24),
        end_date=date(2026, 12, 10),
        status="ACTIVE",
    )
    assert (
        apply_school_calendar(school=school, snapshot=official_snapshot, today=date(2026, 10, 7))
        == "CALENDAR_EXISTING_DATES_CONFLICT"
    )
    year.refresh_from_db()
    assert year.end_date == date(2027, 6, 25) and year.ministry_snapshot_id is None
    term.refresh_from_db()
    assert term.start_date == date(2026, 8, 24) and year.semesters.count() == 1


@pytest.mark.django_db
def test_future_boundaries_are_corrected_without_replacing_year_or_enrollment(
    make_school, official_snapshot
):
    school = make_school()
    _policy(school)
    year = AcademicYear.objects.create(
        school=school,
        name="قائم",
        start_date=date(2026, 8, 23),
        end_date=date(2027, 6, 25),
        status="ACTIVE",
    )
    student = _student(school, year)
    original = student.enrollments.get()
    first = Semester.objects.create(
        school=school,
        academic_year=year,
        name="الأول",
        sequence=1,
        start_date=year.start_date,
        end_date=date(2026, 12, 10),
        status="ACTIVE",
    )
    second = Semester.objects.create(
        school=school,
        academic_year=year,
        name="الثاني",
        sequence=2,
        start_date=date(2027, 1, 10),
        end_date=year.end_date,
    )
    assert (
        apply_school_calendar(school=school, snapshot=official_snapshot, today=date(2026, 10, 7))
        == "APPLIED"
    )
    year.refresh_from_db()
    first.refresh_from_db()
    second.refresh_from_db()
    assert year.end_date == date(2027, 6, 24)
    assert first.end_date == date(2027, 1, 7) and second.start_date == date(2027, 1, 17)
    assert student.enrollments.get().pk == original.pk
    assert AcademicYear.objects.filter(school=school).count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize("role", ["SCHOOL_MANAGER", "VICE_PRINCIPAL", "COUNSELOR"])
def test_school_roles_read_source_but_cannot_set_platform_scope(
    role_client, official_snapshot, role
):
    client, school, _ = role_client([role])
    _policy(school)
    MinistryCalendarSync.objects.create(snapshot=official_snapshot, succeeded_at=timezone.now())
    assert client.get("/api/v1/school/ministry-calendar/").json()["profile"] == "NATIONAL"
    assert (
        client.patch(
            f"/api/v1/platform/schools/{school.pk}/calendar-scope/",
            {"profile": "EXCEPTION", "scope_note": "تغيير غير مصرح به"},
            content_type="application/json",
        ).status_code
        == 403
    )


@pytest.mark.django_db
def test_manager_cannot_change_managed_dates_or_force_activation(role_client, official_snapshot):
    client, school, _ = role_client(["SCHOOL_MANAGER"])
    _policy(school)
    apply_school_calendar(school=school, snapshot=official_snapshot)
    year = AcademicYear.objects.get(school=school)
    for url, body, method in [
        (
            "/api/v1/school/academic-years/",
            {"name": "x", "start_date": "2028-08-20", "end_date": "2029-06-20"},
            "post",
        ),
        (f"/api/v1/school/academic-years/{year.pk}/", {"end_date": "2027-06-25"}, "patch"),
        (f"/api/v1/school/academic-years/{year.pk}/close/", {}, "post"),
        (f"/api/v1/school/academic-years/{year.pk}/semesters/", {}, "post"),
        (f"/api/v1/school/semesters/{year.semesters.first().pk}/activate/", {}, "post"),
    ]:
        response = getattr(client, method)(url, body, content_type="application/json")
        assert (
            response.status_code == 409 and response.json()["code"] == "MINISTRY_CALENDAR_MANAGED"
        )


@pytest.mark.django_db
def test_platform_owner_can_set_scope_but_must_document_match(make_school, official_snapshot):
    owner = User.objects.create_superuser(mobile="0550088123", password="OwnerPass!42")
    client = Client()
    client.force_login(owner)
    school = make_school()
    url = f"/api/v1/platform/schools/{school.pk}/calendar-scope/"
    assert (
        client.patch(
            url, {"profile": "NATIONAL", "scope_note": ""}, content_type="application/json"
        ).status_code
        == 400
    )
    assert (
        client.patch(
            url,
            {"profile": "NATIONAL", "scope_note": "مدرسة حكومية مطابقة للتقويم"},
            content_type="application/json",
        ).status_code
        == 200
    )


@pytest.mark.django_db
def test_prepare_upcoming_year_from_noor_preserves_prior_enrollment(role_client, official_snapshot):
    client, school, _ = role_client(["SCHOOL_MANAGER"])
    old = AcademicYear.objects.create(
        school=school,
        name="الحالي",
        start_date=date(2025, 8, 24),
        end_date=date(2026, 6, 25),
        status="ACTIVE",
    )
    rows = [noor_row("1012345601", "طالب إعداد القيد")]
    first = client.post("/api/v1/student-imports/", {"file": build_xlsx_upload(rows)}).json()
    process(client, first["id"])
    commit_and_refresh(client, first["id"])
    original = StudentEnrollment.objects.get(academic_year=old)
    _policy(school)
    assert (
        apply_school_calendar(school=school, snapshot=official_snapshot) == "ENROLLMENTS_NOT_READY"
    )
    new = AcademicYear.objects.get(school=school, status="UPCOMING")
    uploaded = client.post(
        "/api/v1/student-imports/", {"file": build_xlsx_upload(rows), "academic_year_id": new.pk}
    )
    assert uploaded.status_code == 201
    job_id = uploaded.json()["id"]
    assert uploaded.json()["academic_year"]["id"] == new.pk
    assert process(client, job_id).status_code == 202
    assert commit_and_refresh(client, job_id).json()["status"] == "COMPLETED"
    assert StudentEnrollment.objects.get(pk=original.pk).status == "ACTIVE"
    assert StudentEnrollment.objects.filter(academic_year=new).count() == 1
    assert apply_school_calendar(school=school, snapshot=official_snapshot) == "APPLIED"


@pytest.mark.django_db
def test_import_cannot_target_unmanaged_future_year_or_other_school(role_client, make_school):
    client, school, _ = role_client(["SCHOOL_MANAGER"])
    year = AcademicYear.objects.create(
        school=school, name="قادم", start_date=date(2028, 8, 20), end_date=date(2029, 6, 20)
    )
    url = "/api/v1/student-imports/"
    assert client.post(url, {"academic_year_id": year.pk}).status_code == 409
    other = make_school()
    year.school = other
    year.save()
    assert client.post(url, {"academic_year_id": year.pk}).status_code == 404


@pytest.mark.django_db
def test_old_success_cannot_activate_new_year(make_school, official_snapshot):
    school = make_school()
    _policy(school)
    MinistryCalendarSync.objects.create(
        snapshot=official_snapshot, succeeded_at=timezone.now() - timedelta(days=3)
    )
    assert apply_ministry_calendars()["status"] == "SOURCE_UNAVAILABLE"
    assert not AcademicYear.objects.filter(school=school).exists()


@pytest.mark.django_db
def test_activation_updates_only_pristine_today_context(make_school, official_snapshot):
    school = make_school()
    _policy(school)
    old = AcademicYear.objects.create(
        school=school,
        name="السابق",
        start_date=date(2025, 8, 24),
        end_date=date(2026, 6, 25),
        status="ACTIVE",
    )
    contexts = [
        AttendanceDayContext.objects.create(
            school=school,
            academic_year=old,
            attendance_date=day,
            schedule_snapshot={"schedule_name": "سابق", "is_school_day": True, "periods": []},
            timezone_snapshot="Asia/Riyadh",
        )
        for day in (date(2026, 10, 6), date(2026, 10, 7))
    ]
    assert (
        apply_school_calendar(
            school=school,
            snapshot=official_snapshot,
            today=date(2026, 10, 7),
        )
        == "APPLIED"
    )
    for context in contexts:
        context.refresh_from_db()
    assert contexts[0].academic_year_id == old.pk
    assert contexts[0].schedule_snapshot["schedule_name"] == "سابق"
    assert contexts[1].academic_year_id != old.pk
    assert contexts[1].schedule_snapshot["schedule_name"] is None


@pytest.mark.django_db
def test_started_attendance_defers_year_switch_to_next_day(
    role_client,
    official_snapshot,
):
    _, school, user = role_client(["SCHOOL_MANAGER"])
    _policy(school)
    old = AcademicYear.objects.create(
        school=school,
        name="السابق",
        start_date=date(2025, 8, 24),
        end_date=date(2026, 6, 25),
        status="ACTIVE",
    )
    student = _student(school, old)
    original = student.enrollments.get()
    session = AttendanceSession.objects.create(
        school=school,
        academic_year=old,
        section=original.section,
        attendance_date=date(2026, 10, 7),
        period_sequence=1,
        bell_period_snapshot={"sequence": 1},
        roster_fingerprint="a" * 64,
        unprepared_alert_minutes_snapshot=10,
        started_by_membership=user.memberships.get(),
    )
    assert (
        apply_school_calendar(
            school=school,
            snapshot=official_snapshot,
            today=date(2026, 10, 7),
        )
        == "DAY_ALREADY_IN_USE"
    )
    new = AcademicYear.objects.get(school=school, status="UPCOMING")
    StudentEnrollment.objects.create(
        school=school,
        student=student,
        academic_year=new,
        grade=original.grade,
        section=original.section,
        enrolled_at=new.start_date,
    )
    assert (
        apply_school_calendar(
            school=school,
            snapshot=official_snapshot,
            today=date(2026, 10, 7),
        )
        == "DAY_ALREADY_IN_USE"
    )
    old.refresh_from_db()
    session.refresh_from_db()
    assert old.status == "ACTIVE" and session.academic_year_id == old.pk
    assert (
        apply_school_calendar(
            school=school,
            snapshot=official_snapshot,
            today=date(2026, 10, 8),
        )
        == "APPLIED"
    )
    assert (
        AttendanceDayContext.objects.get(
            school=school,
            attendance_date=date(2026, 10, 8),
        ).academic_year_id
        == new.pk
    )


@pytest.mark.django_db
def test_teacher_and_leaders_share_one_session_under_managed_calendar(
    role_client,
    official_snapshot,
    monkeypatch,
):
    monkeypatch.setattr(
        timezone,
        "now",
        lambda: datetime(2026, 10, 7, 9, 5, tzinfo=ZoneInfo("Asia/Riyadh")),
    )
    teacher, school, _ = role_client(["TEACHER"])
    env = setup_attendance_env(school)
    _policy(school)
    assert apply_school_calendar(school=school, snapshot=official_snapshot) == "APPLIED"
    payload = {"section_id": env["section"].pk}
    url = "/api/v1/attendance/sessions/start/"
    first = teacher.post(url, payload, content_type="application/json")
    assert first.status_code == 201
    assert len(first.json()["roster"]) == 5
    for role in ("SCHOOL_MANAGER", "VICE_PRINCIPAL"):
        leader, _, _ = role_client([role], school=school)
        resumed = leader.post(
            "/api/v1/attendance/admin/sessions/start/",
            {**payload, "date": "2026-10-07", "period_sequence": env["period"].sequence},
            content_type="application/json",
        )
        assert resumed.status_code == 200 and resumed.json()["id"] == first.json()["id"]
    session = AttendanceSession.objects.get(school=school)
    assert session.semester.sequence == 1 and session.academic_year_id == env["year"].pk


@pytest.mark.django_db(transaction=True)
def test_calendar_policy_rls_isolates_reads_and_rejects_cross_school_writes(make_school):
    first, second, third = make_school(), make_school(), make_school()
    policies = [_policy(first), _policy(second)]
    role = connection.ops.quote_name(f"calendar_rls_{uuid4().hex}")
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"CREATE ROLE {role} NOSUPERUSER NOBYPASSRLS")
            cursor.execute(f"GRANT USAGE ON SCHEMA public TO {role}")
            cursor.execute(f"GRANT SELECT, INSERT ON academics_schoolcalendarpolicy TO {role}")
            cursor.execute(
                f"GRANT USAGE ON SEQUENCE academics_schoolcalendarpolicy_id_seq TO {role}"
            )
            cursor.execute(f"SET ROLE {role}")
        clear_tenant_context()
        assert SchoolCalendarPolicy.objects.count() == 0
        with tenant_context(school_id=first.pk):
            assert list(SchoolCalendarPolicy.objects.values_list("id", flat=True)) == [
                policies[0].pk
            ]
            with pytest.raises(DatabaseError, match="row-level security policy"):
                with transaction.atomic():
                    _policy(third)
        with tenant_context(school_id=second.pk):
            assert list(SchoolCalendarPolicy.objects.values_list("id", flat=True)) == [
                policies[1].pk
            ]
        with tenant_context(bypass=True):
            assert SchoolCalendarPolicy.objects.count() == 2
    finally:
        with connection.cursor() as cursor:
            cursor.execute("RESET ROLE")
            cursor.execute(f"DROP OWNED BY {role}")
            cursor.execute(f"DROP ROLE IF EXISTS {role}")
        clear_tenant_context()


@pytest.mark.django_db(transaction=True)
def test_concurrent_activations_do_not_duplicate_year_semesters_or_audit(
    make_school, official_snapshot
):
    school = make_school()
    _policy(school)

    def activate():
        close_old_connections()
        try:
            return apply_school_calendar(
                school=school, snapshot=official_snapshot, today=date(2027, 1, 17)
            )
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: activate(), range(2)))
    assert results == ["APPLIED", "APPLIED"]
    assert AcademicYear.objects.filter(school=school, status="ACTIVE").count() == 1
    assert Semester.objects.filter(school=school).count() == 2
    assert AuditLog.objects.filter(school=school, action="ACADEMIC_YEAR_ACTIVATED").count() == 1
    assert AuditLog.objects.filter(school=school, action="SEMESTER_ACTIVATED").count() == 1
