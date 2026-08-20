"""مخططات الإدخال — العميل يرسل نية فقط.

**ممنوع** قبول `school` أو `opened_by` أو `assigned_counselor` أو `completed_by`
أو `closed_by` أو أي لقطة (البند 101): عدم تعريفها هنا يجعل DRF يتجاهلها،
والخادم يبنيها من الجلسة.
"""

from rest_framework import serializers

from counseling.models import (
    ActivityType,
    CaseClosureReason,
    CasePriority,
    CaseStatus,
    FollowUpRequestType,
    GoalStatus,
    GoalType,
    ImprovementStatus,
    PlanStatus,
    SessionType,
    TeacherImprovementStatus,
)


class OpenCaseSerializer(serializers.Serializer):
    priority = serializers.ChoiceField(choices=CasePriority.values, required=False)


class CaseStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=CaseStatus.values)


class CloseCaseSerializer(serializers.Serializer):
    closure_reason = serializers.ChoiceField(choices=CaseClosureReason.values)
    outcome_summary = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    improvement_status = serializers.ChoiceField(
        choices=ImprovementStatus.values, required=False
    )


class ReopenCaseSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=300)


class ReassignCaseSerializer(serializers.Serializer):
    counselor_membership_id = serializers.IntegerField()


class SessionSerializer(serializers.Serializer):
    session_type = serializers.ChoiceField(choices=SessionType.values)
    occurred_at = serializers.DateTimeField(required=False, allow_null=True)
    summary = serializers.CharField(max_length=2000)
    observations = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    outcome = serializers.CharField(required=False, allow_blank=True, max_length=1000)


class VoidSessionSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=300)


class PlanSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=200)
    start_date = serializers.DateField()
    target_end_date = serializers.DateField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    activate = serializers.BooleanField(required=False, default=False)


class PlanStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=PlanStatus.values)


class GoalSerializer(serializers.Serializer):
    goal_type = serializers.ChoiceField(choices=GoalType.values)
    title = serializers.CharField(max_length=200)
    description = serializers.CharField(required=False, allow_blank=True, max_length=1000)
    baseline_value = serializers.IntegerField(required=False, allow_null=True)
    target_value = serializers.IntegerField(required=False, allow_null=True)
    unit = serializers.CharField(required=False, allow_blank=True, max_length=20)


class GoalStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=GoalStatus.values)


class ActivitySerializer(serializers.Serializer):
    activity_type = serializers.ChoiceField(choices=ActivityType.values)
    title = serializers.CharField(max_length=200)
    description = serializers.CharField(required=False, allow_blank=True, max_length=1000)
    due_date = serializers.DateField(required=False, allow_null=True)


class TeacherRequestSerializer(serializers.Serializer):
    teacher_membership_id = serializers.IntegerField()
    request_type = serializers.ChoiceField(choices=FollowUpRequestType.values)
    question = serializers.CharField(max_length=1000)
    due_date = serializers.DateField(required=False, allow_null=True)


class TeacherResponseSerializer(serializers.Serializer):
    observation = serializers.CharField(max_length=2000)
    improvement_status = serializers.ChoiceField(choices=TeacherImprovementStatus.values)
    notes = serializers.CharField(required=False, allow_blank=True, max_length=1000)


class CaseRowSerializer(serializers.Serializer):
    """للتوثيق فقط — الاستجابة تبنى في الـview."""

    id = serializers.IntegerField()
    student_id = serializers.IntegerField()
    student_name = serializers.CharField()
    grade_name = serializers.CharField(allow_null=True)
    section_name = serializers.CharField(allow_null=True)
    status = serializers.CharField()
    status_label = serializers.CharField()
    priority = serializers.CharField()
    referral_category_label = serializers.CharField()
    referral_reason_label = serializers.CharField()
    counselor_name = serializers.CharField(allow_null=True)
    opened_at = serializers.CharField()
    last_activity_at = serializers.CharField()
    next_activity_due = serializers.CharField(allow_null=True)
