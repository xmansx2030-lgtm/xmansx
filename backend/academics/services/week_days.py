"""خدمات أيام الدراسة وربط الجداول — نفس BellSchedule يخدم عدة أيام بلا نسخ."""

from django.db import transaction

from academics.models import (
    BellSchedule,
    BellScheduleStatus,
    SchoolWeekDay,
    Weekday,
)
from audit.models import AuditAction
from audit.services import record_event
from common.errors import ApiError

from .live_schedule import publish_live_schedule_change

DEFAULT_SCHOOL_DAYS = {
    Weekday.SUNDAY,
    Weekday.MONDAY,
    Weekday.TUESDAY,
    Weekday.WEDNESDAY,
    Weekday.THURSDAY,
}


def get_or_bootstrap_week_days(*, school) -> list[SchoolWeekDay]:
    """يضمن وجود 7 صفوف للمدرسة (افتراضي: الأحد–الخميس أيام دراسة)."""
    existing = {wd.weekday: wd for wd in SchoolWeekDay.objects.filter(school=school)}
    missing = [
        SchoolWeekDay(
            school=school, weekday=day, is_school_day=(day in DEFAULT_SCHOOL_DAYS)
        )
        for day in Weekday.values
        if day not in existing
    ]
    if missing:
        SchoolWeekDay.objects.bulk_create(missing, ignore_conflicts=True)
    return list(
        SchoolWeekDay.objects.filter(school=school)
        .select_related("bell_schedule")
        .order_by("weekday")
    )


@transaction.atomic
def update_week_days(*, school, actor, items: list[dict], request=None) -> list[SchoolWeekDay]:
    """تحديث أيام الدراسة وربط الجداول — يرفض جدول مدرسة أخرى (cross-school FK)."""
    get_or_bootstrap_week_days(school=school)

    schedule_ids = {i["bell_schedule_id"] for i in items if i.get("bell_schedule_id")}
    valid_schedules = {
        s.id: s
        for s in BellSchedule.objects.filter(school=school, id__in=schedule_ids).exclude(
            status=BellScheduleStatus.ARCHIVED
        )
    }
    for item in items:
        sid = item.get("bell_schedule_id")
        if sid and sid not in valid_schedules:
            # جدول غير موجود أو تابع لمدرسة أخرى أو مؤرشف — نفس الرد (لا تسريب)
            raise ApiError(
                "VALIDATION_ERROR", "جدول الحصص المحدد غير صالح.", status_code=400
            )

    changed = []
    locked = SchoolWeekDay.objects.select_for_update().filter(school=school)
    rows = {wd.weekday: wd for wd in locked}
    for item in items:
        row = rows.get(item["weekday"])
        if row is None:
            continue
        new_is_day = item.get("is_school_day", row.is_school_day)
        new_schedule_id = item.get("bell_schedule_id") if new_is_day else None
        if row.is_school_day != new_is_day or row.bell_schedule_id != new_schedule_id:
            changed.append(
                {
                    "weekday": row.weekday,
                    "is_school_day": [row.is_school_day, new_is_day],
                    "bell_schedule_id": [row.bell_schedule_id, new_schedule_id],
                }
            )
            row.is_school_day = new_is_day
            row.bell_schedule_id = new_schedule_id
            row.save(update_fields=["is_school_day", "bell_schedule", "updated_at"])

    if changed:
        record_event(
            AuditAction.SCHOOL_DAY_SCHEDULE_CHANGED,
            request=request,
            actor=actor,
            school=school,
            metadata={"changed": changed},
        )
        publish_live_schedule_change(school_id=school.id)
    return list(
        SchoolWeekDay.objects.filter(school=school)
        .select_related("bell_schedule")
        .order_by("weekday")
    )
