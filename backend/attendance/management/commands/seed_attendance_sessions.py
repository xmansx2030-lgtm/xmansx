"""بذر جلسات حضور معتمدة لحصص محددة — بيئة التطوير/E2E المحلية فقط.

لا يمكن عبر الواجهة فتح جلسة إلا للحصة الحالية، بينما تحتاج اختبارات E2E بيانات
حصص متعددة في نفس اليوم — هذا الأمر يبنيها عبر نفس النماذج والخدمات (snapshot +
ملخصات) دون أي مسار HTTP إنتاجي.

الخطة JSON عبر stdin:
{
  "school": "school-a",
  "sections": [
    {"code": "A1-x", "periods": [
      {"sequence": 1, "absent": ["اسم"]}
    ]}
  ]
}
يطبع JSON: معرفات الجلسات والطلاب — لاستخدامها في خطوات E2E اللاحقة (تعديل PATCH).
"""

import json
import sys
from datetime import date

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone as dj_timezone

from schools.models import School


class Command(BaseCommand):
    help = "بذر جلسات حضور لعدة حصص (DEBUG فقط — للتطوير وE2E)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--allow-production-like",
            action="store_true",
            help="السماح فقط لحزمة E2E محلية تستخدم production settings",
        )

    def handle(self, *args, **options):
        allowed_local_hosts = {"localhost", "127.0.0.1", "backend", "testserver"}
        production_like_e2e = (
            options["allow_production_like"]
            and not settings.SECURE_SSL_REDIRECT
            and bool(settings.ALLOWED_HOSTS)
            and set(settings.ALLOWED_HOSTS).issubset(allowed_local_hosts)
        )
        if not settings.DEBUG and not production_like_e2e:
            raise CommandError("seed_attendance_sessions يعمل في التطوير فقط.")

        from attendance.models import (
            AttendanceMark,
            AttendanceSession,
            AttendanceSessionStatus,
        )
        from attendance.services.daily_summary import (
            recalculate_daily_attendance_for_section,
        )
        from attendance.services.day_context import get_or_create_attendance_day_context
        from attendance.services.periods import school_now
        from attendance.services.sessions import _active_year, get_roster
        from excuses.services.coverage import reconcile_excuse_coverage_for_date
        from memberships.models import SchoolMembership, SchoolRole
        from schools.services.settings import get_or_create_settings
        from students.models import Section

        plan = json.loads(sys.stdin.read())
        school = School.objects.get(slug=plan["school"])
        year = _active_year(school)
        settings_obj = get_or_create_settings(school=school)
        # ‏date اختياري (م11): سيناريوهات الإنذارات تحتاج عدة أيام سابقة
        local_date = (
            date.fromisoformat(plan["date"])
            if plan.get("date")
            else school_now(school).date()
        )
        context = get_or_create_attendance_day_context(
            school=school, attendance_date=local_date
        )
        periods_by_seq = {p["sequence"]: p for p in context.attendance_periods}

        membership = (
            SchoolMembership.objects.filter(
                school=school, roles__role=SchoolRole.TEACHER
            )
            .select_related("user")
            .first()
        )
        if membership is None:
            raise CommandError("لا معلم في المدرسة — شغّل seed_dev أولًا.")

        output = {"date": local_date.isoformat(), "sections": {}}
        seeded_sections = []
        for section_plan in plan["sections"]:
            section = Section.objects.filter(
                school=school, code=section_plan["code"]
            ).first()
            if section is None:
                raise CommandError(f"الفصل {section_plan['code']} غير موجود.")
            roster = get_roster(school=school, section=section, academic_year=year)
            by_name = {r["full_name"]: r["student_id"] for r in roster}
            section_out = {"sessions": {}, "students": by_name}

            for period_plan in section_plan["periods"]:
                seq = period_plan["sequence"]
                period = periods_by_seq.get(seq)
                if period is None:
                    raise CommandError(f"الحصة {seq} غير موجودة في جدول اليوم.")
                start_h, start_m = (int(x) for x in period["start_time"].split(":"))
                session, _ = AttendanceSession.objects.update_or_create(
                    school=school,
                    section=section,
                    attendance_date=local_date,
                    period_sequence=seq,
                    defaults={
                        "academic_year": year,
                        "bell_period": None,
                        "bell_period_snapshot": {
                            "sequence": seq,
                            "name": period["name"],
                            "start_time": period["start_time"],
                            "end_time": period["end_time"],
                            "bell_schedule_id": None,
                            "bell_schedule_name": context.schedule_snapshot.get(
                                "schedule_name"
                            ),
                            "attendance_date": local_date.isoformat(),
                            "timezone": settings_obj.timezone,
                        },
                        "status": AttendanceSessionStatus.SUBMITTED,
                        "roster_fingerprint": "seeded",
                        "unprepared_alert_minutes_snapshot": (
                            settings_obj.unprepared_period_alert_minutes
                        ),
                        "started_by_membership": membership,
                        "submitted_by_membership": membership,
                        "submitted_at": dj_timezone.now(),
                    },
                )
                session.marks.all().delete()
                marks = []
                for name in period_plan.get("absent", []):
                    marks.append(
                        AttendanceMark(
                            school=school, session=session,
                            student_id=by_name[name], status="ABSENT",
                        )
                    )
                AttendanceMark.objects.bulk_create(marks)
                section_out["sessions"][str(seq)] = session.id

            seeded_sections.append(section)
            output["sections"][section_plan["code"]] = section_out

        # نفس ترتيب مسار الاعتماد الحقيقي (submit_session): مواءمة تغطيات الأعذار
        # قبل إعادة حساب الملخصات — وإلا خالفت حالة البذر سلوك الإنتاج
        reconcile_excuse_coverage_for_date(school=school, attendance_date=local_date)
        for section in seeded_sections:
            recalculate_daily_attendance_for_section(
                school=school, section=section, attendance_date=local_date
            )

        self.stdout.write(json.dumps(output, ensure_ascii=False))
