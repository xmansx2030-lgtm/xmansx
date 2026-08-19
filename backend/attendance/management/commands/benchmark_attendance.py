"""قياس أداء الحضور (تطوير فقط): roster/start/submit/edit لأحجام 20-100."""

import time as time_module

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from accounts.models import User
from memberships.models import SchoolMembership, SchoolMembershipRole, SchoolRole
from schools.models import School


class Command(BaseCommand):
    help = "قياس زمن مسارات الحضور (DEBUG فقط)"

    def add_arguments(self, parser):
        parser.add_argument("--sizes", nargs="+", type=int, default=[20, 40, 60, 100])

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("benchmark_attendance يعمل في التطوير فقط.")

        from attendance.services import sessions as svc
        from tests.attendance_helpers import make_students, setup_attendance_env

        school = School.objects.create(name="مدرسة قياس الحضور", slug="att-benchmark")
        user = User.objects.create_user(
            mobile="0551119999", password="Bench-123456"  # noqa: S106 — بيانات قياس مؤقتة
        )
        membership = SchoolMembership.objects.create(user=user, school=school)
        SchoolMembershipRole.objects.create(membership=membership, role=SchoolRole.TEACHER)

        try:
            for index, size in enumerate(options["sizes"]):
                env = setup_attendance_env(school, students_count=0)
                # فصل مستقل لكل حجم (يتفادى قيد الجلسة الفريدة)
                from students.models import Section

                section = Section.objects.create(
                    school=school, grade=env["grade"], code=f"B{index}", name=f"B{index}"
                )
                students = make_students(
                    school, section, env["year"], size, prefix=f"2{index}9"
                )

                t0 = time_module.perf_counter()
                session, roster, _ = svc.start_session(
                    school=school, membership=membership, section=section
                )
                start_seconds = time_module.perf_counter() - t0

                t0 = time_module.perf_counter()
                roster = svc.get_roster(
                    school=school, section=section, academic_year=env["year"]
                )
                roster_seconds = time_module.perf_counter() - t0
                if len(roster) != size:
                    raise CommandError(f"قائمة غير مكتملة: {len(roster)} != {size}")

                marks = [
                    {"student_id": s.id, "status": "ABSENT"} for s in students[:3]
                ]
                t0 = time_module.perf_counter()
                svc.submit_session(
                    session_id=session.id, school=school,
                    membership=membership, marks=marks,
                )
                submit_seconds = time_module.perf_counter() - t0

                t0 = time_module.perf_counter()
                svc.edit_session(
                    session_id=session.id, school=school, membership=membership,
                    roles=[SchoolRole.TEACHER], marks=[], reason="قياس",
                )
                edit_seconds = time_module.perf_counter() - t0

                self.stdout.write(
                    f"roster={size:4d} | start={start_seconds * 1000:6.0f}ms | "
                    f"roster={roster_seconds * 1000:5.0f}ms | "
                    f"submit={submit_seconds * 1000:6.0f}ms | "
                    f"edit={edit_seconds * 1000:5.0f}ms"
                )
        finally:
            _cleanup(school, user)
            self.stdout.write(self.style.SUCCESS("benchmark data cleaned."))


def _cleanup(school: School, user: User) -> None:
    from academics.models import AcademicYear, BellSchedule, SchoolWeekDay
    from attendance.models import AttendanceChange, AttendanceMark, AttendanceSession
    from audit.models import AuditLog
    from students.models import Grade, Section, Student, StudentEnrollment

    AttendanceChange.objects.filter(school=school).delete()
    AttendanceMark.objects.filter(school=school).delete()
    AttendanceSession.objects.filter(school=school).delete()
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
