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
            if not AcademicYear.objects.filter(
                school=school, status=AcademicYearStatus.ACTIVE
            ).exists():
                AcademicYear.objects.create(
                    school=school, name="2026/2027",
                    start_date=date(2026, 8, 23), end_date=date(2027, 6, 25),
                    status=AcademicYearStatus.ACTIVE,
                )
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
