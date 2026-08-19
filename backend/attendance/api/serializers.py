"""‏Serializers الحضور — serializer-first (قاعدة OPENAPI.md من المرحلة 5)."""

from rest_framework import serializers

from attendance.models import AttendanceMarkStatus, AttendanceSession

# ---- الإدخال ----


class StartSessionSerializer(serializers.Serializer):
    section_id = serializers.IntegerField(min_value=1)


class MarkInputSerializer(serializers.Serializer):
    student_id = serializers.IntegerField(min_value=1)
    status = serializers.ChoiceField(choices=AttendanceMarkStatus.choices)
    arrival_time = serializers.TimeField(required=False, allow_null=True)
    # ملاحظة أمنية: لا حقل late_minutes هنا — يحسب خادميًا حصرًا


class SubmitSessionSerializer(serializers.Serializer):
    marks = MarkInputSerializer(many=True)


class EditSessionSerializer(SubmitSessionSerializer):
    reason = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")


class QrResolveSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=64)


# ---- الإخراج ----


class PeriodSerializer(serializers.Serializer):
    sequence = serializers.IntegerField()
    name = serializers.CharField()
    start_time = serializers.CharField()
    end_time = serializers.CharField()


class CurrentPeriodResponseSerializer(serializers.Serializer):
    period = PeriodSerializer(allow_null=True)
    date = serializers.DateField()


class AttendanceSectionSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    grade_id = serializers.IntegerField(required=False)
    grade_name = serializers.CharField()
    students_count = serializers.IntegerField()


class RosterStudentSerializer(serializers.Serializer):
    student_id = serializers.IntegerField()
    full_name = serializers.CharField()
    national_id_masked = serializers.CharField()


class MarkSerializer(serializers.Serializer):
    student_id = serializers.IntegerField()
    status = serializers.CharField()
    arrival_time = serializers.TimeField(allow_null=True)
    late_minutes = serializers.IntegerField(allow_null=True)


class SessionSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    status = serializers.CharField()
    attendance_date = serializers.DateField()
    section = AttendanceSectionSerializer()
    period = PeriodSerializer(source="bell_period_snapshot")
    submitted_by = serializers.CharField(allow_null=True)
    submitted_at = serializers.DateTimeField(allow_null=True)
    can_edit = serializers.BooleanField()
    roster = RosterStudentSerializer(many=True)
    marks = MarkSerializer(many=True)


class QrInfoSerializer(serializers.Serializer):
    section_id = serializers.IntegerField()
    section_name = serializers.CharField()
    grade_name = serializers.CharField()
    token = serializers.CharField()
    url_path = serializers.CharField()


# ---- التحليلات (م8) — بلا PII طلاب: لا هوية ولا جوال ولي أمر ----


class MultiPeriodRequestSerializer(serializers.Serializer):
    date = serializers.DateField()
    period_sequences = serializers.ListField(
        child=serializers.IntegerField(min_value=1, max_value=99),
        min_length=1,
        max_length=20,
    )
    match = serializers.ChoiceField(choices=["ALL_ABSENT", "ANY_ABSENT"], default="ALL_ABSENT")
    grade_id = serializers.IntegerField(required=False, allow_null=True)
    section_id = serializers.IntegerField(required=False, allow_null=True)
    page = serializers.IntegerField(min_value=1, default=1)
    page_size = serializers.ChoiceField(choices=[25, 50, 100], default=25)


class PeriodStatusSerializer(serializers.Serializer):
    sequence = serializers.IntegerField()
    status = serializers.ChoiceField(choices=["ABSENT", "LATE", "PRESENT"])


class AnalyticsStudentSerializer(serializers.Serializer):
    student_id = serializers.IntegerField()
    full_name = serializers.CharField()
    grade_name = serializers.CharField()
    section_name = serializers.CharField()
    period_statuses = PeriodStatusSerializer(many=True)
    # مؤشر بصمة الدخول (م8.5) — للمراجعة، لا يغير نتيجة الغياب
    morning_arrival = serializers.CharField(allow_null=True, required=False)


class IncompleteSectionSerializer(serializers.Serializer):
    section_id = serializers.IntegerField()
    section_name = serializers.CharField()
    grade_name = serializers.CharField()
    missing_sequences = serializers.ListField(child=serializers.IntegerField())
    reason = serializers.CharField()


class PeriodNameSerializer(serializers.Serializer):
    sequence = serializers.IntegerField()
    name = serializers.CharField()


class MultiPeriodSummarySerializer(serializers.Serializer):
    matching_students = serializers.IntegerField()
    complete_sections = serializers.IntegerField()
    incomplete_sections = serializers.IntegerField()


