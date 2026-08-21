import json
from pathlib import Path

from django.core.exceptions import ValidationError

from attendance.models import DailyAttendanceSummary
from counseling.models import CounselorCase
from devices.models import AttendanceDevice, DeviceEvent, SchoolArrival, StudentDeviceIdentity
from documents.models import GeneratedDocument
from excuses.models import AbsenceExcuse, AbsenceExcuseAttachment
from memberships.models import SchoolMembership
from referrals.models import StudentReferral
from schools.models import School
from student_warnings.models import StudentWarning
from students.models import Student, StudentEnrollment
from subscriptions.models import (
    SchoolSubscription,
    SubscriptionEntitlement,
    SubscriptionEvent,
)


def _one(queryset, label: str):
    instance = queryset.order_by("id").first()
    if instance is None:
        raise ValidationError(f"restore fixture is missing {label}")
    return instance


def capture_restore_manifest(school_slug: str) -> dict:
    school = School.objects.get(slug=school_slug)
    membership = _one(SchoolMembership.objects.filter(school=school), "membership")
    student = _one(Student.objects.filter(school=school), "student")
    enrollment = _one(
        StudentEnrollment.objects.filter(school=school, student=student), "enrollment"
    )
    attendance = _one(
        DailyAttendanceSummary.objects.filter(school=school, student=student), "attendance"
    )
    arrival = _one(SchoolArrival.objects.filter(school=school, student=student), "arrival")
    excuse = _one(AbsenceExcuse.objects.filter(school=school, student=student), "excuse")
    attachment = _one(
        AbsenceExcuseAttachment.objects.filter(school=school, excuse=excuse), "attachment"
    )
    warning = _one(StudentWarning.objects.filter(school=school, student=student), "warning")
    document = _one(GeneratedDocument.objects.filter(school=school, student=student), "document")
    referral = _one(StudentReferral.objects.filter(school=school, student=student), "referral")
    case = _one(CounselorCase.objects.filter(school=school, student=student), "counselor case")
    device = _one(AttendanceDevice.objects.filter(school=school), "device")
    identity = _one(
        StudentDeviceIdentity.objects.filter(school=school, student=student), "identity"
    )
    event = _one(DeviceEvent.objects.filter(school=school, student=student), "device event")
    subscription = _one(SchoolSubscription.objects.filter(school=school), "subscription")
    entitlements = list(
        SubscriptionEntitlement.objects.filter(subscription=subscription)
        .order_by("key")
        .values("key", "numeric_value", "is_enabled", "is_override")
    )
    if not entitlements:
        raise ValidationError("restore fixture is missing entitlement snapshots")
    if not SubscriptionEvent.objects.filter(subscription=subscription).exists():
        raise ValidationError("restore fixture is missing subscription events")
    return {
        "schema_version": 1,
        "school": {"id": school.id, "slug": school.slug},
        "manager": {"membership_id": membership.id, "user_id": membership.user_id},
        "student": {
            "id": student.id,
            "school_id": student.school_id,
            "lookup_hash": student.national_id_lookup_hash,
        },
        "enrollment": {
            "id": enrollment.id,
            "student_id": enrollment.student_id,
            "section_id": enrollment.section_id,
            "status": enrollment.status,
        },
        "attendance": {
            "id": attendance.id,
            "expected": attendance.expected_periods,
            "submitted": attendance.submitted_periods,
            "absent": attendance.absent_periods,
            "late": attendance.late_periods,
            "status": attendance.absence_status,
        },
        "arrival": {
            "id": arrival.id,
            "status": arrival.status,
            "late_minutes": arrival.counted_late_minutes,
        },
        "excuse": {"id": excuse.id, "status": excuse.status},
        "attachment": {"id": attachment.id, "checksum": attachment.checksum},
        "warning": {"id": warning.id, "status": warning.status, "level": warning.level},
        "document": {
            "id": document.id,
            "status": document.status,
            "checksum": document.checksum,
            "storage_key": document.storage_key,
        },
        "referral": {"id": referral.id, "status": referral.status},
        "counselor_case": {"id": case.id, "status": case.status},
        "device": {"id": device.id, "status": device.status},
        "device_identity": {"id": identity.id, "student_id": identity.student_id},
        "device_event": {"id": event.id, "student_id": event.student_id},
        "subscription": {
            "id": subscription.id,
            "plan_id": subscription.plan_id,
            "status": subscription.status,
            "entitlements": entitlements,
            "event_count": SubscriptionEvent.objects.filter(subscription=subscription).count(),
        },
        "counts": {
            "students": Student.objects.filter(school=school).count(),
            "enrollments": StudentEnrollment.objects.filter(school=school).count(),
            "attendance": DailyAttendanceSummary.objects.filter(school=school).count(),
            "excuses": AbsenceExcuse.objects.filter(school=school).count(),
            "warnings": StudentWarning.objects.filter(school=school).count(),
            "documents": GeneratedDocument.objects.filter(school=school).count(),
            "referrals": StudentReferral.objects.filter(school=school).count(),
            "counselor_cases": CounselorCase.objects.filter(school=school).count(),
            "devices": AttendanceDevice.objects.filter(school=school).count(),
        },
    }


def verify_restore_manifest(expected: dict) -> dict:
    actual = capture_restore_manifest(expected["school"]["slug"])
    if actual != expected:
        raise ValidationError("restored representative data does not match the source manifest")
    return {"status": "pass", "counts": actual["counts"]}


def write_manifest(path: Path, manifest: dict) -> None:
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
