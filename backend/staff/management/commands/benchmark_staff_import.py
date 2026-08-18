"""قياس أداء استيراد الموظفين (تطوير فقط) — 50/200/500/1000."""

import io
import time
import tracemalloc

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import BaseCommand, CommandError
from openpyxl import Workbook

from accounts.models import User
from schools.models import School
from staff.models import StaffImportJob, StaffImportStatus
from staff.services.imports import commit as commit_service
from staff.services.imports import mapping as mapping_service
from staff.tasks import process_staff_import_job

HEADERS = ["اسم المعلم", "رقم الجوال", "الرقم الوظيفي"]


def _build_file(count: int, tag: str) -> SimpleUploadedFile:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(HEADERS)
    for i in range(count):
        sheet.append([f"معلم قياس {i}", f"05{tag}{i:04d}", f"T{tag}-{i}"])  # tag 4 خانات → 10 أرقام
    buffer = io.BytesIO()
    workbook.save(buffer)
    return SimpleUploadedFile("staff-benchmark.xlsx", buffer.getvalue())


class Command(BaseCommand):
    help = "قياس زمن parse/preview/commit لاستيراد الموظفين (DEBUG فقط)"

    def add_arguments(self, parser):
        parser.add_argument("--sizes", nargs="+", type=int, default=[50, 200, 500, 1000])

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("benchmark_staff_import يعمل في التطوير فقط.")

        school = School.objects.create(name="مدرسة قياس الموظفين", slug="staff-benchmark")
        actor = User.objects.filter(is_superuser=True).first() or User.objects.first()

        try:
            for index, size in enumerate(options["sizes"]):
                tag = f"9{index}80"  # 4 خانات — جوالات فريدة صالحة لكل حجم
                upload = _build_file(size, tag)
                job = StaffImportJob.objects.create(
                    school=school, uploaded_by=actor,
                    original_filename=upload.name, file=upload, headers=HEADERS,
                )
                mapping = mapping_service.suggest_mapping(HEADERS)
                job.column_mapping = {k: v for k, v in mapping.items() if v is not None}
                job.status = StaffImportStatus.PROCESSING
                job.save()

                tracemalloc.start()
                start = time.perf_counter()
                process_staff_import_job(job.id)
                parse_seconds = time.perf_counter() - start
                _, parse_peak = tracemalloc.get_traced_memory()
                tracemalloc.stop()

                start = time.perf_counter()
                committed_job, _credentials = commit_service.commit_import(
                    job_id=job.id, actor=actor
                )
                commit_seconds = time.perf_counter() - start

                # دليل: الاعتماد أنشأ الحسابات فعلاً (وليس صفوف أخطاء)
                created = committed_job.summary.get("created", 0)
                if created != size:
                    raise CommandError(
                        f"benchmark invalid: created={created} expected={size} "
                        f"(summary={committed_job.summary})"
                    )

                peak_mb = parse_peak / 1024 / 1024
                self.stdout.write(
                    f"rows={size:5d} | parse+preview={parse_seconds:6.2f}s | "
                    f"commit={commit_seconds:6.2f}s (created={created}) | "
                    f"parse_peak_mem={peak_mb:5.1f}MB"
                )
        finally:
            _cleanup(school)
            self.stdout.write(self.style.SUCCESS("benchmark data cleaned."))


def _cleanup(school: School) -> None:
    from audit.models import AuditLog
    from memberships.models import SchoolMembership
    from staff.models import StaffProfile

    user_ids = list(
        SchoolMembership.objects.filter(school=school).values_list("user_id", flat=True)
    )
    StaffProfile.objects.filter(school=school).delete()
    StaffImportJob.objects.filter(school=school).delete()
    SchoolMembership.objects.filter(school=school).delete()
    AuditLog.objects.filter(school=school).delete()
    # حسابات القياس فقط (لا عضويات أخرى لها)
    User.objects.filter(
        id__in=user_ids, memberships__isnull=True, is_superuser=False
    ).delete()
    school.delete()
