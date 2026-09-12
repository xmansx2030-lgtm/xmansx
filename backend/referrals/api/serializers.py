"""‏serializer-first — الإدخال لا يقبل school/created_by/accepted_at/closed_at
(بند 75)؛ إجراءات دورة الحياة endpoints منفصلة لا PATCH عام.
"""

from rest_framework import serializers

from referrals.models import (
    OPEN_STATUSES,
    ReferralCategory,
    ReferralObservationType,
    ReferralPriority,
    ReferralReason,
    ReferralSourceType,
    ReferralStatus,
    StudentReferral,
)
from schools.role_labels import school_role_label

# ---- الإدخال ----


class ReferralCreateSerializer(serializers.Serializer):
    student_id = serializers.IntegerField(min_value=1)
    category = serializers.ChoiceField(choices=ReferralCategory.choices)
    reason_code = serializers.ChoiceField(choices=ReferralReason.choices)
    description = serializers.CharField(
        max_length=1000, allow_blank=True, default="", trim_whitespace=False
    )
    priority = serializers.ChoiceField(
        choices=ReferralPriority.choices, default=ReferralPriority.NORMAL
    )
    source_warning_id = serializers.IntegerField(
        min_value=1, required=False, allow_null=True, default=None
    )
    assigned_counselor_id = serializers.IntegerField(
        min_value=1, required=False, allow_null=True, default=None
    )
    # المدير/الوكيل فقط — يُتحقق في الخدمة لا هنا
    allow_duplicate = serializers.BooleanField(default=False)


class AssignSerializer(serializers.Serializer):
    counselor_membership_id = serializers.IntegerField(min_value=1)


class AssignVicePrincipalSerializer(serializers.Serializer):
    vice_principal_membership_id = serializers.IntegerField(min_value=1)


class CloseSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=300)
    cancel = serializers.BooleanField(default=False)


class ContributionCreateSerializer(serializers.Serializer):
    observation_type = serializers.ChoiceField(choices=ReferralObservationType.choices)
    notes = serializers.CharField(max_length=1000)


class OpenCaseContributionSerializer(ContributionCreateSerializer):
    """إضافة ملاحظة بالطالب والفئة — الخادم يحل الحالة المفتوحة بنفسه."""

    student_id = serializers.IntegerField(min_value=1)
    category = serializers.ChoiceField(choices=ReferralCategory.choices)


# ---- الإخراج ----


def membership_name(membership) -> str | None:
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
    """بيانات تعريف الطالب داخل الإحالة — بلا هوية ولا جوال ولي أمر (بند 29)."""
    enrollment = _current_enrollment(student)
    return {
        "id": student.id,
        "full_name": student.full_name,
        "grade_name": enrollment.grade.name if enrollment else None,
        "section_name": enrollment.section.name if enrollment else None,
    }


def serialize_referral_row(referral: StudentReferral) -> dict:
    counseling_case = next(iter(referral.cases.all()), None)
    return {
        "id": referral.id,
        "student": serialize_student_brief(referral.student),
        "source_type": referral.source_type,
        "source_type_label": school_role_label(
            referral.source_type, referral.school.school_type
        ),
        "category": referral.category,
        "category_label": referral.get_category_display(),
        "reason_code": referral.reason_code,
        "reason_label": referral.get_reason_code_display(),
        "status": referral.status,
        "status_label": referral.get_status_display(),
        "priority": referral.priority,
        "priority_label": referral.get_priority_display(),
        "created_at": referral.created_at.isoformat(),
        "created_by_name": membership_name(referral.created_by_membership),
        "assigned_vice_principal_id": referral.assigned_vice_membership_id,
        "assigned_vice_principal_name": membership_name(referral.assigned_vice_membership),
        "assigned_counselor_id": referral.assigned_counselor_membership_id,
        "assigned_counselor_name": membership_name(referral.assigned_counselor_membership),
        "counseling_case_id": counseling_case.id if counseling_case else None,
    }


def serialize_contribution(contribution) -> dict:
    return {
        "id": contribution.id,
        "observation_type": contribution.observation_type,
        "observation_type_label": contribution.get_observation_type_display(),
        "notes": contribution.notes,
        "created_at": contribution.created_at.isoformat(),
        "created_by_name": membership_name(contribution.created_by_membership),
    }


