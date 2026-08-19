"""قياس استحقاق الإنذارات (تطوير فقط): 500/1000/3000/5000 طالب — لا N+1."""

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

SECTION_SIZE = 30
RUNS = 5


class Command(BaseCommand):
    help = "قياس زمن واستعلامات لوحة استحقاق الإنذارات (DEBUG فقط)"

    def add_arguments(self, parser):
        parser.add_argument("--sizes", nargs="+", type=int, default=[500, 1000, 3000, 5000])

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("benchmark_warnings يعمل في التطوير فقط.")

        from academics.models import AcademicYear, AcademicYearStatus
        from attendance.models import DailyAbsenceStatus, DailyAttendanceSummary
        from devices.models import ArrivalSource, ArrivalStatus, SchoolArrival
        from student_warnings.models import WarningRuleType
        from student_warnings.selectors.eligibility import (
            eligibility_dashboard,
            evaluate_student_warning_eligibility,
            metric_for_students,
        )
        from students.models import Grade, Section
        from tests.attendance_helpers import make_students

        school = School.objects.create(name="مدرسة قياس الإنذارات", slug="warn-benchmark")
        user = User.objects.create_user(
            mobile="0551113333", password="Bench-123456"  # noqa: S106 — بيانات قياس مؤقتة
        )
        SchoolMembership.objects.create(user=user, school=school)
        day = date(2026, 8, 16)

        try:
            year = AcademicYear.objects.create(
                school=school, name="قياس", start_date=date(2026, 8, 1),
                end_date=date(2027, 6, 25), status=AcademicYearStatus.ACTIVE,
            )
            grade = Grade.objects.create(school=school, name="قياس", code="B", sequence=1)

            students = []
            index = 0
            max_students = max(options["sizes"])
            while len(students) < max_students:
                count = min(SECTION_SIZE, max_students - len(students))
                section = Section.objects.create(
                    school=school, grade=grade, code=f"w{index}", name=f"w{index}"
                )
                batch = make_students(school, section, year, count, prefix=f"99{index:03d}")
                # ‏20% منهم بلغوا حد الإنذار: 5 أيام غياب كامل بدون عذر + 3 تأخرات
                for position, student in enumerate(batch):
                    if position % 5:
                        continue
                    DailyAttendanceSummary.objects.bulk_create(
                        DailyAttendanceSummary(
                            school=school, student=student, academic_year=year,
                            section=section, attendance_date=day + timedelta(days=offset),
                            expected_periods=7, submitted_periods=7, absent_periods=7,
                            late_periods=0, present_periods=0, total_late_minutes=0,
                            excused_absent_periods=0, unexcused_absent_periods=7,
                            completeness_status="COMPLETE",
                            absence_status=DailyAbsenceStatus.FULL,
                            calculated_at=datetime.now(UTC),
                        )
                        for offset in range(5)
                    )
                    SchoolArrival.objects.bulk_create(
                        SchoolArrival(
                            school=school, student=student,
                            attendance_date=day + timedelta(days=10 + offset),
                            first_arrival_at=datetime.now(UTC),
                            raw_late_minutes=18, counted_late_minutes=13,
                            status=ArrivalStatus.LATE, source=ArrivalSource.BIOMETRIC,
                        )
                        for offset in range(3)
                    )
                students.extend(batch)
                index += 1

            for size in options["sizes"]:
                subset_ids = [s.id for s in students[:size]]

                def timed(label, fn, count=size):
                    durations = []
                    for _ in range(RUNS):
                        with CaptureQueriesContext(connection) as ctx:
                            t0 = time_module.perf_counter()
                            fn()
                            durations.append((time_module.perf_counter() - t0) * 1000)
                        queries = len(ctx.captured_queries)
                    self.stdout.write(
                        f"students={count:5d} | {label:<22} | "
                        f"p50={statistics.median(durations):7.1f}ms | "
                        f"max={max(durations):7.1f}ms | queries={queries}"
                    )

                timed("absence metric", lambda ids=subset_ids: metric_for_students(
                    school=school, year=year,
                    rule_type=WarningRuleType.UNEXCUSED_FULL_DAY_ABSENCE,
                    student_ids=ids,
                ))
                timed("morning metric", lambda ids=subset_ids: metric_for_students(
                    school=school, year=year,
                    rule_type=WarningRuleType.MORNING_LATE_OCCURRENCES,
                    student_ids=ids,
                ))
                timed("dashboard (combined)", lambda: eligibility_dashboard(
                    school=school, status_filter="due", page_size=100
                ))
                timed("single student", lambda s=students[0]:
                      evaluate_student_warning_eligibility(school=school, student=s))
        finally:
            _cleanup(school, user)
            self.stdout.write(self.style.SUCCESS("benchmark data cleaned."))


def _cleanup(school: School, user: User) -> None:
    from academics.models import AcademicYear
    from attendance.models import DailyAttendanceSummary
    from audit.models import AuditLog
    from devices.models import SchoolArrival
    from student_warnings.models import StudentWarning, WarningRule
    from students.models import Grade, Section, Student, StudentEnrollment

    StudentWarning.objects.filter(school=school).delete()
    WarningRule.objects.filter(school=school).delete()
    SchoolArrival.objects.filter(school=school).delete()
    DailyAttendanceSummary.objects.filter(school=school).delete()
    StudentEnrollment.objects.filter(school=school).delete()
    Student.objects.filter(school=school).delete()
    Section.objects.filter(school=school).delete()
    Grade.objects.filter(school=school).delete()
    AuditLog.objects.filter(school=school).delete()
    AcademicYear.objects.filter(school=school).delete()
    SchoolMembership.objects.filter(school=school).delete()
    school.delete()
    if not user.memberships.exists():
        user.delete()
