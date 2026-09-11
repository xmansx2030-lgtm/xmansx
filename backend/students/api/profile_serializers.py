from rest_framework import serializers


class AttendanceProfileSummarySerializer(serializers.Serializer):
    full_absence_days = serializers.IntegerField()
    partial_absence_days = serializers.IntegerField()
    undetermined_days = serializers.IntegerField()
    absent_periods = serializers.IntegerField()
    # م10 — التصنيف الإداري: الإجماليات أعلاه تبقى كما هي (بند 69)
    excused_absent_periods = serializers.IntegerField()
    unexcused_absent_periods = serializers.IntegerField()
    excused_full_absence_days = serializers.IntegerField()
    unexcused_full_absence_days = serializers.IntegerField()
    mixed_full_absence_days = serializers.IntegerField()


class AttendanceProfileSerializer(serializers.Serializer):
    student = serializers.DictField()
    period = serializers.DictField()
    attendance = AttendanceProfileSummarySerializer()
    morning_attendance = serializers.DictField()


class MorningAttendanceHistorySerializer(serializers.Serializer):
    date = serializers.DateField()
    arrival_time = serializers.DateTimeField()
    status = serializers.CharField()
    raw_late_minutes = serializers.IntegerField()
    counted_late_minutes = serializers.IntegerField()
    source = serializers.CharField()
    grade_name = serializers.CharField(allow_null=True)
    section_name = serializers.CharField(allow_null=True)


class AttendanceDaySerializer(serializers.Serializer):
    date = serializers.DateField()
    absence_status = serializers.CharField()
    absence_status_label = serializers.CharField()
    section = serializers.DictField(allow_null=True)
    absent_periods = serializers.IntegerField()
    excused_absent_periods = serializers.IntegerField()
    unexcused_absent_periods = serializers.IntegerField()


class AttendancePeriodSerializer(serializers.Serializer):
    date = serializers.DateField(source="session.attendance_date")
    sequence = serializers.IntegerField(source="session.period_sequence")
    period = serializers.DictField(source="session.bell_period_snapshot")
    section = serializers.DictField()


class AttendanceChangeSerializer(serializers.Serializer):
    date = serializers.DateField(source="session.attendance_date")
    sequence = serializers.IntegerField(source="session.period_sequence")
    period = serializers.DictField(source="session.bell_period_snapshot")
    previous_status = serializers.CharField()
    new_status = serializers.CharField()
    reason = serializers.CharField(allow_blank=True)
    actor = serializers.CharField(allow_null=True)
    changed_at = serializers.DateTimeField()
