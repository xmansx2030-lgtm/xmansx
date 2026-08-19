"""قياس مزامنة قوائم الأجهزة (تطوير فقط): المقارنة والحفظ 500-5000 طالب."""

import statistics
import time as time_module
from datetime import date

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.test.utils import CaptureQueriesContext

from accounts.models import User
from memberships.models import SchoolMembership
from schools.models import School

SECTION_SIZE = 30
RUNS = 3


class Command(BaseCommand):
    help = "قياس مقارنة/حفظ مزامنة قائمة الجهاز (DEBUG فقط)"

    def add_arguments(self, parser):
        parser.add_argument("--sizes", nargs="+", type=int, default=[500, 1000, 3000, 5000])

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("benchmark_roster يعمل في التطوير فقط.")

        from academics.models import AcademicYear, AcademicYearStatus
        from devices.models import AttendanceDevice, DeviceRosterSyncJob, DeviceRosterSyncStatus
        from devices.services.roster import (
            active_student_roster,
            compare_device_roster,
            save_analysis,
        )
        from students.models import Grade, Section
        from tests.attendance_helpers import make_students

        school = School.objects.create(name="مدرسة قياس المزامنة", slug="ros-benchmark")
        user = User.objects.create_user(
            mobile="0551115555", password="Bench-123456"  # noqa: S106 — بيانات قياس مؤقتة
        )
        membership = SchoolMembership.objects.create(user=user, school=school)

        try:
            year = AcademicYear.objects.create(
                school=school, name="قياس", start_date=date(2026, 8, 23),
                end_date=date(2027, 6, 25), status=AcademicYearStatus.ACTIVE,
            )
            grade = Grade.objects.create(school=school, name="قياس", code="B", sequence=1)
            device = AttendanceDevice.objects.create(school=school, name="بوابة قياس")

            built = 0
            section_index = 0
            for size in options["sizes"]:
                while built < size:
                    count = min(SECTION_SIZE, size - built)
                    section = Section.objects.create(
                        school=school, grade=grade,
                        code=f"r{section_index}", name=f"r{section_index}",
                    )
                    make_students(school, section, year, count, prefix=f"79{section_index:03d}")
                    built += count
                    section_index += 1

                # نصف القائمة موجود على الجهاز (matched/update) والنصف الآخر create
                desired = active_student_roster(school=school)
                device_users = [
                    {"external_user_id": row["external_user_id"],
                     "display_name": row["display_name"]}
                    for i, row in enumerate(desired) if i % 2 == 0
                ]

                durations = []
                for _ in range(RUNS):
                    with CaptureQueriesContext(connection) as ctx:
                        t0 = time_module.perf_counter()
                        result = compare_device_roster(
                            school=school, device=device, device_users=device_users
                        )
                        durations.append((time_module.perf_counter() - t0) * 1000)
                    queries = len(ctx.captured_queries)
                if result["summary"]["matched_count"] + result["summary"]["create_count"] != size:
                    raise CommandError("تصنيف ناقص — القياس غير صالح")
                self.stdout.write(
                    f"students={size:5d} | compare  | "
                    f"p50={statistics.median(durations):8.1f}ms | queries={queries}"
                )

                job = DeviceRosterSyncJob.objects.create(
                    school=school, device=device, created_by_membership=membership,
                    status=DeviceRosterSyncStatus.ANALYZING,
                )
                t0 = time_module.perf_counter()
                save_analysis(job=job, device_users=device_users)
                save_ms = (time_module.perf_counter() - t0) * 1000
                self.stdout.write(
                    f"students={size:5d} | save     | total={save_ms:8.1f}ms "
                    f"(items={job.items.count()})"
                )
                job.items.all().delete()
                job.delete()
        finally:
            _cleanup(school, user)
            self.stdout.write(self.style.SUCCESS("benchmark data cleaned."))


def _cleanup(school: School, user: User) -> None:
    from academics.models import AcademicYear
    from audit.models import AuditLog
    from devices.models import (
        AttendanceDevice,
        DeviceRosterSyncItem,
        DeviceRosterSyncJob,
        StudentDeviceIdentity,
    )
    from students.models import Grade, Section, Student, StudentEnrollment

    DeviceRosterSyncItem.objects.filter(device__school=school).delete()
    DeviceRosterSyncJob.objects.filter(school=school).delete()
    StudentDeviceIdentity.objects.filter(school=school).delete()
    AttendanceDevice.objects.filter(school=school).delete()
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
