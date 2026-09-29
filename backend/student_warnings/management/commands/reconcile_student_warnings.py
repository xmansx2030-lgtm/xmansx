"""Preview or reconcile warnings issued before automatic metric reconciliation existed."""

from collections import defaultdict

from django.core.management.base import BaseCommand, CommandError

from academics.models import AcademicYear
from common.tenant_rls import tenant_context
from schools.models import School
from student_warnings.models import StudentWarning, WarningStatus
from student_warnings.selectors.eligibility import metric_for_students
from student_warnings.services.reconciliation import reconcile_issued_warnings


class Command(BaseCommand):
    help = "Preview unsupported issued warnings; --apply voids them and their documents."

    def add_arguments(self, parser):
        parser.add_argument("--school-slug", default=None)
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        if options["apply"] and not options["school_slug"]:
            raise CommandError("حدد --school-slug عند استخدام --apply.")

        with tenant_context(bypass=True):
            schools = School.objects.all().order_by("id")
            if options["school_slug"]:
                schools = schools.filter(slug=options["school_slug"])
            schools = list(schools)
        if options["school_slug"] and not schools:
            raise CommandError("مدرسة غير موجودة.")

        total_candidates = 0
        total_voided = 0
        for school in schools:
            with tenant_context(school_id=school.id):
                warnings = list(
                    StudentWarning.objects.filter(
                        school=school, status=WarningStatus.ISSUED
                    ).values("student_id", "academic_year_id", "warning_type", "threshold_at_issue")
                )
                groups = defaultdict(list)
                for warning in warnings:
                    groups[(warning["academic_year_id"], warning["warning_type"])].append(warning)
                years = AcademicYear.objects.in_bulk({year_id for year_id, _ in groups})
                for (year_id, warning_type), rows in groups.items():
                    student_ids = {row["student_id"] for row in rows}
                    values = metric_for_students(
                        school=school,
                        year=years[year_id],
                        rule_type=warning_type,
                        student_ids=student_ids,
                    )
                    candidates = {
                        row["student_id"]
                        for row in rows
                        if values.get(row["student_id"], 0) < row["threshold_at_issue"]
                    }
                    total_candidates += sum(
                        values.get(row["student_id"], 0) < row["threshold_at_issue"] for row in rows
                    )
                    if options["apply"] and candidates:
                        total_voided += len(
                            reconcile_issued_warnings(
                                school=school,
                                student_ids=candidates,
                                warning_type=warning_type,
                            )
                        )
                self.stdout.write(f"{school.slug}: checked {len(warnings)} issued warnings")

        self.stdout.write(f"unsupported warnings: {total_candidates}; voided: {total_voided}")
