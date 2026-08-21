"""قياس لوحة المتابعة (تطوير فقط): المدة وعدد الاستعلامات لأحجام 10-100 فصل."""

import statistics
import time as time_module
from datetime import datetime, time
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.test.utils import CaptureQueriesContext

from accounts.models import User
from memberships.models import SchoolMembership, SchoolMembershipRole, SchoolRole
from schools.models import School

RUNS = 7  # تشغيلات لكل حجم — تكفي لـ p50 وأعلى قيمة


class Command(BaseCommand):
    help = "قياس زمن واستعلامات لوحة متابعة التحضير (DEBUG فقط)"

    def add_arguments(self, parser):
        parser.add_argument("--sizes", nargs="+", type=int, default=[10, 20, 40, 80, 100])

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("benchmark_attendance_monitoring يعمل في التطوير فقط.")

        from academics.models import (
            AcademicYear,
            AcademicYearStatus,
            BellPeriod,
            BellSchedule,
            SchoolWeekDay,
            Weekday,
        )
        from attendance.models import AttendanceSession
        from attendance.selectors.monitoring import (
            get_current_section_attendance_statuses,
        )
        from attendance.services.periods import build_period_snapshot
        from students.models import Grade, Section
        from tests.attendance_helpers import make_students

        school = School.objects.create(name="مدرسة قياس المتابعة", slug="mon-benchmark")
        user = User.objects.create_user(
            mobile="0551118888", password="Bench-123456"  # noqa: S106 — بيانات قياس مؤقتة
        )
        membership = SchoolMembership.objects.create(user=user, school=school)
        SchoolMembershipRole.objects.create(membership=membership, role=SchoolRole.TEACHER)

        day = datetime(2026, 8, 23).date()  # أحد
        now = datetime(2026, 8, 23, 9, 0, tzinfo=ZoneInfo("Asia/Riyadh"))
        try:
            year = AcademicYear.objects.create(
                school=school, name="قياس", start_date=day,
                end_date=datetime(2027, 6, 25).date(), status=AcademicYearStatus.ACTIVE,
            )
            schedule = BellSchedule.objects.create(school=school, name="قياس")
            period = BellPeriod.objects.create(
                school=school, bell_schedule=schedule, sequence=3, name="الثالثة",
                start_time=time(8, 30), end_time=time(9, 15),
            )
            SchoolWeekDay.objects.create(
                school=school, weekday=Weekday.SUNDAY,
                is_school_day=True, bell_schedule=schedule,
            )
            grade = Grade.objects.create(school=school, name="قياس", sequence=1)

            created = 0
            for size in options["sizes"]:
                # إكمال الفصول للعدد المطلوب — توزيع: ثلث معتمد، ثلث قيد، ثلث بلا جلسة
                while created < size:
                    section = Section.objects.create(
                        school=school, grade=grade, code=f"m{created}", name=f"m{created}"
                    )
                    make_students(school, section, year, 3, prefix=f"19{created:02d}")
                    bucket = created % 3
                    if bucket in (0, 1):
                        AttendanceSession.objects.create(
                            school=school, academic_year=year, section=section,
                            attendance_date=day, bell_period=period, period_sequence=3,
                            bell_period_snapshot=build_period_snapshot(
                                period, day, "Asia/Riyadh"
                            ),
                            status="SUBMITTED" if bucket == 0 else "IN_PROGRESS",
                            roster_fingerprint="fp",
                            unprepared_alert_minutes_snapshot=25,
                            started_by_membership=membership,
                            submitted_by_membership=membership if bucket == 0 else None,
                            submitted_at=now if bucket == 0 else None,
                        )
                    created += 1

                durations = []
                for _ in range(RUNS):
                    with CaptureQueriesContext(connection) as ctx:
                        t0 = time_module.perf_counter()
                        payload = get_current_section_attendance_statuses(
                            school=school, now=now
                        )
                        durations.append((time_module.perf_counter() - t0) * 1000)
                    queries = len(ctx.captured_queries)
                if payload["summary"]["total"] != size:
                    raise CommandError(
                        f"عدد غير مكتمل: {payload['summary']['total']} != {size}"
                    )
                p50 = statistics.median(durations)
                self.stdout.write(
                    f"sections={size:4d} | p50={p50:6.1f}ms | "
                    f"max={max(durations):6.1f}ms | queries={queries}"
                )
        finally:
            _cleanup(school, user)
            self.stdout.write(self.style.SUCCESS("benchmark data cleaned."))


def _cleanup(school: School, user: User) -> None:
    from academics.models import AcademicYear, BellSchedule, SchoolWeekDay
    from attendance.models import (
        AttendanceChange,
        AttendanceDayContext,
        AttendanceMark,
        AttendanceSession,
        DailyAttendanceSummary,
    )
    from audit.models import AuditLog
    from students.models import Grade, Section, Student, StudentEnrollment

    DailyAttendanceSummary.objects.filter(school=school).delete()
    AttendanceChange.objects.filter(school=school).delete()
    AttendanceMark.objects.filter(school=school).delete()
    AttendanceSession.objects.filter(school=school).delete()
    AttendanceDayContext.objects.filter(school=school).delete()
    StudentEnrollment.objects.filter(school=school).delete()
    Student.objects.filter(school=school).delete()
    SchoolWeekDay.objects.filter(school=school).delete()
    BellSchedule.objects.filter(school=school).delete()
    Section.objects.filter(school=school).delete()
    Grade.objects.filter(school=school).delete()
    AuditLog.objects.filter(school=school).delete()
    AcademicYear.objects.filter(school=school).delete()
    SchoolMembership.objects.filter(school=school).delete()
    school.delete()
    if not user.memberships.exists():
        user.delete()
