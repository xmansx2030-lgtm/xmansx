from django.utils import timezone
from rest_framework import serializers

from student_leaves.models import StudentLeaveStatus

_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


class StudentLeaveFilterSerializer(serializers.Serializer):
    student = serializers.IntegerField(min_value=1, required=False)
    date = serializers.DateField(required=False)
    search = serializers.CharField(max_length=200, required=False, allow_blank=True)
    status = serializers.ChoiceField(
        choices=StudentLeaveStatus.values,
        required=False,
        allow_blank=True,
    )


class GateStudentLeaveFilterSerializer(serializers.Serializer):
    search = serializers.CharField(max_length=200, required=False, allow_blank=True)


class CreateStudentLeaveSerializer(serializers.Serializer):
    student_id = serializers.IntegerField(min_value=1)
    leave_date = serializers.DateField()
    leave_time = serializers.TimeField()
    reason = serializers.CharField(min_length=3, max_length=500, trim_whitespace=True)
    recipient_name = serializers.CharField(
        max_length=150, required=False, allow_blank=True, default="", trim_whitespace=True
    )
    recipient_relationship = serializers.CharField(
        max_length=60, required=False, allow_blank=True, default="", trim_whitespace=True
    )
    recipient_id_last4 = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
    )

    def validate_leave_date(self, value):
        if value > timezone.localdate():
            raise serializers.ValidationError("لا يمكن اختيار تاريخ مستقبلي.")
        return value

    def validate_recipient_id_last4(self, value):
        normalized = value.strip().translate(_ARABIC_DIGITS)
        if normalized and (
            len(normalized) != 4 or not normalized.isascii() or not normalized.isdigit()
        ):
            raise serializers.ValidationError("أدخل آخر أربعة أرقام من هوية المستلم.")
        return normalized


class CancelStudentLeaveSerializer(serializers.Serializer):
    reason = serializers.CharField(min_length=3, max_length=300, trim_whitespace=True)
