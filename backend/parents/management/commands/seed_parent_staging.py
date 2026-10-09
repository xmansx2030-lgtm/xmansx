"""Create only new synthetic schools and stateful acceptance fixtures; no SMS."""

import hashlib
import json
import os
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from academics.models import AcademicYear, Semester
from accounts.models import User
from attendance.services.day_context import get_or_refresh_pristine_day_context
from attendance.services.sessions import start_session, submit_session
from common.security.identifiers import (
    encrypt_national_id,
    mask_national_id,
    national_id_lookup_hash,
)
from common.tenant_rls import tenant_context
from counseling.models import CounselorCase
from devices.models import SchoolArrival
from documents.models import GeneratedDocument
from memberships.models import SchoolMembership, SchoolMembershipRole
from parents.management.commands.seed_parent_e2e import fixture_pdf
from parents.models import (
    GuardianRegistrationRequest,
    GuardianStudentRelation,
    ParentRegistrationConfig,
)
from parents.request_services import (
    decide_request,
    publish_family,
    submit_correction,
    submit_excuse,
)
from parents.security import encrypt_value, token_hash
from parents.services import complete_activation, decide_registration, submit_registration
from referrals.models import StudentReferral
from schools.models import School
from student_warnings.models import StudentWarning
from students.models import Section, Student, StudentEnrollment


def _verified_synthetic_email(user):
    """Explicit owner fixture proof for prebuilt request states, never a backfill."""
    from parents.email_recovery_models import AccountRecoveryEmail
    from parents.email_recovery_services import recovery_email_hash

    email = f"state-fixture-{user.pk}@parent.invalid"
    AccountRecoveryEmail.objects.create(
        user=user, current_email_encrypted=encrypt_value(email),
        current_email_hash=recovery_email_hash(email), verified_at=timezone.now(),
    )


