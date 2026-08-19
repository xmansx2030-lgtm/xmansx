"""تقارير الحضور الصباحي — بلا استنتاج غياب من غياب البصمة، وبلا N+1.

الفصل التاريخي للطالب من enrollments_on_date (م8) — النقل لاحقًا لا يغير تقارير
الماضي. الدقائق تعاد أرقامًا — الواجهة تحول (137 → ساعتان و17 دقيقة).
"""

from datetime import date as date_cls
from datetime import timedelta
from zoneinfo import ZoneInfo

from django.db.models import Count, Q, Sum
from django.utils import timezone as dj_timezone

from common.errors import ApiError
from devices.models import (
    OFFLINE_AFTER_MINUTES,
    ArrivalStatus,
    AttendanceDevice,
    DeviceEvent,
    DeviceStatus,
    EventProcessingStatus,
    SchoolArrival,
)
from schools.services.settings import get_or_create_settings
from students.services.enrollments import enrollments_on_date

MAX_HISTORY_DAYS = 400  # سنة دراسية وزيادة — لا Query مفتوحة لسنوات
PAGE_SIZES = (25, 50, 100)


def _paginate(items: list, page: int, page_size: int) -> tuple[list, int, int]:
    page = max(page, 1)
    if page_size not in PAGE_SIZES:
        page_size = PAGE_SIZES[0]
    start = (page - 1) * page_size
    return items[start : start + page_size], page, page_size


def _sections_map(school, on_date, student_ids):
    rows = (
        enrollments_on_date(school=school, on_date=on_date)
        .filter(student_id__in=student_ids)
        .select_related("grade", "section")
    )
    return {
        r.student_id: {"grade_name": r.grade.name, "section_name": r.section.name,
                       "grade_id": r.grade_id, "section_id": r.section_id}
        for r in rows
    }


def effective_device_status(device: AttendanceDevice, now=None) -> str:
    if not device.is_active or device.status == DeviceStatus.DISABLED:
        return DeviceStatus.DISABLED
    now = now or dj_timezone.now()
    if device.last_seen_at is None:
        return DeviceStatus.UNKNOWN
    if device.last_seen_at < now - timedelta(minutes=OFFLINE_AFTER_MINUTES):
        return DeviceStatus.OFFLINE
    return device.status if device.status != DeviceStatus.UNKNOWN else DeviceStatus.ONLINE


def get_morning_summary(*, school, attendance_date: date_cls) -> dict:
    arrivals = SchoolArrival.objects.filter(school=school, attendance_date=attendance_date)
    counts = arrivals.aggregate(
        total=Count("id"),
        on_time=Count("id", filter=Q(status=ArrivalStatus.ON_TIME)),
        late=Count("id", filter=Q(status=ArrivalStatus.LATE)),
        late_minutes=Sum("counted_late_minutes"),
    )
    unmatched_events = DeviceEvent.objects.filter(
        school=school, processing_status=EventProcessingStatus.UNMATCHED
    ).count()
    devices = list(AttendanceDevice.objects.filter(school=school))
    now = dj_timezone.now()
    offline = sum(
        1 for d in devices if effective_device_status(d, now) == DeviceStatus.OFFLINE
    )
    return {
        "date": attendance_date.isoformat(),
        "arrived_total": counts["total"],
        "on_time": counts["on_time"],
        "late": counts["late"],
        "late_minutes_total": counts["late_minutes"] or 0,
        "unmatched_events": unmatched_events,
        "devices_total": len(devices),
        "devices_offline": offline,
    }


def get_late_list(
    *,
    school,
    attendance_date: date_cls,
    grade_id=None,
    section_id=None,
    search: str = "",
    page: int = 1,
    page_size: int = 25,
) -> dict:
    settings_obj = get_or_create_settings(school=school)
    tz = ZoneInfo(settings_obj.timezone)
    arrivals = list(
        SchoolArrival.objects.filter(
            school=school, attendance_date=attendance_date, status=ArrivalStatus.LATE
        )
        .select_related("student")
        .order_by("-counted_late_minutes", "student__full_name")
    )
    sections = _sections_map(school, attendance_date, [a.student_id for a in arrivals])
    rows = []
    for arrival in arrivals:
        info = sections.get(arrival.student_id, {})
        if grade_id and info.get("grade_id") != grade_id:
            continue
        if section_id and info.get("section_id") != section_id:
            continue
        name = arrival.student.full_name
        if search and search.strip() not in name:
            continue
        rows.append(
            {
                "student_id": arrival.student_id,
                "full_name": name,
                "grade_name": info.get("grade_name", "—"),
                "section_name": info.get("section_name", "—"),
                "arrival_time": arrival.first_arrival_at.astimezone(tz).strftime("%H:%M"),
                "raw_late_minutes": arrival.raw_late_minutes,
                "counted_late_minutes": arrival.counted_late_minutes,
                "source": arrival.source,
            }
        )
    total = len(rows)
    page_rows, page, page_size = _paginate(rows, page, page_size)
    return {
        "date": attendance_date.isoformat(),
        "total_late": total,
        "students": page_rows,
        "page": page,
        "page_size": page_size,
    }


def get_student_late_history(
    *, school, student, date_from: date_cls, date_to: date_cls
) -> dict:
    if date_to < date_from:
        raise ApiError("VALIDATION_ERROR", "نهاية الفترة قبل بدايتها.")
    if (date_to - date_from).days > MAX_HISTORY_DAYS:
        raise ApiError("VALIDATION_ERROR", "الفترة المطلوبة أطول من المسموح.")
    settings_obj = get_or_create_settings(school=school)
    tz = ZoneInfo(settings_obj.timezone)
    arrivals = list(
        SchoolArrival.objects.filter(
            school=school,
            student=student,
            attendance_date__gte=date_from,
            attendance_date__lte=date_to,
            status=ArrivalStatus.LATE,
        ).order_by("-attendance_date")
    )
    total_minutes = sum(a.counted_late_minutes for a in arrivals)
    return {
        "student_id": student.id,
        "full_name": student.full_name,
        "from": date_from.isoformat(),
        "to": date_to.isoformat(),
        "late_count": len(arrivals),
        "total_late_minutes": total_minutes,
        "entries": [
            {
                "date": a.attendance_date.isoformat(),
                "arrival_time": a.first_arrival_at.astimezone(tz).strftime("%H:%M"),
                "raw_late_minutes": a.raw_late_minutes,
                "counted_late_minutes": a.counted_late_minutes,
                "source": a.source,
            }
            for a in arrivals
        ],
    }
