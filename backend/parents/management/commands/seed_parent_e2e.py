"""Create isolated, synthetic localhost fixtures; never send SMS or reset real schools."""

import json
import os
import uuid
from datetime import time, timedelta
from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from academics.models import AcademicYear, BellPeriod, BellSchedule, SchoolWeekDay, Weekday
from accounts.models import User
from attendance.services.sessions import start_session, submit_session
from common.security.identifiers import (
    encrypt_national_id,
    mask_national_id,
    national_id_lookup_hash,
)
from common.tenant_rls import tenant_context
from devices.models import SchoolArrival
from documents.models import GeneratedDocument
from memberships.models import SchoolMembership, SchoolMembershipRole
from parents.models import (
    GuardianActivation,
    GuardianRegistrationRequest,
    GuardianStudentRelation,
    ParentRegistrationConfig,
)
from parents.security import token_hash
from parents.services import decide_registration, submit_registration
from schools.models import School, SchoolSettings
from student_warnings.models import StudentWarning
from students.models import Grade, Section, Student, StudentEnrollment


def fixture_pdf():
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 180] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    stream = b"BT /F1 14 Tf 24 120 Td (Synthetic parent portal fixture) Tj ET"
    objects.append(
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"
    )
    content = b"%PDF-1.4\n"
    positions = []
    for number, obj in enumerate(objects, 1):
        positions.append(len(content))
        content += str(number).encode() + b" 0 obj\n" + obj + b"\nendobj\n"
    start = len(content)
    content += b"xref\n0 6\n0000000000 65535 f \n"
    content += b"".join(f"{position:010d} 00000 n \n".encode() for position in positions)
    content += (
        b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n" + str(start).encode() + b"\n%%EOF\n"
    )
    return content


