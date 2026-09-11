import hashlib
import os
from datetime import date, datetime, time, timedelta

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from academics.models import AcademicYear, AcademicYearStatus
from accounts.models import User
from attendance.models import (
    AttendanceMark,
    AttendanceSession,
    DailyAbsenceStatus,
    DailyAttendanceSummary,
    DailyCompleteness,
)
from common.security.identifiers import encrypt_national_id, national_id_lookup_hash
from common.tenant_rls import tenant_context
from counseling.models import CaseStatus, CounselorCase
from devices.models import (
    ArrivalSource,
    ArrivalStatus,
    AttendanceDevice,
    DeviceEvent,
    DeviceStatus,
    EventProcessingStatus,
    IdentityStatus,
    SchoolArrival,
    StudentDeviceIdentity,
)
from documents.models import DocumentStatus, DocumentType, GeneratedDocument
from excuses.models import (
    AbsenceExcuse,
    AbsenceExcuseAttachment,
    AbsenceExcuseStatus,
    ExcuseReasonType,
)
from memberships.models import SchoolMembership, SchoolMembershipRole, SchoolRole
from referrals.models import (
    ReferralCategory,
    ReferralReason,
    ReferralSourceType,
    ReferralStatus,
    StudentReferral,
)
from schools.models import School, SchoolSettings
from student_warnings.models import (
    StudentWarning,
    WarningLevel,
    WarningRuleType,
    WarningStatus,
)
from students.models import Grade, Section, Student, StudentEnrollment
from subscriptions.models import (
    EntitlementKey,
    PlanEntitlement,
    SaaSPlan,
    SchoolSubscription,
    SubscriptionEntitlement,
    SubscriptionEvent,
    SubscriptionEventType,
    SubscriptionStatus,
)

SLUG = "phase18-restore-school-a"
MANAGER_MOBILE = "0550189999"


