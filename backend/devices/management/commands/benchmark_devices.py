"""قياس أداء م8.5 (تطوير فقط): استقبال الدفعات، التكرار، وتقارير الصباح."""

import statistics
import time as time_module
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from accounts.models import User
from memberships.models import SchoolMembership
from schools.models import School

TZ = ZoneInfo("Asia/Riyadh")
SECTION_SIZE = 30
RUNS = 5


class Command(BaseCommand):
    help = "قياس استقبال أحداث الأجهزة وتقارير الصباح (DEBUG فقط)"

    def add_arguments(self, parser):
        parser.add_argument("--batches", nargs="+", type=int, default=[100, 500, 1000])
        parser.add_argument(
            "--students", nargs="+", type=int, default=[500, 1000, 3000, 5000]
        )

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("benchmark_devices يعمل في التطوير فقط.")

        from academics.models import AcademicYear, AcademicYearStatus
        from devices.models import (
            AttendanceDevice,
            DeviceEvent,
            IdentityStatus,
            StudentDeviceIdentity,
        )
        from devices.selectors.morning import (
            get_late_list,
            get_morning_summary,
            get_student_late_history,
        )
        from devices.services.bridge import create_bridge
        from devices.services.ingest import ingest_batch
        from students.models import Grade, Section
        from tests.attendance_helpers import make_students

        school = School.objects.create(name="مدرسة قياس الأجهزة", slug="dev-benchmark")
        user = User.objects.create_user(
            mobile="0551116666", password="Bench-123456"  # noqa: S106 — بيانات قياس مؤقتة
        )
        SchoolMembership.objects.create(user=user, school=school)
        day = (datetime.now(TZ) - timedelta(days=1)).date()

        try:
            year = AcademicYear.objects.create(
                school=school, name="قياس", start_date=date(2026, 8, 23),
                end_date=date(2027, 6, 25), status=AcademicYearStatus.ACTIVE,
            )
            grade = Grade.objects.create(school=school, name="قياس", code="B", sequence=1)
            bridge, _ = create_bridge(school=school, name="جسر قياس", actor=None)
            device = AttendanceDevice.objects.create(school=school, name="بوابة قياس")

            students = []
            section_index = 0
            max_students = max(options["students"])
            while len(students) < max_students:
                count = min(SECTION_SIZE, max_students - len(students))
                section = Section.objects.create(
                    school=school, grade=grade,
                    code=f"d{section_index}", name=f"d{section_index}",
                )
                students.extend(
                    make_students(school, section, year, count, prefix=f"69{section_index:03d}")
                )
                section_index += 1
            StudentDeviceIdentity.objects.bulk_create(
                StudentDeviceIdentity(
                    school=school, device=device, external_user_id=str(i),
                    student=s, status=IdentityStatus.MATCHED,
                )
                for i, s in enumerate(students)
            )

            def make_events(start_index, count, minute_base=10):
                return [
                    {
                        "device_id": device.id,
                        "external_event_id": f"bench-{start_index + i}",
                        "external_user_id": str((start_index + i) % max_students),
                        "occurred_at": datetime.combine(
                            day, time(7, minute_base + (i % 40)), tzinfo=TZ
                        ),
                        "verification_method": "FINGERPRINT",
                        "event_type": "CHECK_IN",
                    }
                    for i in range(count)
                ]

            # ---- استقبال الدفعات ----
            offset = 0
            for size in options["batches"]:
                events = make_events(offset, size)
                t0 = time_module.perf_counter()
                results = ingest_batch(bridge=bridge, events=events)
                ingest_ms = (time_module.perf_counter() - t0) * 1000
                accepted = sum(1 for r in results if r["result"] == "accepted")
                if accepted != size:
                    raise CommandError(f"قبول ناقص: {accepted} != {size}")
                # نفس الدفعة ثانية — كلها duplicates (قياس dedupe)
                t0 = time_module.perf_counter()
                dupes = ingest_batch(bridge=bridge, events=events)
                dedupe_ms = (time_module.perf_counter() - t0) * 1000
                if not all(r["result"] == "duplicate" for r in dupes):
                    raise CommandError("dedupe لم يعمل")
                self.stdout.write(
                    f"batch={size:5d} | ingest={ingest_ms:7.1f}ms "
                    f"({ingest_ms / size:5.2f}ms/event) | dedupe={dedupe_ms:7.1f}ms"
                )
                offset += size

            total_events = DeviceEvent.objects.filter(school=school).count()
            self.stdout.write(f"stored events: {total_events}")

            # ---- تقارير الصباح حسب عدد الطلاب ----
            for target in options["students"]:
                subset = students[:target]

                def timed(label, fn, size=target):
                    durations = []
                    for _ in range(RUNS):
                        t0 = time_module.perf_counter()
                        fn()
                        durations.append((time_module.perf_counter() - t0) * 1000)
                    self.stdout.write(
                        f"students={size:5d} | {label:<18} | "
                        f"p50={statistics.median(durations):7.1f}ms | "
                        f"max={max(durations):7.1f}ms"
                    )

                timed("late list", lambda: get_late_list(
                    school=school, attendance_date=day, page_size=100
                ))
                timed("summary", lambda: get_morning_summary(
                    school=school, attendance_date=day
                ))
                timed("student history", lambda s=subset[0]: get_student_late_history(
                    school=school, student=s,
                    date_from=day - timedelta(days=30), date_to=day,
                ))
        finally:
            _cleanup(school, user)
            self.stdout.write(self.style.SUCCESS("benchmark data cleaned."))


def _cleanup(school: School, user: User) -> None:
    from academics.models import AcademicYear
    from audit.models import AuditLog
    from devices.models import (
        AttendanceDevice,
        DeviceBridgeInstallation,
        DeviceEvent,
        SchoolArrival,
        SchoolArrivalChange,
        StudentDeviceIdentity,
    )
    from students.models import Grade, Section, Student, StudentEnrollment

    SchoolArrivalChange.objects.filter(school=school).delete()
    SchoolArrival.objects.filter(school=school).delete()
    DeviceEvent.objects.filter(school=school).delete()
    StudentDeviceIdentity.objects.filter(school=school).delete()
    AttendanceDevice.objects.filter(school=school).delete()
    DeviceBridgeInstallation.objects.filter(school=school).delete()
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
