"""قياس أداء الحذف النهائي (تطوير فقط) — لضبط PURGE_BATCH_SIZE بالقياس لا التخمين."""

import time
import tracemalloc
from datetime import date

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from academics.models import AcademicYear, AcademicYearStatus
from accounts.models import User
from common.security.identifiers import (
    encrypt_national_id,
    mask_national_id,
    national_id_lookup_hash,
)
from schools.models import School
from students.models import (
    Grade,
    Section,
    Student,
    StudentEnrollment,
    StudentPurgeJob,
    StudentStatus,
)
from students.tasks import run_purge_job


class Command(BaseCommand):
    help = "قياس زمن الحذف النهائي لأحجام مختلفة (DEBUG فقط)"

    def add_arguments(self, parser):
        parser.add_argument("--sizes", nargs="+", type=int, default=[10, 100, 500, 1000])

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("benchmark_purge يعمل في التطوير فقط.")

        school = School.objects.create(name="مدرسة قياس الحذف", slug="purge-benchmark")
        year = AcademicYear.objects.create(
            school=school, name="قياس", start_date=date(2026, 8, 23),
            end_date=date(2027, 6, 25), status=AcademicYearStatus.ACTIVE,
        )
        grade = Grade.objects.create(school=school, code="SEC_3", name="ثالث", sequence=12)
        section = Section.objects.create(school=school, grade=grade, code="1", name="1")
        actor = User.objects.filter(is_superuser=True).first() or User.objects.first()

        try:
            for index, size in enumerate(options["sizes"]):
                students = Student.objects.bulk_create(
                    Student(
                        school=school,
                        national_id_encrypted=encrypt_national_id(f"1{index}{i:08d}"),
                        national_id_lookup_hash=national_id_lookup_hash(f"1{index}{i:08d}"),
                        national_id_masked=mask_national_id(f"1{index}{i:08d}"),
                        full_name=f"قياس {index}-{i}",
                        status=StudentStatus.GRADUATED,
                    )
                    for i in range(size)
                )
                StudentEnrollment.objects.bulk_create(
                    StudentEnrollment(
                        school=school, student=s, academic_year=year, grade=grade,
                        section=section, enrolled_at=date(2026, 8, 23),
                        status="COMPLETED", ended_at=date.today(),
                    )
                    for s in students
                )
                job = StudentPurgeJob.objects.create(
                    school=school, created_by=actor,
                    student_ids=[s.id for s in students], total_students=size,
                )
                tracemalloc.start()
                start = time.perf_counter()
                result = run_purge_job(job.id)
                duration = time.perf_counter() - start
                _, peak = tracemalloc.get_traced_memory()
                tracemalloc.stop()

                job.refresh_from_db()
                if job.deleted_students != size:
                    raise CommandError(
                        f"benchmark invalid: deleted={job.deleted_students} expected={size}"
                    )
                self.stdout.write(
                    f"rows={size:5d} | purge={duration:6.2f}s "
                    f"({size / max(duration, 0.001):6.1f}/s) | status={result} | "
                    f"peak_mem={peak / 1024 / 1024:5.1f}MB"
                )
        finally:
            StudentEnrollment.objects.filter(school=school).delete()
            Student.objects.filter(school=school).delete()
            StudentPurgeJob.objects.filter(school=school).delete()
            from audit.models import AuditLog

            AuditLog.objects.filter(school=school).delete()
            Section.objects.filter(school=school).delete()
            Grade.objects.filter(school=school).delete()
            AcademicYear.objects.filter(school=school).delete()
            school.delete()
            self.stdout.write(self.style.SUCCESS("benchmark data cleaned."))
