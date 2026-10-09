"""Fresh three-viewport families inside the existing exact local synthetic stack."""

import json
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction

from common.security.identifiers import (
    encrypt_national_id,
    mask_national_id,
    national_id_lookup_hash,
)
from common.tenant_rls import tenant_context
from school_sms.models import SchoolSmsIntegration
from school_sms.security import encrypt_secret
from schools.models import School
from students.models import Section, Student, StudentEnrollment


class Command(BaseCommand):
    help = "Create private invitation test families; fake SMS only, no external send."

    def add_arguments(self, parser):
        parser.add_argument("--password", required=True)
        parser.add_argument("--output", required=True)

    @transaction.atomic
    def handle(self, *args, **options):
        # This existing command rejects every DB/profile outside the isolated owner stack.
        call_command("seed_parent_staging", password=options["password"], output=options["output"])
        output = Path(options["output"])
        fixture = json.loads(output.read_text(encoding="utf-8"))
        school = School.objects.get(pk=fixture["schools"][0]["id"])
        families = []
        with tenant_context(school_id=school.id):
            enrollment = (
                StudentEnrollment.objects.filter(school=school)
                .select_related("academic_year", "grade")
                .first()
            )
            section = Section.objects.create(
                school=school,
                grade=enrollment.grade,
                name="فصل دعوات الأسرة الصناعي",
                code="FAMILY-INVITE",
            )
            SchoolSmsIntegration.objects.create(
                school=school,
                provider="DREAMS",
                username="SYNTHETIC-NO-EXTERNAL-SEND",
                sender_name="Synthetic",
                secret_encrypted=encrypt_secret("FAKE-NOT-A-PROVIDER-KEY"),
                is_active=True,
            )
            for i, viewport in enumerate(("desktop", "tablet", "mobile")):
                # Distinct from earlier fixtures. These numbers are never sent externally.
                mobile = f"+96659988{school.id % 1000:03d}{i}"
                name = f"ولي أسرة الدعوة الصناعية {viewport}"
                children = []
                for j in range(3):
                    identifier = f"FAMILY-{fixture['run']}-{i}-{j}"
                    student = Student.objects.create(
                        school=school,
                        full_name=f"ابن الدعوة الصناعية {viewport} {j + 1}",
                        guardian_mobile=mobile,
                        guardian_name=name,
                        national_id_encrypted=encrypt_national_id(identifier),
                        national_id_lookup_hash=national_id_lookup_hash(identifier),
                        national_id_masked=mask_national_id(identifier),
                    )
                    StudentEnrollment.objects.create(
                        school=school,
                        student=student,
                        academic_year=enrollment.academic_year,
                        grade=enrollment.grade,
                        section=section,
                        enrolled_at=enrollment.academic_year.start_date,
                    )
                    children.append({"id": student.id, "name": student.full_name})
                families.append(
                    {
                        "viewport": viewport,
                        "name": name,
                        "mobile": mobile,
                        "email": f"family-{fixture['run']}-{viewport}@parent.invalid",
                        "children": children,
                    }
                )
        fixture["family_invitations"] = families
        output.write_text(json.dumps(fixture, ensure_ascii=False, indent=2), encoding="utf-8")
        self.stdout.write(
            self.style.SUCCESS("Synthetic family invitations prepared; fake provider only")
        )
