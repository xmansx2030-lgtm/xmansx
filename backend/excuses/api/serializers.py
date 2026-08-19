"""‏serializer-first (قاعدة OPENAPI.md) — الإدخال لا يقبل school/status/approved_by:
إجراءات الاعتماد/الرفض/الإلغاء endpoints منفصلة (لا Mass Assignment — بند 96).
"""

from rest_framework import serializers

from excuses.models import (
    AbsenceExcuse,
    AbsenceExcuseStatus,
    ExcuseCoverageStatus,
    ExcuseReasonType,
)

# ---- الإدخال ----


class TargetInputSerializer(serializers.Serializer):
    attendance_date = serializers.DateField()
    period_sequence = serializers.IntegerField(
        min_value=1, max_value=30, required=False, allow_null=True, default=None
    )


class ExcuseCreateSerializer(serializers.Serializer):
    student_id = serializers.IntegerField(min_value=1)
    reason_type = serializers.ChoiceField(choices=ExcuseReasonType.choices)
    notes = serializers.CharField(max_length=500, allow_blank=True, default="")
    targets = TargetInputSerializer(many=True)


class ExcusePatchSerializer(serializers.Serializer):
    reason_type = serializers.ChoiceField(choices=ExcuseReasonType.choices, required=False)
    notes = serializers.CharField(max_length=500, allow_blank=True, required=False)
    targets = TargetInputSerializer(many=True, required=False)


class ApproveSerializer(serializers.Serializer):
    preview_hash = serializers.CharField(max_length=64)


class DecisionReasonSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=300)


# ---- الإخراج ----


def _membership_name(membership) -> str | None:
    if membership is None:
        return None
    profile = getattr(membership, "staff_profile", None)
    return profile.display_name if profile else membership.user.display_name


def _current_enrollment(student):
    enrollments = [e for e in student.enrollments.all() if e.status == "ACTIVE"]
    if not enrollments:
        enrollments = list(student.enrollments.all())
    return max(enrollments, key=lambda e: e.enrolled_at, default=None)


def serialize_student_brief(student) -> dict:
    enrollment = _current_enrollment(student)
    return {
        "id": student.id,
        "full_name": student.full_name,
        "grade_name": enrollment.grade.name if enrollment else None,
        "section_name": enrollment.section.name if enrollment else None,
    }


def serialize_excuse_row(excuse: AbsenceExcuse) -> dict:
    """صف قائمة — يعتمد على annotations (targets_count...) وprefetch (لا N+1)."""
    return {
        "id": excuse.id,
        "student": serialize_student_brief(excuse.student),
        "status": excuse.status,
        "status_label": AbsenceExcuseStatus(excuse.status).label,
        "reason_type": excuse.reason_type,
        "reason_type_label": ExcuseReasonType(excuse.reason_type).label,
        "date_from": excuse.date_from.isoformat() if excuse.date_from else None,
        "date_to": excuse.date_to.isoformat() if excuse.date_to else None,
        "targets_count": excuse.targets_count,
        "active_coverage_count": excuse.active_coverage_count,
        "attachments_count": excuse.attachments_count,
        "recorded_at": excuse.recorded_at.isoformat(),
        "recorded_by_name": _membership_name(excuse.recorded_by_membership),
        "approved_by_name": _membership_name(excuse.approved_by_membership),
    }


def serialize_excuse_detail(excuse: AbsenceExcuse) -> dict:
    targets = [
        {
            "id": target.id,
            "attendance_date": target.attendance_date.isoformat(),
            "period_sequence": target.period_sequence,
        }
        for target in excuse.targets.all()
    ]
    coverages = [
        {
            "id": coverage.id,
            "attendance_date": coverage.attendance_date.isoformat(),
            "period_sequence": coverage.period_sequence_snapshot,
            "status": coverage.status,
            "status_label": ExcuseCoverageStatus(coverage.status).label,
            "voided_at": coverage.voided_at.isoformat() if coverage.voided_at else None,
            "void_reason": coverage.void_reason,
        }
        for coverage in excuse.coverages.all()
    ]
    attachments = [serialize_attachment(a) for a in excuse.attachments.all()]
    return {
        "id": excuse.id,
        "student": serialize_student_brief(excuse.student),
        "status": excuse.status,
        "status_label": AbsenceExcuseStatus(excuse.status).label,
        "reason_type": excuse.reason_type,
        "reason_type_label": ExcuseReasonType(excuse.reason_type).label,
        "notes": excuse.notes,
        "targets": targets,
        "coverages": coverages,
        "active_coverage_count": sum(
            1 for c in excuse.coverages.all() if c.status == ExcuseCoverageStatus.ACTIVE
        ),
        "attachments": attachments,
        "recorded_at": excuse.recorded_at.isoformat(),
        "recorded_by_name": _membership_name(excuse.recorded_by_membership),
        "approved_at": excuse.approved_at.isoformat() if excuse.approved_at else None,
        "approved_by_name": _membership_name(excuse.approved_by_membership),
        "rejected_at": excuse.rejected_at.isoformat() if excuse.rejected_at else None,
        "rejected_by_name": _membership_name(excuse.rejected_by_membership),
        "rejection_reason": excuse.rejection_reason,
        "cancelled_at": excuse.cancelled_at.isoformat() if excuse.cancelled_at else None,
        "cancelled_by_name": _membership_name(excuse.cancelled_by_membership),
        "cancellation_reason": excuse.cancellation_reason,
    }


def serialize_attachment(attachment) -> dict:
    """‏storage_key الخام لا يعرض أبدًا (بند 85) — التنزيل عبر endpoint مصرح."""
    return {
        "id": attachment.id,
        "original_filename": attachment.original_filename,
        "mime_type": attachment.mime_type,
        "size_bytes": attachment.size_bytes,
        "created_at": attachment.created_at.isoformat(),
        "uploaded_by_name": _membership_name(attachment.uploaded_by_membership),
    }
