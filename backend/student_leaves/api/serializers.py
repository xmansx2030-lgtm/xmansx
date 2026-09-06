from django.utils import timezone
from rest_framework import serializers

from student_leaves.models import StudentLeaveStatus


class StudentLeaveFilterSerializer(serializers.Serializer):
    student = serializers.IntegerField(min_value=1, required=False)
    date = serializers.DateField(required=False)
    search = serializers.CharField(max_length=200, required=False, allow_blank=True)
    status = serializers.ChoiceField(
        choices=StudentLeaveStatus.values,
        required=False,
        allow_blank=True,
    )


class CreateStudentLeaveSerializer(serializers.Serializer):
    student_id = serializers.IntegerField(min_value=1)
    leave_date = serializers.DateField()
    leave_time = serializers.TimeField()
    reason = serializers.CharField(min_length=3, max_length=500, trim_whitespace=True)

    def validate_leave_date(self, value):
        if value > timezone.localdate():
            raise serializers.ValidationError("لا يمكن اختيار تاريخ مستقبلي.")
        return value


class CancelStudentLeaveSerializer(serializers.Serializer):
    reason = serializers.CharField(min_length=3, max_length=300, trim_whitespace=True)
