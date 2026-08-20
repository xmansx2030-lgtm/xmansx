"""مخططات الإدخال — العميل يرسل نية فقط، والخادم يبني كل ما عداها."""

from rest_framework import serializers

from student_actions.models import StudentActionType


class CreateActionSerializer(serializers.Serializer):
    student_id = serializers.IntegerField()
    action_type = serializers.ChoiceField(choices=StudentActionType.values)
    warning_id = serializers.IntegerField(required=False, allow_null=True)
    performed_at = serializers.DateTimeField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True, max_length=500)


class CancelActionSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=300)


class ActionSerializer(serializers.Serializer):
    """للتوثيق فقط (drf-spectacular) — الاستجابة تبنى في الـview."""

    id = serializers.IntegerField()
    student_id = serializers.IntegerField()
    action_type = serializers.CharField()
    action_type_label = serializers.CharField()
    status = serializers.CharField()
    status_label = serializers.CharField()
    warning_id = serializers.IntegerField(allow_null=True)
    warning_label = serializers.CharField(allow_null=True)
    performed_at = serializers.CharField()
    performed_by_name = serializers.CharField(allow_null=True)
    notes = serializers.CharField()
    cancelled_at = serializers.CharField(allow_null=True)
    cancellation_reason = serializers.CharField()
