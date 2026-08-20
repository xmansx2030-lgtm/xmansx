"""قياس أداء لوحة الإدارة (م15) — المدة وعدد الاستعلامات عند أحجام متزايدة.

يُشغّل يدويًا: python benchmark_dashboard.py
ليس اختبارًا: لا يدخل ضمن pytest حتى لا يبطئ الانحدار.
"""

import os
import time
from datetime import date, timedelta

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.test")
django.setup()

from django.conf import settings  # noqa: E402
from django.db import connection, reset_queries  # noqa: E402
from django.test.runner import DiscoverRunner  # noqa: E402
from django.test.utils import setup_test_environment, teardown_test_environment  # noqa: E402


class Range:
    def __init__(self, from_date, to_date):
        self.from_date = from_date
        self.to_date = to_date
        self.preset = "CUSTOM"

    @property
    def days(self):
        return (self.to_date - self.from_date).days + 1

    def previous(self):
        end = self.from_date - timedelta(days=1)
        return Range(end - timedelta(days=self.days - 1), end)


def main() -> None:
    setup_test_environment()
    runner = DiscoverRunner(verbosity=0, interactive=False)
    old_config = runner.setup_databases()
    settings.DEBUG = True

    from academics.models import AcademicYear, AcademicYearStatus
    from school_dashboard.selectors import attendance as att
    from school_dashboard.selectors import followup as fu
    from schools.models import School
    from students.models import Grade, Section, Student, StudentEnrollment

    school = School.objects.create(name="Perf", slug="perf")
    year = AcademicYear.objects.create(
        school=school, name="2026/2027", start_date=date(2026, 8, 1),
        end_date=date(2027, 6, 25), status=AcademicYearStatus.ACTIVE,
    )
    grade = Grade.objects.create(school=school, name="G", code="G1", sequence=1)
    date_range = Range(date(2026, 8, 16), date(2026, 8, 16))

    print(f"{'students':>9} | {'duration':>10} | {'queries':>7}")
    for size in (500, 1000, 3000, 5000):
        StudentEnrollment.objects.filter(school=school).delete()
        Student.objects.filter(school=school).delete()
        Section.objects.filter(school=school).delete()
        sections = [
            Section.objects.create(school=school, grade=grade, code=str(i), name=str(i))
            for i in range(1, size // 30 + 2)
        ]
        students = Student.objects.bulk_create(
            [
                Student(
                    school=school,
                    full_name=f"S{i}",
                    student_number=str(i),
                    national_id_lookup_hash=f"h{i}",
                    national_id_masked="****",
                    status="ACTIVE",
                )
                for i in range(size)
            ]
        )
        StudentEnrollment.objects.bulk_create(
            [
                StudentEnrollment(
                    school=school, student=student, academic_year=year, grade=grade,
                    section=sections[i % len(sections)], status="ACTIVE",
                    enrolled_at=date(2026, 8, 1),
                )
                for i, student in enumerate(students)
            ]
        )

        reset_queries()
        started = time.perf_counter()
        att.attendance_kpis(school=school, date_range=date_range)
        fu.counseling_metrics(school=school, date_range=date_range)
        fu.warning_metrics(school=school, date_range=date_range)
        fu.referral_metrics(school=school, date_range=date_range)
        elapsed = (time.perf_counter() - started) * 1000
        print(f"{size:>9} | {elapsed:>8.1f}ms | {len(connection.queries):>7}")

    runner.teardown_databases(old_config)
    teardown_test_environment()


if __name__ == "__main__":
    main()