def serialize_event(event) -> dict:
    return {
        "id": event.id,
        "event_type": event.event_type,
        "event_type_label": event.get_event_type_display(),
        "actor_name": membership_name(event.actor_membership),
        "created_at": event.created_at.isoformat(),
        "metadata": event.metadata_safe,
    }


def serialize_referral_detail(
    referral: StudentReferral,
    *,
    current_metrics=None,
    membership=None,
    roles=None,
    recommended_counselor=None,
) -> dict:
    """التفاصيل: لقطة الإحالة ثابتة، والمؤشرات الحالية منفصلة عنها صراحة (بند 59).

    ‏can_cancel يُحسب خادميًا لتخفي الواجهة زرًا سيرفضه الخادم أصلًا.
    """
    role_set = set(roles or [])
    is_manager = "SCHOOL_MANAGER" in role_set
    is_responsible_vice = (
        "VICE_PRINCIPAL" in role_set
        and membership is not None
        and referral.assigned_vice_membership_id == membership.id
    )
    is_assigned_counselor = (
        "COUNSELOR" in role_set
        and membership is not None
        and referral.assigned_counselor_membership_id == membership.id
    )
    is_creator = membership is not None and (referral.created_by_membership_id == membership.id)
    vice_stage_ready = (
        referral.source_type != ReferralSourceType.TEACHER
        or referral.assigned_vice_membership_id is not None
    )
    return {
        **serialize_referral_row(referral),
        "can_cancel": (
            referral.status in OPEN_STATUSES
            and (
                is_manager
                or (
                    is_creator
                    and referral.status == ReferralStatus.PENDING_VICE
                )
            )
        ),
        "can_assign_vice_principal": is_manager
        and referral.status
        in (ReferralStatus.PENDING_VICE, ReferralStatus.UNDER_VICE_REVIEW),
        "can_start_vice_review": (
            is_manager or is_responsible_vice
        )
        and vice_stage_ready
        and referral.status == ReferralStatus.PENDING_VICE,
        "can_forward_to_counselor": (
            is_manager or is_responsible_vice
        )
        and vice_stage_ready
        and referral.status
        in (
            ReferralStatus.PENDING_VICE,
            ReferralStatus.UNDER_VICE_REVIEW,
            ReferralStatus.REFERRED,
        ),
        "can_acknowledge": is_assigned_counselor
        and referral.status == ReferralStatus.REFERRED,
        "can_close": (
            is_manager
            or (
                is_responsible_vice
                and referral.status
                in (
                    ReferralStatus.PENDING_VICE,
                    ReferralStatus.UNDER_VICE_REVIEW,
                )
            )
            or (
                is_assigned_counselor
                and referral.status == ReferralStatus.ACKNOWLEDGED
            )
        )
        and referral.status in OPEN_STATUSES,
        "description": referral.description,
        "snapshot_at_referral": referral.snapshot_data,
        "current_metrics": current_metrics,
        "source_warning": (
            {
                "id": referral.source_warning_id,
                "warning_type": referral.source_warning.warning_type,
                "level": referral.source_warning.level,
                "issued_at": referral.source_warning.issued_at.isoformat(),
            }
            if referral.source_warning_id and referral.source_warning
            else None
        ),
        "accepted_at": referral.accepted_at.isoformat() if referral.accepted_at else None,
        "vice_reviewed_at": (
            referral.vice_reviewed_at.isoformat() if referral.vice_reviewed_at else None
        ),
        "recommended_counselor_id": (
            recommended_counselor.id if recommended_counselor else None
        ),
        "recommended_counselor_name": membership_name(recommended_counselor),
        "closed_at": referral.closed_at.isoformat() if referral.closed_at else None,
        "closed_by_name": membership_name(referral.closed_by_membership),
        "closure_reason": referral.closure_reason,
        "contributions": [serialize_contribution(c) for c in referral.contributions.all()],
        # ترتيب صريح يضمن أن يظهر الخط الزمني من الإنشاء إلى أحدث إجراء حتى
        # عندما تتقارب أزمنة الأحداث أو يغيّر مخطط قاعدة البيانات ترتيب الصفوف.
        "events": [
            serialize_event(e)
            for e in referral.events.order_by("created_at", "id")
        ],
    }


def serialize_counselor(membership) -> dict:
    return {"id": membership.id, "name": membership_name(membership)}
