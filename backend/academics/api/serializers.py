from rest_framework import serializers

from academics.models import (
    AcademicYear,
    BellPeriod,
    BellSchedule,
    Semester,
    Weekday,
)

# ---- إخراج (school لا يظهر — السياق معروف) ----


class SemesterSerializer(serializers.ModelSerializer):
    class Meta:
        model = Semester
        fields = ["id", "name", "sequence", "start_date", "end_date", "status"]


class AcademicYearSerializer(serializers.ModelSerializer):
    semesters = SemesterSerializer(many=True, read_only=True)

    class Meta:
        model = AcademicYear
        fields = ["id", "name", "start_date", "end_date", "status", "semesters"]


class BellPeriodSerializer(serializers.ModelSerializer):
    class Meta:
        model = BellPeriod
        fields = ["id", "sequence", "name", "start_time", "end_time", "is_attendance_period"]


class BellScheduleSerializer(serializers.ModelSerializer):
    periods = BellPeriodSerializer(many=True, read_only=True)

    class Meta:
        model = BellSchedule
        fields = ["id", "name", "status", "valid_from", "valid_to", "periods"]


# ---- إدخال (بلا school ولا ids حرة — منع mass assignment) ----


class AcademicYearInputSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=50)
    start_date = serializers.DateField()
    end_date = serializers.DateField()


class SemesterInputSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=50)
    sequence = serializers.IntegerField(min_value=1, max_value=10)
    start_date = serializers.DateField()
    end_date = serializers.DateField()


class BellScheduleInputSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100)
    valid_from = serializers.DateField(required=False, allow_null=True)
    valid_to = serializers.DateField(required=False, allow_null=True)


class BellPeriodInputSerializer(serializers.Serializer):
    sequence = serializers.IntegerField(min_value=1, max_value=20)
    name = serializers.CharField(max_length=50)
    start_time = serializers.TimeField()
    end_time = serializers.TimeField()
    is_attendance_period = serializers.BooleanField(default=True)


class PeriodsReplaceSerializer(serializers.Serializer):
    periods = BellPeriodInputSerializer(many=True)


class WeekDayInputSerializer(serializers.Serializer):
    weekday = serializers.ChoiceField(choices=Weekday.choices)
    is_school_day = serializers.BooleanField()
    bell_schedule_id = serializers.IntegerField(required=False, allow_null=True)


class WeekDaysReplaceSerializer(serializers.Serializer):
    days = WeekDayInputSerializer(many=True)


def serialize_week_day(week_day) -> dict:
    return {
        "weekday": week_day.weekday,
        "is_school_day": week_day.is_school_day,
        "bell_schedule_id": week_day.bell_schedule_id,
        "bell_schedule_name": week_day.bell_schedule.name if week_day.bell_schedule else None,
    }
