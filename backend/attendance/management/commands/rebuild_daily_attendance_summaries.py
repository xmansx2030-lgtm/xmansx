"""إعادة بناء ملخصات الحضور اليومية — إصلاح/Backfill (idempotent بالكامل).

الاستخدام:
    manage.py rebuild_daily_attendance_summaries --school-slug school-a --date 2026-08-19
    manage.py rebuild_daily_attendance_summaries --from 2026-08-01 --to 2026-08-19
بلا --school-slug يعمل على كل المدارس.
"""

from datetime import date, timedelta

from django.core.management.base import BaseCommand, CommandError

from common.tenant_rls import tenant_context
from schools.models import School


class Command(BaseCommand):
    help = "إعادة بناء DailyAttendanceSummary لمدرسة/تاريخ/مدى — idempotent"

    def add_arguments(self, parser):
        parser.add_argument("--school-slug", default=None)
        parser.add_argument("--date", default=None, help="YYYY-MM-DD")
        parser.add_argument("--from", dest="date_from", default=None)
        parser.add_argument("--to", dest="date_to", default=None)

    def handle(self, *args, **options):
        from attendance.models import AttendanceSession
        from attendance.services.daily_summary import (
            recalculate_daily_attendance_for_section,
        )

        if options["date"]:
            dates = [date.fromisoformat(options["date"])]
        elif options["date_from"] and options["date_to"]:
            start = date.fromisoformat(options["date_from"])
            end = date.fromisoformat(options["date_to"])
            if end < start:
                raise CommandError("‏--to قبل --from.")
            dates = [start + timedelta(days=i) for i in range((end - start).days + 1)]
        else:
            raise CommandError("حدد --date أو (--from و --to).")

        with tenant_context(bypass=True):
            schools_query = School.objects.all()
            if options["school_slug"]:
                schools_query = schools_query.filter(slug=options["school_slug"])
            schools = list(schools_query)
        if options["school_slug"] and not schools:
            raise CommandError("مدرسة غير موجودة.")

        total_rows = 0
        for school in schools:
            with tenant_context(school_id=school.id):
                for target_date in dates:
                    # الفصول ذات جلسات ذلك اليوم — ما بلا جلسات يبقى بلا صفوف
                    section_ids = (
                        AttendanceSession.objects.filter(
                            school=school, attendance_date=target_date
                        )
                        .values_list("section_id", flat=True)
                        .distinct()
                    )
                    from excuses.services.coverage import (
                        reconcile_excuse_coverage_for_date,
                    )
                    from students.models import Section

                    # أداة الإصلاح تصلح التغطية قبل إعادة خبزها في الملخصات.
                    reconcile_excuse_coverage_for_date(
                        school=school, attendance_date=target_date
                    )
                    for section in Section.objects.filter(id__in=list(section_ids)):
                        total_rows += recalculate_daily_attendance_for_section(
                            school=school,
                            section=section,
                            attendance_date=target_date,
                        )
        self.stdout.write(self.style.SUCCESS(f"rebuilt rows: {total_rows}"))
