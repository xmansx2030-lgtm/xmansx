"""Morning attendance data for the student profile, separate from period attendance."""

from datetime import date

from django.db.models import Count, Q, Sum

from devices.models import ArrivalStatus, SchoolArrival
from students.models import Student, StudentEnrollment


def get_morning_profile_summary(
    *, school, student: Student, from_date: date, to_date: date
) -> dict:
    arrivals = SchoolArrival.objects.filter(
        school=school,
        student=student,
        attendance_date__range=(from_date, to_date),
    )
    totals = arrivals.aggregate(
        late_occurrences=Count("id", filter=Q(status=ArrivalStatus.LATE)),
        late_minutes=Sum("counted_late_minutes", filter=Q(status=ArrivalStatus.LATE)),
    )
    return {
        "status": "AVAILABLE",
        "morning_late_occurrences": totals["late_occurrences"] or 0,
        "morning_late_minutes": totals["late_minutes"] or 0,
    }


def get_morning_profile_history(*, school, student: Student, from_date: date, to_date: date):
    return SchoolArrival.objects.filter(
        school=school,
        student=student,
        attendance_date__range=(from_date, to_date),
    ).order_by("-attendance_date")


def serialize_morning_history(*, school, arrivals):
    if not arrivals:
        return []
    dates = [arrival.attendance_date for arrival in arrivals]
    enrollments = StudentEnrollment.objects.filter(
        school=school,
        student_id=arrivals[0].student_id,
        enrolled_at__lte=max(dates),
    ).filter(
        Q(ended_at__isnull=True) | Q(ended_at__gt=min(dates))
    ).select_related("grade", "section")
    result = []
    for arrival in arrivals:
        enrollment = next(
            (
                row for row in enrollments
                if row.enrolled_at <= arrival.attendance_date
                and (row.ended_at is None or row.ended_at > arrival.attendance_date)
            ),
            None,
        )
        result.append({
            "date": arrival.attendance_date,
            "arrival_time": arrival.first_arrival_at,
            "status": arrival.status,
            "raw_late_minutes": arrival.raw_late_minutes,
            "counted_late_minutes": arrival.counted_late_minutes,
            "source": arrival.source,
            "grade_name": enrollment.grade.name if enrollment else None,
            "section_name": enrollment.section.name if enrollment else None,
        })
    return result