class MultiPeriodResponseSerializer(serializers.Serializer):
    date = serializers.DateField()
    periods = PeriodNameSerializer(many=True)
    match = serializers.CharField()
    summary = MultiPeriodSummarySerializer()
    students = AnalyticsStudentSerializer(many=True)
    incomplete_sections = IncompleteSectionSerializer(many=True)
    day_periods = PeriodNameSerializer(many=True)
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    total_students = serializers.IntegerField()


class DailySummaryKpisSerializer(serializers.Serializer):
    total_students = serializers.IntegerField()
    complete_students = serializers.IntegerField()
    incomplete_students = serializers.IntegerField()
    full_absent = serializers.IntegerField()
    partial_absent = serializers.IntegerField()
    no_absence = serializers.IntegerField()
    undetermined = serializers.IntegerField()
    late_students = serializers.IntegerField()
    late_occurrences = serializers.IntegerField()
    late_minutes = serializers.IntegerField()


class DailyStudentSerializer(serializers.Serializer):
    student_id = serializers.IntegerField()
    full_name = serializers.CharField()
    grade_name = serializers.CharField()
    section_name = serializers.CharField()
    absent_periods = serializers.IntegerField()
    late_periods = serializers.IntegerField()
    total_late_minutes = serializers.IntegerField()
    submitted_periods = serializers.IntegerField()
    expected_periods = serializers.IntegerField()


class DailyResponseSerializer(serializers.Serializer):
    date = serializers.DateField()
    is_school_day = serializers.BooleanField()
    expected_periods = serializers.IntegerField()
    day_periods = PeriodNameSerializer(many=True)
    summary = DailySummaryKpisSerializer()
    students = DailyStudentSerializer(many=True)
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    total_students_filtered = serializers.IntegerField()


# ---- لوحة المتابعة (م7) — إخراج فقط، الاشتقاق كله في selectors/monitoring ----


class MonitoringAlertSerializer(serializers.Serializer):
    minutes = serializers.IntegerField()
    alert_at = serializers.CharField()


class MonitoringSummarySerializer(serializers.Serializer):
    total = serializers.IntegerField()
    submitted = serializers.IntegerField()
    in_progress = serializers.IntegerField()
    not_started = serializers.IntegerField()
    overdue_total = serializers.IntegerField()
    overdue_submitted = serializers.IntegerField()
    overdue_in_progress = serializers.IntegerField()
    overdue_not_started = serializers.IntegerField()


class MonitoringSectionSerializer(serializers.Serializer):
    section_id = serializers.IntegerField()
    section_name = serializers.CharField()
    grade_id = serializers.IntegerField()
    grade_name = serializers.CharField()
    students_count = serializers.IntegerField()
    attendance_status = serializers.ChoiceField(
        choices=["SUBMITTED", "IN_PROGRESS", "NOT_STARTED"]
    )
    timeliness_status = serializers.ChoiceField(choices=["ON_TIME", "OVERDUE"])
    started_at = serializers.CharField(allow_null=True)
    submitted_at = serializers.CharField(allow_null=True)
    minutes_overdue = serializers.IntegerField(allow_null=True)
    teacher_name = serializers.CharField(allow_null=True)
    session_id = serializers.IntegerField(allow_null=True)


class MonitoringResponseSerializer(serializers.Serializer):
    school_time = serializers.DateTimeField()
    date = serializers.DateField()
    period = PeriodSerializer(allow_null=True)
    alert = MonitoringAlertSerializer(allow_null=True)
    summary = MonitoringSummarySerializer(allow_null=True)
    sections = MonitoringSectionSerializer(many=True)


def serialize_session(session: AttendanceSession, roster: list[dict], *, can_edit: bool) -> dict:
    submitter = None
    if session.submitted_by_membership_id:
        profile = getattr(session.submitted_by_membership, "staff_profile", None)
        submitter = (
            profile.display_name
            if profile
            else session.submitted_by_membership.user.display_name
        )
    snapshot = session.bell_period_snapshot
    return {
        "id": session.id,
        "status": session.status,
        "attendance_date": session.attendance_date.isoformat(),
        "section": {
            "id": session.section.id,
            "name": session.section.name,
            "grade_name": session.section.grade.name,
            "students_count": len(roster),
        },
        "period": {
            "sequence": snapshot["sequence"],
            "name": snapshot["name"],
            "start_time": snapshot["start_time"],
            "end_time": snapshot["end_time"],
        },
        "submitted_by": submitter,
        "submitted_at": session.submitted_at.isoformat() if session.submitted_at else None,
        "can_edit": can_edit,
        "roster": roster,
        "marks": [
            {
                "student_id": m.student_id,
                "status": m.status,
                "arrival_time": m.arrival_time.strftime("%H:%M") if m.arrival_time else None,
                "late_minutes": m.late_minutes,
            }
            for m in session.marks.all()
        ],
    }
