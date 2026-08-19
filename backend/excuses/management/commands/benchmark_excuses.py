"""قياس أداء الأعذار (تطوير فقط): الاعتماد بأحجام مختلفة + القائمة + التفاصيل.

يقيس المسارات التي يمكن أن تتحول إلى N+1: الاعتماد (حل الأهداف + إنشاء التغطيات
+ إعادة حساب الملخصات)، وقائمة الأعذار، وتفاصيل العذر، والمعاينة.
"""

import statistics
import time as time_module
from datetime import date, datetime, timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.test.utils import CaptureQueriesContext

from accounts.models import User
from memberships.models import SchoolMembership, SchoolMembershipRole, SchoolRole
from schools.models import School

RUNS = 3


def _purge_previous(*, slug: str, mobile_suffix: str) -> None:
    """يحذف بقايا تشغيل سابق انقطع قبل التنظيف — ترتيب التبعيات نفسه."""
    from academics.models import (
        AcademicYear,
        BellPeriod,
        BellSchedule,
        SchoolWeekDay,
    )
    from attendance.models import (
        AttendanceDayContext,
        AttendanceMark,
        AttendanceSession,
        DailyAttendanceSummary,
    )
    from audit.models import AuditLog
    from excuses.models import (
        AbsenceExcuse,
        AbsenceExcuseCoverage,
        AbsenceExcuseTarget,
    )
    from students.models import Grade, Section, Student, StudentEnrollment

    school = School.objects.filter(slug=slug).first()
    if school is not None:
        AuditLog.objects.filter(school=school).delete()
        AbsenceExcuseCoverage.objects.filter(school=school).delete()
        AbsenceExcuseTarget.objects.filter(school=school).delete()
        AbsenceExcuse.objects.filter(school=school).delete()
        AttendanceMark.objects.filter(school=school).delete()
        DailyAttendanceSummary.objects.filter(school=school).delete()
        AttendanceSession.objects.filter(school=school).delete()
        AttendanceDayContext.objects.filter(school=school).delete()
        StudentEnrollment.objects.filter(school=school).delete()
        Student.objects.filter(school=school).delete()
        Section.objects.filter(school=school).delete()
        Grade.objects.filter(school=school).delete()
        BellPeriod.objects.filter(school=school).delete()
        SchoolWeekDay.objects.filter(school=school).delete()
        BellSchedule.objects.filter(school=school).delete()
        AcademicYear.objects.filter(school=school).delete()
        SchoolMembershipRole.objects.filter(membership__school=school).delete()
        SchoolMembership.objects.filter(school=school).delete()
        school.delete()
    User.objects.filter(mobile__endswith=mobile_suffix).delete()


