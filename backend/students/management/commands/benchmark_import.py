"""قياس أداء الاستيراد (تطوير فقط) — أرقام موثقة في تقرير المرحلة.

الاستخدام: python manage.py benchmark_import --sizes 500 1500 3000
ينشئ مدرسة قياس مؤقتة ويحذفها بعد الانتهاء.
"""

import io
import time
import tracemalloc
from datetime import date

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import BaseCommand, CommandError
from openpyxl import Workbook

from academics.models import AcademicYear, AcademicYearStatus
from accounts.models import User
from schools.models import School
from students.models import ImportJobStatus, StudentImportJob
from students.services.imports import commit as commit_service
from students.services.imports import mapping as mapping_service
from students.tasks import process_import_job

HEADERS = ["رقم الهوية", "اسم الطالب", "الصف", "الفصل"]


def _build_file(count: int) -> SimpleUploadedFile:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(HEADERS)
    grades = ["الأول الثانوي", "الثاني الثانوي", "الثالث الثانوي"]
    for i in range(count):
        sheet.append([
            f"1{i:09d}", f"طالب قياس {i}", grades[i % 3], str((i % 8) + 1),
        ])
    buffer = io.BytesIO()
    workbook.save(buffer)
    return SimpleUploadedFile("benchmark.xlsx", buffer.getvalue())


class Command(BaseCommand):
    help = "قياس زمن parse/preview/commit لأحجام مختلفة (DEBUG فقط)"

    def add_arguments(self, parser):
        parser.add_argument("--sizes", nargs="+", type=int, default=[500, 1500, 3000])

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("benchmark_import يعمل في التطوير فقط.")

        school = School.objects.create(name="مدرسة القياس", slug="benchmark-school")
        year = AcademicYear.objects.create(
            school=school, name="قياس", start_date=date(2026, 8, 23),
            end_date=date(2027, 6, 25), status=AcademicYearStatus.ACTIVE,
        )
        actor = User.objects.filter(is_superuser=True).first() or User.objects.first()

        try:
            for size in options["sizes"]:
                upload = _build_file(size)
                job = StudentImportJob.objects.create(
                    school=school, uploaded_by=actor, academic_year=year,
                    original_filename=upload.name, file=upload, headers=HEADERS,
                )
                mapping = mapping_service.suggest_mapping(HEADERS)
                job.column_mapping = {k: v for k, v in mapping.items() if v is not None}
                job.status = ImportJobStatus.PROCESSING
                job.save()

                tracemalloc.start()
                start = time.perf_counter()
                process_import_job(job.id)  # متزامن للقياس
                parse_seconds = time.perf_counter() - start
                _, parse_peak = tracemalloc.get_traced_memory()
                tracemalloc.stop()

                start = time.perf_counter()
                commit_service.commit_import(job_id=job.id, actor=actor)
                commit_seconds = time.perf_counter() - start

                peak_mb = parse_peak / 1024 / 1024
                self.stdout.write(
                    f"rows={size:5d} | parse+preview={parse_seconds:6.2f}s | "
                    f"commit={commit_seconds:6.2f}s | parse_peak_mem={peak_mb:5.1f}MB"
                )
        finally:
            _cleanup_school(school)
            self.stdout.write(self.style.SUCCESS("benchmark data cleaned."))


def _cleanup_school(school: School) -> None:
    """حذف بيانات القياس بالترتيب الصحيح (PROTECT FKs تمنع cascade مباشر)."""
    from audit.models import AuditLog
    from students.models import Grade, Section, Student, StudentEnrollment

    StudentEnrollment.objects.filter(school=school).delete()
    Student.objects.filter(school=school).delete()
    StudentImportJob.objects.filter(school=school).delete()
    Section.objects.filter(school=school).delete()
    Grade.objects.filter(school=school).delete()
    AuditLog.objects.filter(school=school).delete()  # بيانات قياس فقط — ليست إنتاجًا
    AcademicYear.objects.filter(school=school).delete()
    school.delete()
