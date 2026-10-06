from datetime import date, datetime, timedelta
from io import BytesIO
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone
from openpyxl import load_workbook

from academics.models import AcademicYear, AcademicYearStatus
from attendance.models import (
    DailyAbsenceStatus,
    DailyAttendanceSummary,
    DailyCompleteness,
)
from devices.models import ArrivalSource, ArrivalStatus, SchoolArrival
from memberships.models import SchoolMembership
from referrals.models import (
    ReferralCategory,
    ReferralPriority,
    ReferralReason,
    ReferralStatus,
    StudentReferral,
)
from students.models import Grade, Section, Student

TODAY = date.today()
TZ = ZoneInfo("Asia/Riyadh")


@pytest.fixture
def report_env(make_school, role_client):
    school = make_school("مدرسة التقارير")
    manager_client, _, _ = role_client(["SCHOOL_MANAGER"], school=school)
    vice_client, _, _ = role_client(["VICE_PRINCIPAL"], school=school)
    year = AcademicYear.objects.create(
        school=school,
        name="2026/2027",
        start_date=TODAY,
        end_date=TODAY + timedelta(days=1),
        status=AcademicYearStatus.ACTIVE,
    )
    grade = Grade.objects.create(school=school, name="الأول", code="G1", sequence=1)
    section = Section.objects.create(school=school, grade=grade, name="أ", code="A")
    student = Student.objects.create(
        school=school,
        national_id_encrypted="encrypted",
        national_id_lookup_hash="a" * 64,
        national_id_masked="******1111",
        full_name="طالب التقرير",
        guardian_mobile="0550000001",
    )
    partial_student = Student.objects.create(
        school=school,
        national_id_encrypted="encrypted-partial",
        national_id_lookup_hash="b" * 64,
        national_id_masked="******2222",
        full_name="طالب غياب حصة",
    )
    DailyAttendanceSummary.objects.create(
        school=school,
        student=student,
        academic_year=year,
        section=section,
        attendance_date=TODAY,
        expected_periods=7,
        submitted_periods=7,
        absent_periods=7,
        present_periods=0,
        excused_absent_periods=2,
        unexcused_absent_periods=5,
        completeness_status=DailyCompleteness.COMPLETE,
        absence_status=DailyAbsenceStatus.FULL,
        calculated_at=timezone.now(),
    )
    SchoolArrival.objects.create(
        school=school,
        student=student,
        attendance_date=TODAY,
        first_arrival_at=datetime(TODAY.year, TODAY.month, TODAY.day, 7, 15, tzinfo=TZ),
        raw_late_minutes=15,
        counted_late_minutes=10,
        status=ArrivalStatus.LATE,
        source=ArrivalSource.MANUAL,
    )
    DailyAttendanceSummary.objects.create(
        school=school,
        student=partial_student,
        academic_year=year,
        section=section,
        attendance_date=TODAY,
        expected_periods=7,
        submitted_periods=2,
        absent_periods=1,
        present_periods=1,
        excused_absent_periods=0,
        unexcused_absent_periods=1,
        completeness_status=DailyCompleteness.INCOMPLETE,
        absence_status=DailyAbsenceStatus.PARTIAL,
        calculated_at=timezone.now(),
    )
    return {
        "school": school,
        "manager": manager_client,
        "vice": vice_client,
        "student": student,
        "partial_student": partial_student,
        "grade": grade,
        "section": section,
    }


@pytest.mark.django_db
def test_manager_and_vice_principal_receive_filtered_absence_report(report_env):
    url = (
        f"/api/v1/reports/absence/?preset=TODAY&grade={report_env['grade'].id}"
        "&absence_type=FULL&excuse_type=MIXED"
    )
    for client in (report_env["manager"], report_env["vice"]):
        response = client.get(url)
        assert response.status_code == 200
        assert response.json()["summary"]["students"] == 1
        assert response.json()["results"][0]["full_name"] == "طالب التقرير"
        assert response.json()["results"][0]["guardian_mobile"] == "0550000001"
        assert response.json()["results"][0]["unexcused_absent_periods"] == 5


