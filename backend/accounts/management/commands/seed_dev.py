"""Dev Seed — بيئة التطوير فقط، يرفض العمل عند DEBUG=False.

لا أسرار ثابتة: كلمة المرور تمرر عبر --password إلزاميًا.
الاستخدام:
    python manage.py seed_dev --password "كلمة-مرور-التطوير"
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import User
from memberships.models import SchoolMembership, SchoolMembershipRole, SchoolRole
from schools.models import School

SEED = [
    # (mobile, first, last, [(school_slug, [roles]), ...])
    (
        "0550000001",
        "أحمد",
        "المعلم",
        [("school-a", ["TEACHER"]), ("school-b", ["TEACHER", "COUNSELOR"])],
    ),
    # مدير في A ومعلم في B — سيناريو E2E للصلاحيات متعددة المدارس
    ("0550000002", "خالد", "المدير", [("school-a", ["SCHOOL_MANAGER"]), ("school-b", ["TEACHER"])]),
    ("0550000003", "سعد", "الوكيل", [("school-a", ["VICE_PRINCIPAL"])]),
    ("0550000004", "فهد", "المرشد", [("school-c", ["COUNSELOR"])]),
    # مرشدة في A (م13): مرشدو البذر كانوا في B وC فقط بينما بيانات الاختبارات
    # كلها في A — فلا يمكن إثبات «معلم يحيل ← مرشد يستلم» بمستخدمين مختلفين
    ("0550000005", "ليان", "المرشدة", [("school-a", ["COUNSELOR"])]),
    # مديرة B وC — لسيناريوهات استيراد الموظفين متعددة المدارس
    ("0550000006", "منى", "المديرة", [
        ("school-b", ["SCHOOL_MANAGER"]),
        ("school-c", ["SCHOOL_MANAGER"]),
    ]),
]

SCHOOLS = [
    ("ثانوية الأندلس", "school-a"),
    ("مدارس الرواد", "school-b"),
    ("ثانوية المستقبل", "school-c"),
]


class Command(BaseCommand):
    help = "إنشاء بيانات تطوير: 3 مدارس و4 مستخدمين بأدوار متعددة (DEBUG فقط)"

    def add_arguments(self, parser):
        parser.add_argument("--password", required=True, help="كلمة مرور كل حسابات الـ seed")

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("seed_dev يعمل في بيئة التطوير فقط (DEBUG=True).")

        from datetime import date

        from academics.models import AcademicYear, AcademicYearStatus

        password = options["password"]
        schools: dict[str, School] = {}
        for name, slug in SCHOOLS:
            school, _ = School.objects.get_or_create(slug=slug, defaults={"name": name})
            schools[slug] = school
            # عام دراسي نشط لكل مدرسة (يلزم للاستيراد) — idempotent
            active_year = AcademicYear.objects.filter(
                school=school, status=AcademicYearStatus.ACTIVE
            ).first()
            if active_year is None:
                AcademicYear.objects.create(
                    school=school, name="2026/2027",
                    start_date=date(2026, 8, 1), end_date=date(2027, 6, 25),
                    status=AcademicYearStatus.ACTIVE,
                )
            elif active_year.start_date > date.today():
                # اتساق بيئة التطوير: عام «نشط» لم يبدأ بعد يجعل كل المقاييس
                # المرتبطة بنطاق تواريخ العام (كالتأخر الصباحي) فارغة
                active_year.start_date = date(2026, 8, 1)
                active_year.save(update_fields=["start_date"])
            self._seed_all_day_schedule(school)
            self.stdout.write(f"school: {school.name} (id={school.id}, slug={slug})")

        for mobile, first, last, assignments in SEED:
            user = User.objects.filter(mobile__endswith=mobile[1:]).first()
            if user is None:
                user = User.objects.create_user(
                    mobile=mobile, password=password, first_name=first, last_name=last
                )
            for slug, roles in assignments:
                membership, _ = SchoolMembership.objects.get_or_create(
                    user=user, school=schools[slug]
                )
                for role in roles:
                    SchoolMembershipRole.objects.get_or_create(
                        membership=membership, role=SchoolRole(role)
                    )
            self.stdout.write(f"user: {user.display_name} ({user.mobile}) id={user.id}")

        self.stdout.write(self.style.SUCCESS("Seed completed."))

    def _seed_all_day_schedule(self, school):
        """جدول تطويري يغطي اليوم كاملًا كل أيام الأسبوع — حتمية E2E في أي وقت تشغيل."""
        from datetime import time

        from academics.models import BellPeriod, BellSchedule, SchoolWeekDay, Weekday

        # 24 حصة × ساعة: أقصى مسافة عن بداية الحصة 60 دقيقة < حد المهلة 120 —
        # فاختبارات E2E تستطيع دائمًا جعل الفصل «في الوقت» أو «متأخرًا» عبر الإعداد
        schedule, created = BellSchedule.objects.get_or_create(
            school=school, name="جدول التطوير (24 حصة)"
        )
        if created:
            for i in range(24):
                BellPeriod.objects.create(
                    school=school,
                    bell_schedule=schedule,
                    sequence=i + 1,
                    name=f"الحصة {i + 1}",
                    start_time=time(i, 0),
                    end_time=time(i, 59, 59),
                )
        for weekday in Weekday.values:
            SchoolWeekDay.objects.update_or_create(
                school=school,
                weekday=weekday,
                defaults={"is_school_day": True, "bell_schedule": schedule},
            )
