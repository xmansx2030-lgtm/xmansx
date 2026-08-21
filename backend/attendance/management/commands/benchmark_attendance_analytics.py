"""قياس تحليلات الغياب (تطوير فقط): حصة/عدة حصص/يومي/إعادة بناء — 500-5000 طالب."""

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

RUNS = 5
SECTION_SIZE = 30
PERIODS = 7


class Command(BaseCommand):
    help = "قياس زمن واستعلامات تحليلات الغياب (DEBUG فقط)"

    def add_arguments(self, parser):
        parser.add_argument("--sizes", nargs="+", type=int, default=[500, 1000, 3000, 5000])

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("benchmark_attendance_analytics يعمل في التطوير فقط.")

        from academics.models import (
            AcademicYear,
            AcademicYearStatus,
            BellPeriod,
            BellSchedule,
            SchoolWeekDay,
            Weekday,
        )
        from attendance.models import AttendanceMark, AttendanceSession
        from attendance.selectors.analytics import (
            get_daily_report,
            get_multi_period_report,
        )
        from attendance.services.daily_summary import (
            recalculate_daily_attendance_for_section,
        )
        from students.models import Grade, Section
        from tests.attendance_helpers import make_students

        school = School.objects.create(name="مدرسة قياس التحليلات", slug="ana-benchmark")
        user = User.objects.create_user(
            mobile="0551117777", password="Bench-123456"  # noqa: S106 — بيانات قياس مؤقتة
        )
        membership = SchoolMembership.objects.create(user=user, school=school)
        SchoolMembershipRole.objects.create(membership=membership, role=SchoolRole.TEACHER)

        day = datetime(2026, 8, 23).date()  # أحد
        try:
            year = AcademicYear.objects.create(
                school=school, name="قياس", start_date=day,
                end_date=datetime(2027, 6, 25).date(), status=AcademicYearStatus.ACTIVE,
            )
            schedule = BellSchedule.objects.create(school=school, name="قياس")
            for i in range(PERIODS):
                BellPeriod.objects.create(
                    school=school, bell_schedule=schedule, sequence=i + 1,
                    name=f"حصة {i + 1}", start_time=time(7 + i, 0), end_time=time(7 + i, 45),
                )
            SchoolWeekDay.objects.create(
                school=school, weekday=Weekday.SUNDAY,
                is_school_day=True, bell_schedule=schedule,
            )
            grade = Grade.objects.create(school=school, name="قياس", code="B", sequence=1)

            built_students = 0
            section_index = 0
            sections = []
            for size in options["sizes"]:
                # إكمال البيانات تدريجيًا حتى الحجم المطلوب
                while built_students < size:
                    count = min(SECTION_SIZE, size - built_students)
                    section = Section.objects.create(
                        school=school, grade=grade,
                        code=f"b{section_index}", name=f"b{section_index}",
                    )
                    students = make_students(
                        school, section, year, count, prefix=f"39{section_index:03d}"
                    )
                    sections.append(section)
                    for seq in range(1, PERIODS + 1):
                        session = AttendanceSession.objects.create(
                            school=school, academic_year=year, section=section,
                            attendance_date=day, period_sequence=seq,
                            bell_period_snapshot={
                                "sequence": seq, "name": f"حصة {seq}",
                                "start_time": f"{6 + seq:02d}:00",
                                "end_time": f"{6 + seq:02d}:45",
                                "attendance_date": day.isoformat(),
                                "timezone": "Asia/Riyadh",
                            },
                            status="SUBMITTED", roster_fingerprint="fp",
                            unprepared_alert_minutes_snapshot=25,
                            started_by_membership=membership,
                            submitted_by_membership=membership,
                            submitted_at=datetime(
                                2026, 8, 23, 6 + seq, 10, tzinfo=ZoneInfo("Asia/Riyadh")
                            ),
                        )
                        # ~20% غائبون في الحصص 1-3 (يطابقون ALL[1,2,3])، وتأخر متفرق
                        AttendanceMark.objects.bulk_create(
                            AttendanceMark(
                                school=school, session=session, student=s,
                                status="ABSENT",
                            )
                            for i, s in enumerate(students)
                            if i % 5 == 0 and seq <= 3
                        )
                    recalculate_daily_attendance_for_section(
                        school=school, section=section, attendance_date=day
                    )
                    built_students += count
                    section_index += 1

                connection.queries_log.clear()
                self._measure(
                    school, day, size, sections,
                    get_multi_period_report, get_daily_report,
                    recalculate_daily_attendance_for_section,
                )
        finally:
            _cleanup(school, user)
            self.stdout.write(self.style.SUCCESS("benchmark data cleaned."))

    def _measure(self, school, day, size, sections, multi, daily, recalc):
        def timed(label, fn):
            durations = []
            for _ in range(RUNS):
                with CaptureQueriesContext(connection) as ctx:
                    t0 = time_module.perf_counter()
                    fn()
                    durations.append((time_module.perf_counter() - t0) * 1000)
                queries = len(ctx.captured_queries)
            self.stdout.write(
                f"students={size:5d} | {label:<22} | "
                f"p50={statistics.median(durations):7.1f}ms | "
                f"max={max(durations):7.1f}ms | queries={queries}"
            )

        timed("period [1]", lambda: multi(
            school=school, attendance_date=day, sequences=[1], match="ALL_ABSENT"
        ))
        timed("2-period ALL", lambda: multi(
            school=school, attendance_date=day, sequences=[1, 2], match="ALL_ABSENT"
        ))
        timed("3-period ALL", lambda: multi(
            school=school, attendance_date=day, sequences=[1, 2, 3], match="ALL_ABSENT"
        ))
        timed("7-period ALL", lambda: multi(
            school=school, attendance_date=day,
            sequences=[1, 2, 3, 4, 5, 6, 7], match="ALL_ABSENT",
        ))
        timed("daily analytics", lambda: daily(school=school, attendance_date=day))
        timed("rebuild 1 section", lambda: recalc(
            school=school, section=sections[0], attendance_date=day
        ))

        t0 = time_module.perf_counter()
        for section in sections:
            recalc(school=school, section=section, attendance_date=day)
        rebuild_ms = (time_module.perf_counter() - t0) * 1000
        self.stdout.write(
            f"students={size:5d} | {'rebuild full day':<22} | "
            f"total={rebuild_ms:8.1f}ms ({len(sections)} sections)"
        )


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