class Command(BaseCommand):
    help = "Seed deterministic representative data for the isolated Phase 18 restore drill."

    def handle(self, *args, **options):
        with tenant_context(bypass=True):
            return self._seed(*args, **options)

    def _seed(self, *args, **options):
        password = os.environ.get("RESTORE_DRILL_MANAGER_PASSWORD", "")
        if len(password) < 12:
            raise CommandError("RESTORE_DRILL_MANAGER_PASSWORD must be at least 12 characters")
        if School.objects.filter(slug=SLUG).exists():
            raise CommandError("restore drill school already exists; use a clean source database")
        with transaction.atomic():
            school = School.objects.create(name="Phase 18 Restore School A", slug=SLUG)
            SchoolSettings.objects.create(school=school, city="Riyadh")
            user = User.objects.create_user(
                mobile=MANAGER_MOBILE,
                password=password,
                first_name="Restore",
                last_name="Manager",
            )
            membership = SchoolMembership.objects.create(user=user, school=school)
            SchoolMembershipRole.objects.create(
                membership=membership, role=SchoolRole.SCHOOL_MANAGER
            )

            year = AcademicYear.objects.create(
                school=school,
                name="2026/2027",
                start_date=date(2026, 8, 1),
                end_date=date(2027, 7, 31),
                status=AcademicYearStatus.ACTIVE,
            )
            grade = Grade.objects.create(
                school=school, name="Grade 10", code="grade-10", sequence=10
            )
            section = Section.objects.create(school=school, grade=grade, name="A", code="a")
            national_id = "1098765432"
            student = Student.objects.create(
                school=school,
                national_id_encrypted=encrypt_national_id(national_id),
                national_id_lookup_hash=national_id_lookup_hash(national_id),
                national_id_masked=Student.mask(national_id),
                student_number="P18-001",
                full_name="Phase 18 Restore Student",
            )
            StudentEnrollment.objects.create(
                school=school,
                student=student,
                academic_year=year,
                grade=grade,
                section=section,
                enrolled_at=date(2026, 8, 1),
            )

            attendance_date = date(2026, 8, 20)
            session = AttendanceSession.objects.create(
                school=school,
                academic_year=year,
                section=section,
                attendance_date=attendance_date,
                period_sequence=1,
                bell_period_snapshot={
                    "sequence": 1,
                    "name": "Period 1",
                    "start_time": "07:00",
                    "end_time": "07:45",
                },
                status="SUBMITTED",
                roster_fingerprint="phase18-restore",
                unprepared_alert_minutes_snapshot=25,
                started_by_membership=membership,
                submitted_by_membership=membership,
                submitted_at=timezone.now(),
            )
            AttendanceMark.objects.create(
                school=school,
                session=session,
                student=student,
                status="ABSENT",
            )
            DailyAttendanceSummary.objects.create(
                school=school,
                student=student,
                academic_year=year,
                section=section,
                attendance_date=attendance_date,
                expected_periods=1,
                submitted_periods=1,
                absent_periods=1,
                late_periods=0,
                present_periods=0,
                unexcused_absent_periods=1,
                completeness_status=DailyCompleteness.COMPLETE,
                absence_status=DailyAbsenceStatus.FULL,
                calculated_at=timezone.now(),
            )

            excuse = AbsenceExcuse.objects.create(
                school=school,
                student=student,
                status=AbsenceExcuseStatus.APPROVED,
                reason_type=ExcuseReasonType.OFFICIAL,
                recorded_by_membership=membership,
                recorded_at=timezone.now(),
                approved_by_membership=membership,
                approved_at=timezone.now(),
            )
            attachment_bytes = b"phase18 restore attachment\n"
            AbsenceExcuseAttachment.objects.create(
                school=school,
                excuse=excuse,
                file=ContentFile(attachment_bytes, name="restore-proof.pdf"),
                original_filename="restore-proof.pdf",
                mime_type="application/pdf",
                size_bytes=len(attachment_bytes),
                checksum=hashlib.sha256(attachment_bytes).hexdigest(),
                uploaded_by_membership=membership,
            )

            warning = StudentWarning.objects.create(
                school=school,
                student=student,
                academic_year=year,
                warning_type=WarningRuleType.UNEXCUSED_FULL_DAY_ABSENCE,
                level=WarningLevel.LEVEL_1,
                status=WarningStatus.ISSUED,
                threshold_at_issue=1,
                metric_value_at_issue=1,
                student_name_snapshot=student.full_name,
                grade_name_snapshot=grade.name,
                section_name_snapshot=section.name,
                national_id_masked_snapshot=student.national_id_masked,
                full_absence_days_at_issue=1,
                unexcused_full_absence_days_at_issue=1,
                absent_periods_at_issue=1,
                unexcused_absent_periods_at_issue=1,
                issued_by_membership=membership,
                issued_at=timezone.now(),
            )
            pdf_bytes = b"%PDF-1.4\n% Phase 18 immutable restore document\n%%EOF\n"
            GeneratedDocument.objects.create(
                school=school,
                student=student,
                warning=warning,
                document_type=DocumentType.WARNING_LEVEL_1,
                template_key="warning_level_1",
                template_version="v1",
                status=DocumentStatus.READY,
                snapshot_data={"restore_drill": True},
                file=ContentFile(pdf_bytes, name="restore-document.pdf"),
                mime_type="application/pdf",
                size_bytes=len(pdf_bytes),
                checksum=hashlib.sha256(pdf_bytes).hexdigest(),
                generated_by_membership=membership,
                generated_at=timezone.now(),
            )

            referral = StudentReferral.objects.create(
                school=school,
                student=student,
                source_type=ReferralSourceType.SCHOOL_MANAGER,
                category=ReferralCategory.ATTENDANCE,
                reason_code=ReferralReason.REPEATED_ABSENCE,
                created_by_membership=membership,
                assigned_counselor_membership=membership,
                status=ReferralStatus.ACKNOWLEDGED,
                accepted_at=timezone.now(),
                snapshot_data={"restore_drill": True},
            )
            CounselorCase.objects.create(
                school=school,
                student=student,
                primary_referral=referral,
                assigned_counselor_membership=membership,
                status=CaseStatus.OPEN,
                opened_by_membership=membership,
                opened_at=timezone.now(),
                last_activity_at=timezone.now(),
                snapshot_data={"restore_drill": True},
            )

            device = AttendanceDevice.objects.create(
                school=school,
                name="Restore Gate Device",
                status=DeviceStatus.ONLINE,
                last_seen_at=timezone.now(),
                last_successful_sync_at=timezone.now(),
            )
            StudentDeviceIdentity.objects.create(
                school=school,
                device=device,
                external_user_id="P18-001",
                student=student,
                status=IdentityStatus.MATCHED,
                mapped_at=timezone.now(),
                mapped_by_membership=membership,
            )
            device_event = DeviceEvent.objects.create(
                school=school,
                device=device,
                external_event_id="restore-event-1",
                dedupe_key="phase18-restore-event-1",
                external_user_id="P18-001",
                occurred_at=timezone.now(),
                student=student,
                processing_status=EventProcessingStatus.PROCESSED,
            )
            SchoolArrival.objects.create(
                school=school,
                student=student,
                attendance_date=attendance_date,
                first_arrival_at=datetime.combine(
                    attendance_date, time(7, 8), tzinfo=timezone.get_current_timezone()
                ),
                raw_late_minutes=8,
                counted_late_minutes=3,
                status=ArrivalStatus.LATE,
                source=ArrivalSource.BIOMETRIC,
                device_event=device_event,
            )

            plan = SaaSPlan.objects.create(
                code="phase18-restore-professional",
                name_ar="Phase 18 Professional",
                name_en="Phase 18 Professional",
            )
            entitlement_values = {
                EntitlementKey.MAX_STUDENTS: 1000,
                EntitlementKey.MAX_STAFF: 100,
                EntitlementKey.MAX_DEVICES: 10,
                EntitlementKey.MAX_STORAGE_GB: 10,
            }
            for key in EntitlementKey.values:
                numeric = entitlement_values.get(key)
                PlanEntitlement.objects.create(
                    plan=plan,
                    key=key,
                    numeric_value=numeric,
                    is_enabled=True,
                )
            subscription = SchoolSubscription.objects.create(
                school=school,
                plan=plan,
                status=SubscriptionStatus.ACTIVE,
                starts_at=timezone.now() - timedelta(days=1),
                ends_at=timezone.now() + timedelta(days=365),
                created_by=user,
                updated_by=user,
            )
            for entitlement in plan.entitlements.all():
                SubscriptionEntitlement.objects.create(
                    subscription=subscription,
                    key=entitlement.key,
                    numeric_value=entitlement.numeric_value,
                    is_enabled=entitlement.is_enabled,
                )
            SubscriptionEvent.objects.create(
                school=school,
                subscription=subscription,
                event_type=SubscriptionEventType.ACTIVATED,
                actor=user,
                reason="Phase 18 restore drill",
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"restore drill fixture seeded school={SLUG} manager={MANAGER_MOBILE}"
            )
        )
