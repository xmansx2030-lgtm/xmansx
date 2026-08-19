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