class Command(BaseCommand):
    help = "Create a new isolated synthetic acceptance run; registrations are disabled by default."

    def add_arguments(self, parser):
        parser.add_argument("--password", required=True)
        parser.add_argument("--output", required=True)
        parser.add_argument("--enable-registration", action="store_true")

    @transaction.atomic
    def handle(self, *args, **options):
        db = settings.DATABASES["default"]
        if not (
            settings.DEBUG
            and os.environ.get("PARENT_VERIFICATION_LOCAL_ONLY") == "1"
            and db.get("NAME") == "parent_verification"
            and db.get("HOST") == "postgres"
            and db.get("USER") == "parent_verify_owner"
        ):
            raise CommandError(
                "Staging fixtures require the exact isolated synthetic owner database"
            )
        output = Path(options["output"])
        call_command(
            "seed_parent_e2e",
            password=options["password"],
            output=str(output),
            enable_registration=options["enable_registration"],
            stdout=self.stdout,
        )
        fixture = json.loads(output.read_text(encoding="utf-8"))
        suffix = fixture["employee"]["mobile"][-3:]
        snapshot_parent = User.objects.create_user(
            mobile=f"+966551820{suffix}",
            password=options["password"],
            first_name="ولي حالات القبول الصناعية",
        )
        _verified_synthetic_email(snapshot_parent)
        today = date.fromisoformat(fixture["date"])
        fixture["acceptance"] = {"parent_mobile": snapshot_parent.mobile, "children": []}
        for index, school_data in enumerate(fixture["schools"], 1):
            school = School.objects.get(id=school_data["id"])
            with tenant_context(school_id=school.id):
                manager = SchoolMembership.objects.select_related("user").get(
                    school=school, user__mobile=school_data["staff_mobile"]
                )
                staff = {}
                for role_index, (role, title) in enumerate(
                    (("VICE_PRINCIPAL", "وكيل"), ("TEACHER", "معلم"), ("COUNSELOR", "مرشد")), 1
                ):
                    user = User.objects.create_user(
                        mobile=f"+966552{index}{role_index}{suffix}0",
                        password=options["password"],
                        first_name=title,
                        last_name="اختبار صناعي",
                    )
                    membership = SchoolMembership.objects.create(
                        school=school, user=user, status="ACTIVE"
                    )
                    SchoolMembershipRole.objects.create(membership=membership, role=role)
                    staff[role] = {"mobile": user.mobile, "membership_id": membership.id}
                school_data["acceptance_staff"] = staff
                original_section = Section.objects.get(id=school_data["section_id"], school=school)
                section = Section.objects.create(
                    school=school,
                    grade=original_section.grade,
                    name="قبول صناعي",
                    code="PARENT_STAGING_ACCEPTANCE",
                )
                year = AcademicYear.objects.get(school=school, status="ACTIVE")
                Semester.objects.create(
                    school=school, academic_year=year,
                    name="الفصل الصناعي للقبول", sequence=1,
                    start_date=year.start_date, end_date=year.end_date, status="ACTIVE",
                )
                identifier = f"S{fixture['run']}{index}"
                student = Student.objects.create(
                    school=school,
                    full_name=f"طالب حالات القبول الصناعية {index}",
                    national_id_encrypted=encrypt_national_id(identifier),
                    national_id_lookup_hash=national_id_lookup_hash(identifier),
                    national_id_masked=mask_national_id(identifier),
                    guardian_name=snapshot_parent.first_name,
                    guardian_mobile=snapshot_parent.mobile,
                )
                StudentEnrollment.objects.create(
                    school=school,
                    student=student,
                    academic_year=year,
                    grade=original_section.grade,
                    section=section,
                    enrolled_at=year.start_date,
                )
                config = ParentRegistrationConfig.objects.get(school=school)
                original_enabled = config.enabled
                config.enabled = True
                config.save(update_fields=["enabled", "updated_at"])
                receipt = submit_registration(
                    school=school,
                    data={
                        "name": snapshot_parent.first_name,
                        "mobile": snapshot_parent.mobile,
                        "email": f"state-fixture-{snapshot_parent.pk}@parent.invalid",
                        "student_identifier": identifier,
                        "relationship_type": "GUARDIAN",
                    },
                )
                registration = GuardianRegistrationRequest.objects.get(
                    school=school, receipt_hash=token_hash(receipt["receipt_token"])
                )
                approval = decide_registration(
                    school=school,
                    membership=manager,
                    request_id=registration.id,
                    data={
                        "decision": "APPROVE",
                        "student_id": student.id,
                        "verification_note": "إثبات صناعي مستقل خاص ببيئة القبول فقط",
                        "decision_reason": "",
                        "contact_bound": True,
                        "delivery": "MANUAL",
                    },
                )
                activation_token = parse_qs(urlparse(approval["activation_url"]).fragment)["token"][
                    0
                ]
                complete_activation(token=activation_token, user=snapshot_parent)
                relation = GuardianStudentRelation.objects.get(
                    school=school, student=student, user=snapshot_parent
                )
                config.enabled = original_enabled
                config.save(update_fields=["enabled", "updated_at"])
                child = {
                    "school_id": school.id,
                    "student_id": student.id,
                    "student_name": student.full_name,
                    "relation_id": relation.id,
                    "section_id": section.id,
                    "sessions": [],
                }
                if index == 3:
                    not_started_date = today + timedelta(days=1)
                    get_or_refresh_pristine_day_context(
                        school=school, attendance_date=not_started_date
                    )
                    child["not_started_date"] = not_started_date.isoformat()
                if index < 3:
                    for period in (1, 2):
                        session, _, _ = start_session(
                            school=school,
                            membership=manager,
                            section=section,
                            attendance_date=today,
                            period_sequence=period,
                        )
                        if index == 1 or period == 1:
                            submit_session(
                                session_id=session.id,
                                school=school,
                                membership=manager,
                                marks=[{"student_id": student.id, "status": "ABSENT"}],
                            )
                        child["sessions"].append({"id": session.id, "period_sequence": period})
                    SchoolArrival.objects.create(
                        school=school,
                        student=student,
                        attendance_date=today,
                        first_arrival_at=timezone.now(),
                        raw_late_minutes=12 if index == 1 else 0,
                        counted_late_minutes=7 if index == 1 else 0,
                        status="LATE" if index == 1 else "ON_TIME",
                        source="MANUAL",
                        recorded_by_membership=manager,
                    )
                    correction = submit_correction(
                        relation=relation,
                        user=snapshot_parent,
                        session_id=child["sessions"][1 if index == 1 else 0]["id"],
                        reason="طلب تصحيح صناعي يخضع للمراجعة ولا يغير حضور المعلم تلقائياً",
                    )
                    child["correction_id"] = correction.id
                if index == 1:
                    child["excuses"] = []
                    for period, decision in ((1, "APPROVED"), (2, "REJECTED")):
                        excuse = submit_excuse(
                            relation=relation,
                            user=snapshot_parent,
                            reason_type="MEDICAL_REPORT",
                            notes="سبب اصطناعي لرحلة قبول لا يحتوي بيانات شخصية",
                            targets=[{"attendance_date": today, "period_sequence": period}],
                        )
                        decide_request(
                            obj=excuse,
                            school=school,
                            membership=manager,
                            decision=decision,
                            note="قرار صناعي موثق لاختبار الخدمة الحالية",
                        )
                        child["excuses"].append({"id": excuse.id, "status": decision})
                    decide_request(
                        obj=correction,
                        school=school,
                        membership=manager,
                        decision="APPROVED",
                        note="تصحيح صناعي معتمد عبر الخدمة القائمة",
                    )
                    counselor = SchoolMembership.objects.get(id=staff["COUNSELOR"]["membership_id"])
                    referral = StudentReferral.objects.create(
                        school=school,
                        student=student,
                        source_type="SCHOOL_MANAGER",
                        category="OTHER",
                        reason_code="COUNSELOR_MEETING_REQUEST",
                        description="إحالة صناعية",
                        created_by_membership=manager,
                        assigned_counselor_membership=counselor,
                        status="ACKNOWLEDGED",
                    )
                    case = CounselorCase.objects.create(
                        school=school,
                        student=student,
                        primary_referral=referral,
                        assigned_counselor_membership=counselor,
                        opened_by_membership=manager,
                        opened_at=timezone.now(),
                        last_activity_at=timezone.now(),
                        summary="STAGING_INTERNAL_COUNSELOR_NOTE_MUST_NOT_LEAK",
                    )
                    publication = publish_family(
                        school=school,
                        membership=counselor,
                        student=student,
                        case=case,
                        title="إرشاد منشور للأسرة الصناعية",
                        body="محتوى تربوي منشور مستقل عن ملاحظات المرشد الداخلية",
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
                        grade_name_snapshot=original_section.grade.name,
                        section_name_snapshot=section.name,
                        morning_late_occurrences_at_issue=1,
                        morning_late_minutes_at_issue=7,
                        issued_by_membership=manager,
                        issued_at=timezone.now(),
                    )
                    document = GeneratedDocument.objects.create(
                        school=school,
                        student=student,
                        warning=warning,
                        document_type="WARNING_LEVEL_1",
                        template_key="parent-staging",
                        template_version="1",
                        status="PENDING",
                        mime_type="application/pdf",
                        generated_by_membership=manager,
                        generated_at=timezone.now(),
                    )
                    pdf = fixture_pdf()
                    document.file.save("synthetic-staging.pdf", ContentFile(pdf), save=False)
                    document.size_bytes = len(pdf)
                    document.checksum = hashlib.sha256(pdf).hexdigest()
                    document.status = "READY"
                    document.save()
                    file_publication = publish_family(
                        school=school,
                        membership=manager,
                        student=student,
                        document=document,
                        title="مستند صناعي منشور خاص",
                        body="مستند اصطناعي مخصص لاختبار الوصول المصرح فقط",
                    )
                    child.update(
                        warning_id=warning.id,
                        document_id=document.id,
                        publication_id=publication.id,
                        file_publication_id=file_publication.id,
                    )
                fixture["acceptance"]["children"].append(child)
                if index == 3:
                    # Independent of the employee subject suspended by the PWA
                    # scenario. Reuse this synthetic teacher's global account.
                    switch_user = User.objects.get(mobile=staff["TEACHER"]["mobile"])
                    switch_section = Section.objects.create(
                        school=school,
                        grade=original_section.grade,
                        name="تبديل حساب صناعي",
                        code="PARENT_STAGING_SWITCH",
                    )
                    switch_identifier = f"W{fixture['run']}"
                    switch_student = Student.objects.create(
                        school=school,
                        full_name="ابن معلم تبديل الحساب الصناعي",
                        national_id_encrypted=encrypt_national_id(switch_identifier),
                        national_id_lookup_hash=national_id_lookup_hash(switch_identifier),
                        national_id_masked=mask_national_id(switch_identifier),
                        guardian_name=switch_user.first_name,
                        guardian_mobile=switch_user.mobile,
                    )
                    StudentEnrollment.objects.create(
                        school=school,
                        student=switch_student,
                        academic_year=year,
                        grade=original_section.grade,
                        section=switch_section,
                        enrolled_at=year.start_date,
                    )
                    config.enabled = True
                    config.save(update_fields=["enabled", "updated_at"])
                    switch_receipt = submit_registration(
                        school=school,
                        data={
                            "name": switch_user.first_name,
                            "mobile": switch_user.mobile,
                            "email": f"state-fixture-{switch_user.pk}@parent.invalid",
                            "student_identifier": switch_identifier,
                            "relationship_type": "GUARDIAN",
                        },
                    )
                    switch_request = GuardianRegistrationRequest.objects.get(
                        school=school, receipt_hash=token_hash(switch_receipt["receipt_token"])
                    )
                    switch_approval = decide_registration(
                        school=school,
                        membership=manager,
                        request_id=switch_request.id,
                        data={
                            "decision": "APPROVE",
                            "student_id": switch_student.id,
                            "verification_note": "تحقق صناعي مستقل لتبديل الحساب على الجهاز نفسه",
                            "decision_reason": "",
                            "contact_bound": True,
                            "delivery": "MANUAL",
                        },
                    )
                    switch_token = parse_qs(urlparse(switch_approval["activation_url"]).fragment)[
                        "token"
                    ][0]
                    complete_activation(token=switch_token, user=switch_user)
                    _verified_synthetic_email(switch_user)
                    switch_relation = GuardianStudentRelation.objects.get(
                        school=school, student=switch_student, user=switch_user
                    )
                    config.enabled = original_enabled
                    config.save(update_fields=["enabled", "updated_at"])
                    fixture["acceptance"]["switch_actor"] = {
                        "id": switch_user.id,
                        "mobile": switch_user.mobile,
                        "student_id": switch_student.id,
                        "student_name": switch_student.full_name,
                        "relation_id": switch_relation.id,
                        "school_id": school.id,
                        "membership_id": staff["TEACHER"]["membership_id"],
                    }
        output.write_text(json.dumps(fixture, ensure_ascii=False, indent=2), encoding="utf-8")
        self.stdout.write(
            self.style.SUCCESS("Synthetic acceptance fixture created; no provider configured")
        )
