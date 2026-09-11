"""قياس أداء توليد المستندات وقوائمها (البنود 134-136) — DEBUG فقط.

يقيس: مستند إنذار، تعهد، وكشف غياب بـ30/100/500 صفًا، وقوائم الإجراءات/المستندات
بأحجام مختلفة مع عدّ الاستعلامات (كشف N+1).

    manage.py benchmark_documents --school-slug school-a
"""

import time
from datetime import date, timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone as dj_timezone


class Command(BaseCommand):
    help = "قياس توليد المستندات وقوائمها — لا يشغل في الإنتاج"

    def add_arguments(self, parser):
        parser.add_argument("--school-slug", required=True)

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("القياس متاح في التطوير فقط.")

        from academics.models import AcademicYear, AcademicYearStatus
        from attendance.models import (
            DailyAbsenceStatus,
            DailyAttendanceSummary,
            DailyCompleteness,
        )
        from documents.models import DocumentType
        from documents.services import snapshots as snapshot_service
        from documents.services.generation import generate_document
        from memberships.models import SchoolMembership, SchoolRole
        from schools.models import School
        from student_warnings.models import (
            StudentWarning,
            WarningLevel,
            WarningRuleType,
            WarningStatus,
        )
        from students.models import Student

        school = School.objects.filter(slug=options["school_slug"]).first()
        if school is None:
            raise CommandError("مدرسة غير موجودة.")
        membership = (
            SchoolMembership.objects.filter(
                school=school, roles__role=SchoolRole.SCHOOL_MANAGER
            )
            .select_related("user")
            .first()
        )
        if membership is None:
            raise CommandError("لا يوجد مدير لهذه المدرسة.")
        student = Student.objects.filter(school=school).first()
        section = getattr(
            student.enrollments.select_related("section").order_by("-enrolled_at").first(),
            "section",
            None,
        ) if student else None
        year = AcademicYear.objects.filter(school=school, status=AcademicYearStatus.ACTIVE).first()
        if student is None or year is None or section is None:
            raise CommandError("بيانات ناقصة (طالب/قيد/عام دراسي نشط).")

        def timed(label, fn):
            start = time.perf_counter()
            result = fn()
            elapsed = (time.perf_counter() - start) * 1000
            self.stdout.write(f"{label}: {elapsed:.0f}ms")
            return result

        with transaction.atomic():
            warning = StudentWarning.objects.create(
                school=school, student=student, academic_year=year,
                warning_type=WarningRuleType.UNEXCUSED_FULL_DAY_ABSENCE,
                level=WarningLevel.LEVEL_3, status=WarningStatus.ISSUED,
                threshold_at_issue=10, metric_value_at_issue=12,
                student_name_snapshot=student.full_name,
                grade_name_snapshot="قياس", section_name_snapshot="قياس",
                national_id_masked_snapshot=student.national_id_masked,
                issued_by_membership=membership, issued_at=dj_timezone.now(),
            )
            timed(
                "مستند إنذار",
                lambda: generate_document(
                    school=school, membership=membership, student=student,
                    document_type=DocumentType.WARNING_LEVEL_3, warning_id=warning.id,
                ),
            )
            timed(
                "تعهد حضور",
                lambda: generate_document(
                    school=school, membership=membership, student=student,
                    document_type=DocumentType.ATTENDANCE_COMMITMENT,
                    from_date=year.start_date, to_date=year.end_date,
                ),
            )

            base = date(2020, 1, 1)  # تواريخ قياس بعيدة عن بيانات المدرسة الحقيقية
            for size in (30, 100, 300):
                DailyAttendanceSummary.objects.filter(
                    student=student, attendance_date__gte=base
                ).delete()
                DailyAttendanceSummary.objects.bulk_create(
                    [
                        DailyAttendanceSummary(
                            school=school, student=student, section=section,
                            academic_year=year, attendance_date=base + timedelta(days=i),
                            absence_status=DailyAbsenceStatus.FULL, absent_periods=7,
                            unexcused_absent_periods=7, expected_periods=7,
                            submitted_periods=7, present_periods=0,
                            completeness_status=DailyCompleteness.COMPLETE,
                            calculated_at=dj_timezone.now(),
                        )
                        for i in range(size)
                    ]
                )
                timed(
                    f"كشف غياب {size} صفًا",
                    lambda size=size: generate_document(
                        school=school, membership=membership, student=student,
                        document_type=DocumentType.ABSENCE_DETAIL_REPORT,
                        from_date=base, to_date=base + timedelta(days=size + 1),
                    ),
                )
                timed(
                    f"لقطة كشف {size} صفًا (بلا PDF)",
                    lambda size=size: snapshot_service.absence_report_snapshot(
                        school=school, student=student, membership=membership,
                        from_date=base, to_date=base + timedelta(days=size + 1),
                    ),
                )

            # 500 صف تتجاوز نافذة العام (حارس المدى)، فيقاس الرسم وحده على لقطة موسعة
            snapshot = snapshot_service.absence_report_snapshot(
                school=school, student=student, membership=membership,
                from_date=base, to_date=base + timedelta(days=301),
            )
            rows = snapshot["rows"]
            snapshot["rows"] = (rows * (500 // max(1, len(rows)) + 1))[:500]
            timed("رسم PDF لكشف 500 صف", lambda: self._render_only(snapshot))

            self._list_queries(school)
            transaction.set_rollback(True)  # لا يترك بيانات قياس في قاعدة التطوير
        self.stdout.write(self.style.SUCCESS("تم القياس (وأعيدت البيانات كما كانت)."))

    def _render_only(self, snapshot: dict) -> int:
        from django.template.loader import render_to_string

        from documents.pdf import render_pdf_with_pages

        html = render_to_string("documents/absence_report.html", {"data": snapshot})
        pdf, pages = render_pdf_with_pages(html)
        self.stdout.write(f"  (صفحات: {pages} — حجم: {len(pdf) // 1024}KB)")
        return len(pdf)

    def _list_queries(self, school):
        from documents.api.views import _base_queryset as documents_queryset
        from student_actions.api.views import _base_queryset as actions_queryset

        for label, queryset in (
            ("قائمة المستندات (25)", documents_queryset(school)[:25]),
            ("قائمة الإجراءات (25)", actions_queryset(school)[:25]),
        ):
            connection.queries_log.clear()
            start = time.perf_counter()
            rows = list(queryset)
            elapsed = (time.perf_counter() - start) * 1000
            self.stdout.write(
                f"{label}: {elapsed:.0f}ms — استعلامات: {len(connection.queries)}"
                f" — صفوف: {len(rows)}"
            )