class Command(BaseCommand):
    help = "Create new synthetic parent-e2e schools/users on a DEBUG localhost database."

    def add_arguments(self, parser):
        parser.add_argument("--password", required=True)
        parser.add_argument("--output", required=True)
        parser.add_argument(
            "--enable-registration",
            action="store_true",
            help="Enable registration only in the three newly created synthetic schools.",
        )
        parser.add_argument(
            "--expire-session-for",
            help="Expire only an account recorded in this synthetic fixture.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        database_host = str(settings.DATABASES["default"].get("HOST", ""))
        local_verification = (
            os.environ.get("PARENT_VERIFICATION_LOCAL_ONLY") == "1"
            and database_host == "postgres"
            and settings.DATABASES["default"].get("NAME") == "parent_verification"
            and settings.DATABASES["default"].get("USER") == "parent_verify_owner"
        )
        if not settings.DEBUG or (
            database_host not in {"localhost", "127.0.0.1", "::1"} and not local_verification
        ):
            raise CommandError("Parent fixtures require DEBUG=True and a localhost database.")
        if options.get("expire_session_for"):
            if not local_verification:
                raise CommandError(
                    "Session expiry requires the explicitly isolated verification stack."
                )
            from django.contrib.sessions.models import Session

            fixture = json.loads(Path(options["output"]).read_text(encoding="utf-8"))
            mobile = options["expire_session_for"]
            allowed = {fixture["parent_mobile"], fixture["employee"]["mobile"]}
            if (
                mobile not in allowed
                or not School.objects.filter(slug=f"parent-e2e-a-{fixture['run']}").exists()
            ):
                raise CommandError(
                    "Session expiry is restricted to this synthetic fixture's accounts."
                )
            user = User.objects.get(mobile=mobile)
            with tenant_context(user_id=user.id):
                synthetic_relations = list(
                    GuardianStudentRelation.objects.filter(user=user).values_list(
                        "school_id", flat=True
                    )
                )
            if (
                not mobile.startswith("+966551800")
                or not School.objects.filter(
                    id__in=synthetic_relations,
                    slug__in=[
                        f"parent-e2e-{letter}-{fixture['run']}" for letter in ("a", "b", "c")
                    ],
                ).exists()
            ):
                raise CommandError(
                    "Only an activated synthetic fixture account can expire sessions."
                )
            session_keys = [
                session.session_key
                for session in Session.objects.filter(expire_date__gt=timezone.now())
                if session.get_decoded().get("_auth_user_id") == str(user.id)
            ]
            deleted, _ = Session.objects.filter(session_key__in=session_keys).delete()
            self.stdout.write(self.style.SUCCESS(f"Expired {deleted} synthetic account sessions."))
            return
        run = uuid.uuid4().hex[:8]
        slot = next(
            (
                slot
                for slot in range(10, 990, 10)
                if not User.objects.filter(
                    mobile__in=[
                        f"+966551800{slot + offset:03d}" for offset in (1, 2, 3, 6, 7, 8, 9)
                    ]
                ).exists()
            ),
            None,
        )
        if slot is None:
            raise CommandError("No unused synthetic fixture mobile block remains.")
        password = options["password"]
        parent_mobile = f"+966551800{slot + 9:03d}"
        employee = User.objects.create_user(
            mobile=f"+966551800{slot + 8:03d}",
            password=password,
            first_name="معلم",
            last_name="ولي اختبار الأسرة",
        )
        now = timezone.localtime(timezone.now())
        from zoneinfo import ZoneInfo

        local = now.astimezone(ZoneInfo("Asia/Riyadh"))
        today = local.date()
        fixture = {
            "run": run,
            "date": today.isoformat(),
            "parent_mobile": parent_mobile,
            "rejected_mobile": f"+966551800{slot + 7:03d}",
            "employee": {"id": employee.id, "mobile": employee.mobile},
            "schools": [],
            "registration_enabled": bool(options["enable_registration"]),
        }
        for index, letter in enumerate(("a", "b", "c"), 1):
            school = School.objects.create(
                name=f"مدرسة اختبار بوابة الأسرة {letter.upper()}",
                slug=f"parent-e2e-{letter}-{run}",
            )
            with tenant_context(school_id=school.id):
                SchoolSettings.objects.create(school=school, timezone="Asia/Riyadh")
                year = AcademicYear.objects.create(
                    school=school,
                    name="عام اختبار الأسرة",
                    start_date=today - timedelta(days=90),
                    end_date=today + timedelta(days=180),
                    status="ACTIVE",
                )
                grade = Grade.objects.create(
                    school=school, name="الأول الثانوي", code="PARENT_E2E", sequence=1
                )
                section = Section.objects.create(
                    school=school, grade=grade, name="1", code="PARENT_E2E", department="علمي"
                )
                identifier = f"P{slot:03d}{index}180"
                student = Student.objects.create(
                    school=school,
                    full_name=("أحمد اختبار الأسرة", "خالد اختبار الأسرة", "سارة اختبار الأسرة")[
                        index - 1
                    ],
                    national_id_encrypted=encrypt_national_id(identifier),
                    national_id_lookup_hash=national_id_lookup_hash(identifier),
                    national_id_masked=mask_national_id(identifier),
                    guardian_name="ولي اختبار الأسرة",
                    guardian_mobile=parent_mobile,
                )
                StudentEnrollment.objects.create(
                    school=school,
                    student=student,
                    academic_year=year,
                    grade=grade,
                    section=section,
                    enrolled_at=year.start_date,
                )
                user = User.objects.create_user(
                    mobile=f"+966551800{slot + index:03d}",
                    password=password,
                    first_name="مدير",
                    last_name=f"اختبار الأسرة {letter.upper()}",
                )
                membership = SchoolMembership.objects.create(
                    school=school, user=user, status="ACTIVE"
                )
                for role in ("SCHOOL_MANAGER", "TEACHER"):
                    SchoolMembershipRole.objects.create(membership=membership, role=role)
                # The isolated expired-link fixture needs the registration service.
                # Disable the newly created school's config before this transaction
                # commits unless the caller explicitly requests browser acceptance.
                registration = ParentRegistrationConfig.objects.create(school=school, enabled=True)
                schedule = BellSchedule.objects.create(school=school, name="جدول اختبار الأسرة")
                for sequence in (1, 2):
                    BellPeriod.objects.create(
                        school=school,
                        bell_schedule=schedule,
                        sequence=sequence,
                        name=f"الحصة {sequence}",
                        start_time=time(0, (sequence - 1) * 15),
                        end_time=time(0, sequence * 15),
                    )
                for weekday in Weekday.values:
                    SchoolWeekDay.objects.create(
                        school=school, weekday=weekday, is_school_day=True, bell_schedule=schedule
                    )
                entry = {
                    "id": school.id,
                    "name": school.name,
                    "student_id": student.id,
                    "student_name": student.full_name,
                    "identifier": identifier,
                    "staff_mobile": user.mobile,
                    "registration_path": f"/parent/register/{registration.token}",
                    "section_id": section.id,
                }
                if index == 1:
                    employee_membership = SchoolMembership.objects.create(
                        school=school, user=employee, status="ACTIVE"
                    )
                    SchoolMembershipRole.objects.create(
                        membership=employee_membership, role="TEACHER"
                    )
                    employee_identifier = f"E{slot:03d}1180"
                    employee_student = Student.objects.create(
                        school=school,
                        full_name="ابن المعلم اختبار الأسرة",
                        national_id_encrypted=encrypt_national_id(employee_identifier),
                        national_id_lookup_hash=national_id_lookup_hash(employee_identifier),
                        national_id_masked=mask_national_id(employee_identifier),
                        guardian_name=employee.get_full_name(),
                        guardian_mobile=employee.mobile,
                    )
                    StudentEnrollment.objects.create(
                        school=school,
                        student=employee_student,
                        academic_year=year,
                        grade=grade,
                        section=section,
                        enrolled_at=year.start_date,
                    )
                    fixture["employee"].update(
                        student_id=employee_student.id,
                        student_name=employee_student.full_name,
                        identifier=employee_identifier,
                        membership_id=employee_membership.id,
                        school_id=school.id,
                    )
                    # Reuse production services and roster snapshots for actual submission.
                    draft, _, _ = start_session(
                        school=school,
                        membership=membership,
                        section=section,
                        attendance_date=today,
                        period_sequence=1,
                    )
                    submitted, _, _ = start_session(
                        school=school,
                        membership=membership,
                        section=section,
                        attendance_date=today,
                        period_sequence=2,
                    )
                    submit_session(
                        session_id=submitted.id,
                        school=school,
                        membership=membership,
                        marks=[{"student_id": student.id, "status": "ABSENT"}],
                    )
                    SchoolArrival.objects.create(
                        school=school,
                        student=student,
                        attendance_date=today,
                        first_arrival_at=local,
                        raw_late_minutes=12,
                        counted_late_minutes=7,
                        status="LATE",
                        source="MANUAL",
                        recorded_by_membership=membership,
                    )
                    warning = StudentWarning.objects.create(
                        school=school,
                        student=student,
                        academic_year=year,
                        warning_type="MORNING_LATE_OCCURRENCES",
                        level="LEVEL_1",
                        threshold_at_issue=1,
                        metric_value_at_issue=1,
                        student_name_snapshot=student.full_name,
                        grade_name_snapshot=grade.name,
                        section_name_snapshot=section.name,
                        morning_late_occurrences_at_issue=1,
                        morning_late_minutes_at_issue=7,
                        issued_by_membership=membership,
                        issued_at=timezone.now(),
                    )
                    document = GeneratedDocument.objects.create(
                        school=school,
                        student=student,
                        warning=warning,
                        document_type="WARNING_LEVEL_1",
                        template_key="parent-e2e",
                        template_version="1",
                        status="PENDING",
                        mime_type="application/pdf",
                        generated_by_membership=membership,
                        generated_at=timezone.now(),
                    )
                    pdf = fixture_pdf()
                    import hashlib

                    document.file.save("parent-e2e.pdf", ContentFile(pdf), save=False)
                    document.size_bytes = len(pdf)
                    document.checksum = hashlib.sha256(pdf).hexdigest()
                    document.status = "READY"
                    document.save()
                    employee_document = GeneratedDocument.objects.create(
                        school=school,
                        student=employee_student,
                        document_type="STUDENT_ATTENDANCE_REPORT",
                        template_key="parent-e2e",
                        template_version="1",
                        status="PENDING",
                        mime_type="application/pdf",
                        generated_by_membership=membership,
                        generated_at=timezone.now(),
                    )
                    employee_document.file.save(
                        "parent-e2e-employee.pdf", ContentFile(pdf), save=False
                    )
                    employee_document.size_bytes = len(pdf)
                    employee_document.checksum = hashlib.sha256(pdf).hexdigest()
                    employee_document.status = "READY"
                    employee_document.save()
                    fixture["employee"]["document_id"] = employee_document.id
                    entry.update(
                        draft_session_id=draft.id,
                        absent_session_id=submitted.id,
                        warning_id=warning.id,
                        document_id=document.id,
                    )
                elif index == 2:
                    submitted, _, _ = start_session(
                        school=school,
                        membership=membership,
                        section=section,
                        attendance_date=today,
                        period_sequence=1,
                    )
                    submit_session(
                        session_id=submitted.id,
                        school=school,
                        membership=membership,
                        marks=[{"student_id": student.id, "status": "ABSENT"}],
                    )
                    entry["absent_session_id"] = submitted.id
                fixture["schools"].append(entry)
                if index == 3:
                    expired_mobile = f"+966551800{slot + 6:03d}"
                    expired_identifier = f"X{slot:03d}3180"
                    expired_student = Student.objects.create(
                        school=school,
                        full_name="طالب رابط التفعيل المنتهي الاصطناعي",
                        national_id_encrypted=encrypt_national_id(expired_identifier),
                        national_id_lookup_hash=national_id_lookup_hash(expired_identifier),
                        national_id_masked=mask_national_id(expired_identifier),
                        guardian_name="ولي رابط اختبار منتهي",
                        guardian_mobile=expired_mobile,
                    )
                    StudentEnrollment.objects.create(
                        school=school,
                        student=expired_student,
                        academic_year=year,
                        grade=grade,
                        section=section,
                        enrolled_at=year.start_date,
                    )
                    expired_receipt = submit_registration(
                        school=school,
                        data={
                            "name": "ولي رابط اختبار منتهي",
                            "mobile": expired_mobile,
                            "student_identifier": expired_identifier,
                            "relationship_type": "GUARDIAN",
                        },
                    )
                    expired_request = GuardianRegistrationRequest.objects.get(
                        receipt_hash=token_hash(expired_receipt["receipt_token"])
                    )
                    expired_decision = decide_registration(
                        school=school,
                        membership=membership,
                        request_id=expired_request.id,
                        data={
                            "decision": "APPROVE",
                            "student_id": expired_student.id,
                            "verification_note": "تحقق مستقل اصطناعي لاختبار انتهاء رابط التفعيل",
                            "decision_reason": "",
                            "contact_bound": True,
                            "delivery": "MANUAL",
                        },
                    )
                    GuardianActivation.objects.filter(request=expired_request).update(
                        expires_at=timezone.now() - timedelta(seconds=1)
                    )
                    fixture["expired_activation_url"] = expired_decision["activation_url"]
                if not options["enable_registration"]:
                    registration.enabled = False
                    registration.save(update_fields=["enabled", "updated_at"])
        output = Path(options["output"]).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(fixture, ensure_ascii=False, indent=2), encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(f"Synthetic parent fixtures created: {output}"))
