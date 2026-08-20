"""قياس أداء الإحالات (تطوير فقط): القائمة، صندوق الوارد، التفاصيل، كشف التكرار.

الهدف الأول إثبات **ثبات عدد الاستعلامات** مع الحجم (لا N+1)، لا السرعة المطلقة.
"""

import statistics
import time as time_module
from datetime import date

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone as dj_timezone

from accounts.models import User
from memberships.models import SchoolMembership, SchoolMembershipRole, SchoolRole
from schools.models import School

RUNS = 3
SLUG = "ref-benchmark"
MOBILE_SUFFIX = "1117777"


def _purge_previous() -> None:
    from audit.models import AuditLog
    from referrals.models import (
        StudentReferral,
        StudentReferralContribution,
        StudentReferralEvent,
    )
    from students.models import Grade, Section, Student, StudentEnrollment

    school = School.objects.filter(slug=SLUG).first()
    if school is not None:
        AuditLog.objects.filter(school=school).delete()
        StudentReferralEvent.objects.filter(school=school).delete()
        StudentReferralContribution.objects.filter(school=school).delete()
        StudentReferral.objects.filter(school=school).delete()
        StudentEnrollment.objects.filter(school=school).delete()
        Student.objects.filter(school=school).delete()
        Section.objects.filter(school=school).delete()
        Grade.objects.filter(school=school).delete()
        from academics.models import AcademicYear

        AcademicYear.objects.filter(school=school).delete()
        SchoolMembershipRole.objects.filter(membership__school=school).delete()
        SchoolMembership.objects.filter(school=school).delete()
        school.delete()
    User.objects.filter(mobile__endswith=MOBILE_SUFFIX).delete()


class Command(BaseCommand):
    help = "قياس قوائم الإحالات وكشف التكرار (DEBUG فقط)"

    def add_arguments(self, parser):
        parser.add_argument("--sizes", nargs="+", type=int, default=[100, 1000, 5000])
        parser.add_argument("--history", nargs="+", type=int, default=[1, 10, 50])

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("benchmark_referrals يعمل في التطوير فقط.")

        from academics.models import AcademicYear, AcademicYearStatus
        from referrals.api.serializers import (
            serialize_referral_detail,
            serialize_referral_row,
        )
        from referrals.models import (
            ReferralCategory,
            ReferralReason,
            ReferralStatus,
            StudentReferral,
        )
        from referrals.selectors import referral_kpis, visible_referrals
        from referrals.services.referrals import find_open_duplicate
        from students.models import Grade, Section
        from tests.attendance_helpers import make_students

        _purge_previous()
        school = School.objects.create(name="مدرسة قياس الإحالات", slug=SLUG)
        user = User.objects.create_user(
            mobile="0551117777", password="Bench-123456"  # noqa: S106 — بيانات قياس مؤقتة
        )
        membership = SchoolMembership.objects.create(user=user, school=school)
        SchoolMembershipRole.objects.create(
            membership=membership, role=SchoolRole.SCHOOL_MANAGER
        )
        counselor_user = User.objects.create_user(
            mobile="0551117778", password="Bench-123456"  # noqa: S106
        )
        counselor = SchoolMembership.objects.create(user=counselor_user, school=school)
        SchoolMembershipRole.objects.create(
            membership=counselor, role=SchoolRole.COUNSELOR
        )

        def timed(label, fn):
            durations, queries = [], 0
            for _ in range(RUNS):
                with CaptureQueriesContext(connection) as ctx:
                    start = time_module.perf_counter()
                    fn()
                    durations.append((time_module.perf_counter() - start) * 1000)
                queries = len(ctx.captured_queries)
            self.stdout.write(
                f"{label:<40} | p50={statistics.median(durations):8.1f}ms | queries={queries}"
            )

        try:
            year = AcademicYear.objects.create(
                school=school, name="قياس", start_date=date(2025, 9, 1),
                end_date=date(2026, 8, 30), status=AcademicYearStatus.ACTIVE,
            )
            grade = Grade.objects.create(school=school, name="قياس", code="B", sequence=1)
            section = Section.objects.create(school=school, grade=grade, code="r", name="r")
            students = make_students(school, section, year, 20, prefix="77000")

            for size in options["sizes"]:
                StudentReferral.objects.filter(school=school).delete()
                StudentReferral.objects.bulk_create(
                    StudentReferral(
                        school=school,
                        student=students[i % len(students)],
                        source_type="TEACHER",
                        category=ReferralCategory.ACADEMIC,
                        reason_code=ReferralReason.ACADEMIC_WEAKNESS,
                        description="قياس",
                        created_by_membership=membership,
                        assigned_counselor_membership=counselor if i % 2 else None,
                        status=(
                            ReferralStatus.NEW if i % 3 else ReferralStatus.ACKNOWLEDGED
                        ),
                        snapshot_data={"student_name": "قياس"},
                        accepted_at=None,
                    )
                    for i in range(size)
                )

                def page(_size=size):
                    queryset = visible_referrals(
                        school=school, membership=membership, roles=["SCHOOL_MANAGER"]
                    ).order_by("-created_at", "-id")[:25]
                    return [serialize_referral_row(row) for row in queryset]

                timed(f"list page of 25 (total={size})", page)
                timed(
                    f"counselor inbox page (total={size})",
                    lambda _s=size: [
                        serialize_referral_row(row)
                        for row in visible_referrals(
                            school=school, membership=counselor, roles=["COUNSELOR"]
                        ).order_by("-created_at", "-id")[:25]
                    ],
                )
                timed(
                    f"kpis (total={size})",
                    lambda _s=size: referral_kpis(
                        school=school, membership=membership, roles=["SCHOOL_MANAGER"]
                    ),
                )

            # كشف التكرار مقابل تاريخ طالب متضخم
            student = students[0]
            for history in options["history"]:
                StudentReferral.objects.filter(school=school, student=student).delete()
                StudentReferral.objects.bulk_create(
                    StudentReferral(
                        school=school, student=student, source_type="TEACHER",
                        category=ReferralCategory.ACADEMIC,
                        reason_code=ReferralReason.ACADEMIC_WEAKNESS,
                        description="سابقة", created_by_membership=membership,
                        status=ReferralStatus.CLOSED,
                        closed_at=dj_timezone.now(), snapshot_data={},
                    )
                    for _ in range(history)
                )
                timed(
                    f"duplicate check (history={history})",
                    lambda _h=history: find_open_duplicate(
                        school=school,
                        student=student,
                        category=ReferralCategory.ACADEMIC,
                    ),
                )

            # التفاصيل مع ملاحظات وأحداث
            detail = StudentReferral.objects.filter(school=school).first()

            def load_detail():
                loaded = (
                    StudentReferral.objects.filter(id=detail.id)
                    .select_related(
                        "student",
                        "source_warning",
                        "created_by_membership__user",
                        "created_by_membership__staff_profile",
                        "assigned_counselor_membership__user",
                        "assigned_counselor_membership__staff_profile",
                        "closed_by_membership__user",
                        "closed_by_membership__staff_profile",
                    )
                    .prefetch_related(
                        "contributions__created_by_membership__user",
                        "contributions__created_by_membership__staff_profile",
                        "events__actor_membership__user",
                        "events__actor_membership__staff_profile",
                        "student__enrollments__grade",
                        "student__enrollments__section",
                    )
                    .first()
                )
                return serialize_referral_detail(loaded)

            timed("referral detail", load_detail)
        finally:
            _purge_previous()
            self.stdout.write(self.style.SUCCESS("benchmark data cleaned."))