class Command(BaseCommand):
    help = "قياس اعتماد الأعذار وقوائمها (DEBUG فقط)"

    def add_arguments(self, parser):
        parser.add_argument("--periods", nargs="+", type=int, default=[1, 7, 30, 100])
        parser.add_argument("--list-sizes", nargs="+", type=int, default=[100, 1000])

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("benchmark_excuses يعمل في التطوير فقط.")

        from academics.models import (
            AcademicYear,
            AcademicYearStatus,
            BellPeriod,
            BellSchedule,
            SchoolWeekDay,
            Weekday,
        )
        from attendance.models import AttendanceMark, AttendanceSession
        from excuses.api.serializers import serialize_excuse_detail, serialize_excuse_row
        from excuses.models import AbsenceExcuse, AbsenceExcuseStatus
        from excuses.services.coverage import approve_excuse, resolve_coverage_plan
        from excuses.services.excuses import create_excuse
        from students.models import Grade, Section
        from tests.attendance_helpers import make_students

        # تنظيف بقايا تشغيل سابق انقطع (لا يعتمد القياس على حالة سابقة)
        _purge_previous(slug="exc-benchmark", mobile_suffix="1115555")

        school = School.objects.create(name="مدرسة قياس الأعذار", slug="exc-benchmark")
        user = User.objects.create_user(
            mobile="0551115555", password="Bench-123456"  # noqa: S106 — بيانات قياس مؤقتة
        )
        membership = SchoolMembership.objects.create(user=user, school=school)
        SchoolMembershipRole.objects.create(
            membership=membership, role=SchoolRole.VICE_PRINCIPAL
        )

        def timed(label, fn):
            durations = []
            queries = 0
            for _ in range(RUNS):
                with CaptureQueriesContext(connection) as ctx:
                    t0 = time_module.perf_counter()
                    fn()
                    durations.append((time_module.perf_counter() - t0) * 1000)
                queries = len(ctx.captured_queries)
            self.stdout.write(
                f"{label:<34} | p50={statistics.median(durations):8.1f}ms | queries={queries}"
            )

        try:
            max_periods = max(options["periods"])
            year = AcademicYear.objects.create(
                school=school, name="قياس", start_date=date(2025, 9, 1),
                end_date=date(2026, 8, 30), status=AcademicYearStatus.ACTIVE,
            )
            schedule = BellSchedule.objects.create(school=school, name="قياس")
            # حصص وهمية كثيرة على أيام متعددة — الغياب موزع عليها
            per_day = 7
            for i in range(per_day):
                BellPeriod.objects.create(
                    school=school, bell_schedule=schedule, sequence=i + 1,
                    name=f"الحصة {i + 1}",
                    start_time=f"{7 + i:02d}:00", end_time=f"{7 + i:02d}:45",
                )
            for weekday in Weekday.values:
                SchoolWeekDay.objects.update_or_create(
                    school=school, weekday=weekday,
                    defaults={"is_school_day": True, "bell_schedule": schedule},
                )
            grade = Grade.objects.create(school=school, name="قياس", code="B", sequence=1)
            section = Section.objects.create(school=school, grade=grade, code="e", name="e")
            students = make_students(school, section, year, 2, prefix="88000")
            student = students[0]

            # أيام غياب كاملة كافية لأكبر قياس
            days_needed = -(-max_periods // per_day)
            base_day = date(2026, 8, 18)
            days = [base_day - timedelta(days=offset) for offset in range(days_needed)]
            sessions = []
            for day in days:
                for seq in range(1, per_day + 1):
                    session = AttendanceSession.objects.create(
                        school=school, academic_year=year, section=section,
                        attendance_date=day, period_sequence=seq,
                        bell_period_snapshot={
                            "sequence": seq, "name": f"الحصة {seq}",
                            "start_time": f"{6 + seq:02d}:00",
                            "end_time": f"{6 + seq:02d}:45",
                            "attendance_date": day.isoformat(),
                            "timezone": "Asia/Riyadh",
                        },
                        status="SUBMITTED", roster_fingerprint="bench",
                        unprepared_alert_minutes_snapshot=25,
                        started_by_membership=membership,
                        submitted_by_membership=membership,
                        submitted_at=datetime.now().astimezone(),
                    )
                    sessions.append(session)
                    AttendanceMark.objects.create(
                        school=school, session=session, student=student, status="ABSENT"
                    )

            # ---- قياس الاعتماد بأحجام تغطية مختلفة ----
            for size in options["periods"]:
                needed_days = -(-size // per_day)
                targets = [{"attendance_date": d} for d in days[:needed_days]]
                excuse = create_excuse(
                    school=school, membership=membership, student=student,
                    reason_type="MEDICAL_REPORT", notes="", targets=targets,
                )
                plan = resolve_coverage_plan(excuse)
                covered = len(plan["covered"])
                timed(
                    f"preview ({covered} covered periods)",
                    lambda e=excuse: resolve_coverage_plan(e),
                )
                # الاعتماد مرة واحدة فعليًا (ليس RUNS) — عملية غير idempotent للقياس
                with CaptureQueriesContext(connection) as ctx:
                    t0 = time_module.perf_counter()
                    approve_excuse(
                        excuse_id=excuse.id, school=school, membership=membership,
                        preview_hash=plan["preview_hash"],
                    )
                    elapsed = (time_module.perf_counter() - t0) * 1000
                self.stdout.write(
                    f"{f'approve ({covered} periods)':<34} | "
                    f"   {elapsed:8.1f}ms | queries={len(ctx.captured_queries)}"
                )
                # تنظيف حتى لا يتداخل القياس التالي مع تغطيات سابقة
                excuse.coverages.all().delete()
                excuse.targets.all().delete()
                excuse.delete()

            # ---- قياس القوائم ----
            from excuses.models import AbsenceExcuseTarget

            for size in options["list_sizes"]:
                AbsenceExcuse.objects.filter(school=school).delete()
                bulk = AbsenceExcuse.objects.bulk_create(
                    AbsenceExcuse(
                        school=school, student=students[i % 2],
                        status=AbsenceExcuseStatus.PENDING,
                        reason_type="FAMILY", notes="",
                        recorded_by_membership=membership,
                        recorded_at=datetime.now().astimezone(),
                    )
                    for i in range(size)
                )
                AbsenceExcuseTarget.objects.bulk_create(
                    AbsenceExcuseTarget(
                        school=school, excuse=excuse_row,
                        attendance_date=base_day, period_sequence=None,
                    )
                    for excuse_row in bulk
                )

                from django.db.models import Count, Max, Min, Q

                from excuses.models import ExcuseCoverageStatus

                def page(size=size):
                    queryset = (
                        AbsenceExcuse.objects.filter(school=school)
                        .select_related(
                            "student",
                            "recorded_by_membership__staff_profile",
                            "recorded_by_membership__user",
                            "approved_by_membership__staff_profile",
                            "approved_by_membership__user",
                        )
                        .prefetch_related(
                            "student__enrollments__grade", "student__enrollments__section"
                        )
                        .annotate(
                            targets_count=Count("targets", distinct=True),
                            active_coverage_count=Count(
                                "coverages",
                                filter=Q(coverages__status=ExcuseCoverageStatus.ACTIVE),
                                distinct=True,
                            ),
                            attachments_count=Count("attachments", distinct=True),
                            date_from=Min("targets__attendance_date"),
                            date_to=Max("targets__attendance_date"),
                        )
                        .order_by("-recorded_at", "-id")[:25]
                    )
                    return [serialize_excuse_row(row) for row in queryset]

                timed(f"list page of 25 (total={size})", page)

            # ---- قياس التفاصيل ----
            detail_excuse = create_excuse(
                school=school, membership=membership, student=student,
                reason_type="MEDICAL_REPORT", notes="",
                targets=[{"attendance_date": d} for d in days],
            )
            detail_plan = resolve_coverage_plan(detail_excuse)
            approve_excuse(
                excuse_id=detail_excuse.id, school=school, membership=membership,
                preview_hash=detail_plan["preview_hash"],
            )
            covered_total = detail_excuse.coverages.count()

            def detail():
                loaded = (
                    AbsenceExcuse.objects.filter(id=detail_excuse.id)
                    .select_related(
                        "student",
                        "recorded_by_membership__staff_profile",
                        "recorded_by_membership__user",
                        "approved_by_membership__staff_profile",
                        "approved_by_membership__user",
                        "rejected_by_membership__staff_profile",
                        "rejected_by_membership__user",
                        "cancelled_by_membership__staff_profile",
                        "cancelled_by_membership__user",
                    )
                    .prefetch_related(
                        "targets", "coverages",
                        "attachments__uploaded_by_membership__staff_profile",
                        "attachments__uploaded_by_membership__user",
                        "student__enrollments__grade",
                        "student__enrollments__section",
                    )
                    .first()
                )
                return serialize_excuse_detail(loaded)

            timed(f"detail ({covered_total} coverages)", detail)
        finally:
            from attendance.models import (
                AttendanceDayContext,
                DailyAttendanceSummary,
            )
            from audit.models import AuditLog
            from excuses.models import (
                AbsenceExcuseCoverage,
            )
            from excuses.models import (
                AbsenceExcuseTarget as Target,
            )
            from students.models import Student, StudentEnrollment

            AuditLog.objects.filter(school=school).delete()  # PROTECT على school
            AbsenceExcuseCoverage.objects.filter(school=school).delete()
            Target.objects.filter(school=school).delete()
            AbsenceExcuse.objects.filter(school=school).delete()
            AttendanceMark.objects.filter(school=school).delete()
            DailyAttendanceSummary.objects.filter(school=school).delete()
            AttendanceSession.objects.filter(school=school).delete()
            AttendanceDayContext.objects.filter(school=school).delete()
            StudentEnrollment.objects.filter(school=school).delete()
            Student.objects.filter(school=school).delete()
            Section.objects.filter(school=school).delete()
            Grade.objects.filter(school=school).delete()
            BellPeriod.objects.filter(school=school).delete()
            SchoolWeekDay.objects.filter(school=school).delete()
            BellSchedule.objects.filter(school=school).delete()
            AcademicYear.objects.filter(school=school).delete()
            SchoolMembershipRole.objects.filter(membership=membership).delete()
            SchoolMembership.objects.filter(school=school).delete()
            school.delete()
            User.objects.filter(pk=user.pk).delete()  # الجوال يخزن منسقًا (+966…)
            self.stdout.write(self.style.SUCCESS("benchmark data cleaned."))
