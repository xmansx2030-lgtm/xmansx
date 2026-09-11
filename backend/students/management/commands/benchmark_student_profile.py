"""قياس ملف حضور الطالب (تطوير فقط): فترات 30/90/180/365 يومًا."""

import statistics
import time as time_module
from datetime import UTC, date, datetime, timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.test.utils import CaptureQueriesContext

from accounts.models import User
from memberships.models import SchoolMembership
from schools.models import School

RUNS = 5


class Command(BaseCommand):
    help = "قياس ملخص/سجل ملف حضور الطالب (DEBUG فقط)"

    def add_arguments(self, parser):
        parser.add_argument("--windows", nargs="+", type=int, default=[30, 90, 180, 365])

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("benchmark_student_profile يعمل في التطوير فقط.")

        from academics.models import AcademicYear, AcademicYearStatus
        from attendance.models import DailyAttendanceSummary
        from devices.models import SchoolArrival
        from students.models import Grade, Section
        from students.services.attendance_profile import (
            get_daily_history,
            get_profile_summary,
        )
        from tests.attendance_helpers import make_students

        school = School.objects.create(name="مدرسة قياس الملف", slug="prof-benchmark")
        user = User.objects.create_user(
            mobile="0551114444", password="Bench-123456"  # noqa: S106 — بيانات قياس مؤقتة
        )
        SchoolMembership.objects.create(user=user, school=school)

        try:
            year = AcademicYear.objects.create(
                school=school, name="قياس", start_date=date(2025, 9, 1),
                end_date=date(2026, 8, 30), status=AcademicYearStatus.ACTIVE,
            )
            grade = Grade.objects.create(school=school, name="قياس", code="B", sequence=1)
            section = Section.objects.create(school=school, grade=grade, code="p", name="p")
            student = make_students(school, section, year, 1, prefix="89000")[0]

            end = date(2026, 8, 18)
            max_days = max(options["windows"])
            DailyAttendanceSummary.objects.bulk_create(
                DailyAttendanceSummary(
                    school=school, student=student, academic_year=year, section=section,
                    attendance_date=end - timedelta(days=i),
                    expected_periods=7, submitted_periods=7,
                    absent_periods=i % 3,
                    present_periods=7 - (i % 3),
                    completeness_status="COMPLETE",
                    absence_status="PARTIAL" if i % 3 else "NONE",
                    calculated_at=datetime.now(UTC),
                )
                for i in range(max_days)
            )
            SchoolArrival.objects.bulk_create(
                SchoolArrival(
                    school=school, student=student,
                    attendance_date=end - timedelta(days=i),
                    first_arrival_at=datetime.now(UTC) - timedelta(days=i),
                    raw_late_minutes=12, counted_late_minutes=7,
                    status="LATE", source="BIOMETRIC",
                )
                for i in range(max_days)
            )

            for window in options["windows"]:
                start = end - timedelta(days=window - 1)

                def timed(label, fn, size=window):
                    durations = []
                    for _ in range(RUNS):
                        with CaptureQueriesContext(connection) as ctx:
                            t0 = time_module.perf_counter()
                            fn()
                            durations.append((time_module.perf_counter() - t0) * 1000)
                        queries = len(ctx.captured_queries)
                    self.stdout.write(
                        f"days={size:4d} | {label:<16} | "
                        f"p50={statistics.median(durations):7.1f}ms | queries={queries}"
                    )

                timed("summary", lambda s=start: get_profile_summary(
                    school=school, student=student, from_date=s, to_date=end
                ))
                timed("daily history", lambda s=start: list(
                    get_daily_history(
                        school=school, student=student, from_date=s, to_date=end
                    )[:25]
                ))
        finally:
            from students.models import Student, StudentEnrollment

            SchoolArrival.objects.filter(school=school).delete()
            DailyAttendanceSummary.objects.filter(school=school).delete()
            StudentEnrollment.objects.filter(school=school).delete()
            Student.objects.filter(school=school).delete()
            Section.objects.filter(school=school).delete()
            Grade.objects.filter(school=school).delete()
            AcademicYear.objects.filter(school=school).delete()
            SchoolMembership.objects.filter(school=school).delete()
            school.delete()
            user.delete()
            self.stdout.write(self.style.SUCCESS("benchmark data cleaned."))