@pytest.mark.django_db
def test_absence_report_accepts_partial_absence_without_planned_period_condition(report_env):
    response = report_env["manager"].get(
        "/api/v1/reports/absence/?preset=TODAY&absence_type=PARTIAL"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["students"] == 1
    assert payload["summary"]["partial_absence_days"] == 1
    assert payload["summary"]["unexcused_absent_periods"] == 1
    assert payload["summary"]["incomplete_days"] == 0
    assert payload["results"][0]["student_id"] == report_env["partial_student"].id


@pytest.mark.django_db
def test_absence_report_exports_real_xlsx(report_env):
    response = report_env["manager"].get("/api/v1/reports/absence/export.xlsx?preset=TODAY")
    assert response.status_code == 200
    assert response["Content-Type"] == (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    workbook = load_workbook(BytesIO(response.content), read_only=True)
    sheet = workbook["الغياب"]
    assert sheet["A1"].value == "تقرير الغياب"
    assert sheet["A7"].value == "الطالب"
    assert sheet["B7"].value == "جوال ولي الأمر"
    assert sheet["I7"].value == "حصص دون عذر"
    assert sheet["A8"].value == "طالب التقرير"
    assert sheet["B8"].value == "0550000001"
    assert sheet["I8"].value == 5


@pytest.mark.django_db
def test_lateness_report_uses_morning_arrivals_only(report_env):
    response = report_env["vice"].get(
        "/api/v1/reports/lateness/?preset=TODAY&min_occurrences=1"
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"] == {
        "students": 1,
        "morning_occurrences": 1,
        "morning_minutes": 10,
    }
    assert payload["results"][0]["morning_occurrences"] == 1


@pytest.mark.django_db
def test_corrected_arrival_disappears_from_lateness_report_for_same_period(report_env):
    vice = report_env["vice"]
    student = report_env["student"]
    arrival = SchoolArrival.objects.get(school=report_env["school"], student=student)
    report_url = f"/api/v1/reports/lateness/?from_date={TODAY}&to_date={TODAY}"
    profile_url = (
        f"/api/v1/students/{student.id}/attendance-profile/"
        f"?from_date={TODAY}&to_date={TODAY}"
    )

    assert vice.get(report_url).json()["summary"]["morning_occurrences"] == 1
    corrected = vice.post(
        f"/api/v1/morning/arrivals/{arrival.id}/correct/",
        {"arrival_time": "07:05", "reason": "تصحيح وقت الوصول"},
        content_type="application/json",
    )
    assert corrected.status_code == 200
    assert corrected.json()["status"] == ArrivalStatus.ON_TIME

    report = vice.get(report_url)
    profile = vice.get(profile_url)
    assert report.status_code == 200
    assert report.json()["summary"] == {
        "students": 0,
        "morning_occurrences": 0,
        "morning_minutes": 0,
    }
    assert report.json()["results"] == []
    assert profile.status_code == 200
    assert profile.json()["morning_attendance"]["morning_late_occurrences"] == 0


@pytest.mark.django_db
def test_lateness_report_exports_real_xlsx(report_env):
    response = report_env["vice"].get("/api/v1/reports/lateness/export.xlsx?preset=TODAY")
    assert response.status_code == 200
    workbook = load_workbook(BytesIO(response.content), read_only=True)
    sheet = workbook["التأخر"]
    assert sheet["A1"].value == "تقرير التأخر الصباحي"
    assert sheet["D7"].value == "مرات التأخر الصباحي"
    assert sheet["A8"].value == "طالب التقرير"
    assert sheet["D8"].value == 1
    assert sheet["E8"].value == 10


@pytest.mark.django_db
def test_referral_report_filters_priority_and_student(report_env):
    membership = SchoolMembership.objects.get(
        school=report_env["school"], roles__role="SCHOOL_MANAGER"
    )
    referral = StudentReferral.objects.create(
        school=report_env["school"],
        student=report_env["student"],
        source_type="SCHOOL_MANAGER",
        category=ReferralCategory.ATTENDANCE,
        reason_code=ReferralReason.REPEATED_ABSENCE,
        description="غياب متكرر",
        created_by_membership=membership,
        priority=ReferralPriority.HIGH,
    )
    response = report_env["manager"].get(
        f"/api/v1/reports/referrals/?preset=TODAY&priority=HIGH&student={report_env['student'].id}"
    )
    assert response.status_code == 200
    assert response.json()["summary"]["high_priority"] == 1
    assert response.json()["results"][0]["id"] == referral.id


@pytest.mark.django_db
def test_referrals_report_exports_real_xlsx(report_env):
    membership = SchoolMembership.objects.get(
        school=report_env["school"], roles__role="SCHOOL_MANAGER"
    )
    StudentReferral.objects.create(
        school=report_env["school"],
        student=report_env["student"],
        source_type="SCHOOL_MANAGER",
        category=ReferralCategory.ATTENDANCE,
        reason_code=ReferralReason.REPEATED_ABSENCE,
        description="غياب متكرر",
        created_by_membership=membership,
        priority=ReferralPriority.HIGH,
    )
    response = report_env["manager"].get("/api/v1/reports/referrals/export.xlsx?preset=TODAY")
    assert response.status_code == 200
    workbook = load_workbook(BytesIO(response.content), read_only=True)
    sheet = workbook["الإحالات"]
    assert sheet["A1"].value == "تقرير مسار الإحالات"
    assert sheet["D7"].value == "الفئة"
    assert sheet["A8"].value == "طالب التقرير"
    assert sheet["D8"].value == "المواظبة"
    assert sheet["I8"].value == "عاجلة"


@pytest.mark.django_db
def test_teacher_cannot_access_school_reports(role_client):
    client, _, _ = role_client(["TEACHER"])
    for path in ("absence", "lateness", "referrals"):
        assert client.get(f"/api/v1/reports/{path}/?preset=TODAY").status_code == 403
        assert client.get(f"/api/v1/reports/{path}/export.xlsx?preset=TODAY").status_code == 403


@pytest.fixture(params=[["COUNSELOR"], ["COUNSELOR", "TEACHER"]])
def counselor_report_env(request, report_env, role_client):
    school = report_env["school"]
    client, _, user = role_client(request.param, school=school)
    membership = SchoolMembership.objects.get(school=school, user=user)
    _, _, colleague = role_client(["COUNSELOR"], school=school)
    colleague_membership = SchoolMembership.objects.get(school=school, user=colleague)
    manager = SchoolMembership.objects.get(school=school, roles__role="SCHOOL_MANAGER")

    def referral(student, counselor, *, status=ReferralStatus.REFERRED, **kwargs):
        return StudentReferral.objects.create(
            school=school,
            student=student,
            source_type="SCHOOL_MANAGER",
            category=ReferralCategory.ATTENDANCE,
            reason_code=ReferralReason.REPEATED_ABSENCE,
            description="متابعة الإحالة",
            created_by_membership=kwargs.pop("created_by_membership", manager),
            assigned_counselor_membership=counselor,
            status=status,
            **kwargs,
        )

    own = referral(report_env["student"], membership, priority=ReferralPriority.HIGH)
    own_closed = referral(
        report_env["partial_student"], membership,
        status=ReferralStatus.CLOSED, closed_at=timezone.now(),
    )
    # Even a counselor who created a colleague's referral as a teacher must not export it.
    referral(report_env["student"], colleague_membership, created_by_membership=membership)
    referral(report_env["student"], None, status=ReferralStatus.PENDING_VICE)

    _, other_school, other_user = role_client(["COUNSELOR"])
    other_membership = SchoolMembership.objects.get(school=other_school, user=other_user)
    other_student = Student.objects.create(
        school=other_school, full_name="طالب مدرسة أخرى",
        national_id_encrypted="other-school", national_id_lookup_hash="c" * 64,
        national_id_masked="******3333",
    )
    StudentReferral.objects.create(
        school=other_school, student=other_student, source_type="SCHOOL_MANAGER",
        category=ReferralCategory.ATTENDANCE, reason_code=ReferralReason.REPEATED_ABSENCE,
        description="مدرسة أخرى", created_by_membership=other_membership,
        assigned_counselor_membership=other_membership, status=ReferralStatus.REFERRED,
    )
    return {
        **report_env, "client": client, "membership": membership,
        "colleague": colleague_membership, "own": own, "own_closed": own_closed,
        "other_school": other_school,
    }


@pytest.mark.django_db
def test_counselor_report_and_summary_include_only_assigned_referrals(counselor_report_env):
    env = counselor_report_env
    response = env["client"].get("/api/v1/reports/referrals/?preset=TODAY")
    assert response.status_code == 200
    payload = response.json()
    assert {row["id"] for row in payload["results"]} == {env["own"].id, env["own_closed"].id}
    assert payload["count"] == 2
    assert payload["summary"] == {
        "total": 2, "new": 0, "under_vice_review": 0, "referred": 1,
        "acknowledged": 0, "closed": 1, "unassigned": 0, "high_priority": 1,
    }
    assert payload["context"]["scope"]["counselor_membership_id"] == env["membership"].id
    assert env["manager"].get("/api/v1/reports/referrals/?preset=TODAY").json()["count"] == 4


@pytest.mark.django_db
def test_counselor_report_filters_cannot_expand_assignment_or_school(counselor_report_env):
    env = counselor_report_env
    base_url = "/api/v1/reports/referrals/?preset=TODAY"
    for filters in (f"&counselor={env['colleague'].id}", "&counselor=UNASSIGNED"):
        response = env["client"].get(base_url + filters)
        assert response.status_code == 200
        assert response.json()["count"] == 0
        assert response.json()["summary"]["total"] == 0
        export = env["client"].get(base_url.replace("/?", "/export.xlsx?") + filters)
        assert export.status_code == 200
        assert load_workbook(BytesIO(export.content))["الإحالات"].max_row == 7
    filtered = env["client"].get(base_url + "&priority=HIGH&status=OPEN")
    assert [row["id"] for row in filtered.json()["results"]] == [env["own"].id]
    other_school = env["client"].get(base_url + f"&school_id={env['other_school'].id}")
    assert other_school.json()["count"] == 2


@pytest.mark.django_db
def test_counselor_excel_exports_all_own_referrals_and_scope(counselor_report_env):
    env = counselor_report_env
    response = env["client"].get("/api/v1/reports/referrals/export.xlsx?preset=TODAY&page_size=1")
    assert response.status_code == 200
    sheet = load_workbook(BytesIO(response.content))["الإحالات"]
    assert sheet["B4"].value == "الإحالات الخاصة بالمرشد"
    assert sheet["A5"].value == "عدد النتائج المطابقة: 2"
    assert sheet.max_row == 9
    assert {sheet["A8"].value, sheet["A9"].value} == {"طالب التقرير", "طالب غياب حصة"}


@pytest.mark.django_db
def test_counselor_cannot_access_executive_reports_or_dashboard(role_client):
    client, _, _ = role_client(["COUNSELOR"])
    for path in ("absence", "lateness"):
        assert client.get(f"/api/v1/reports/{path}/?preset=TODAY").status_code == 403
        assert client.get(f"/api/v1/reports/{path}/export.xlsx?preset=TODAY").status_code == 403
    assert client.get("/api/v1/dashboard/overview/?preset=TODAY").status_code == 403
