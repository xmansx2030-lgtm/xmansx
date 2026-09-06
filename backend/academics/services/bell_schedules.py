"""خدمات جداول الحصص — التحقق من التسلسل والأوقات والتداخل، والاستبدال الذري.

حماية مستقبلية (المرحلة 6+): عندما توجد AttendanceSessions مرتبطة بالحصص،
يجب أن يرفض replace_schedule_periods حذف حصص مستخدمة تاريخيًا — الحضور سيأخذ
snapshot كاملًا (ADR-010) لذا التاريخ لن يعتمد على هذه الصفوف، لكن سياسة الحذف
ستراجع عند بناء الحضور. هذا موثق هنا عمدًا.
"""

from django.db import transaction

from academics.models import (
    BellPeriod,
    BellSchedule,
    BellScheduleStatus,
    SchoolWeekDay,
)
from audit.models import AuditAction
from audit.services import record_event
from common.errors import ApiError

from .live_schedule import publish_live_schedule_change


def create_schedule(
    *, school, actor, name: str, valid_from=None, valid_to=None, request=None
) -> BellSchedule:
    if not name.strip():
        raise ApiError("VALIDATION_ERROR", "اسم الجدول مطلوب.")
    schedule = BellSchedule.objects.create(
        school=school, name=name.strip(), valid_from=valid_from, valid_to=valid_to
    )
    record_event(
        AuditAction.BELL_SCHEDULE_CREATED,
        request=request,
        actor=actor,
        school=school,
        target_type="BellSchedule",
        target_id=schedule.id,
        metadata={"name": schedule.name},
    )
    return schedule


def update_schedule(*, schedule: BellSchedule, actor, data: dict, request=None) -> BellSchedule:
    changed = {}
    for field in ("name", "status", "valid_from", "valid_to"):
        if field in data and data[field] != getattr(schedule, field):
            changed[field] = {"from": str(getattr(schedule, field)), "to": str(data[field])}
            setattr(schedule, field, data[field])
    if changed:
        schedule.save()
        record_event(
            AuditAction.BELL_SCHEDULE_UPDATED,
            request=request,
            actor=actor,
            school=schedule.school,
            target_type="BellSchedule",
            target_id=schedule.id,
            metadata={"changed": changed},
        )
        publish_live_schedule_change(school_id=schedule.school_id)
    return schedule


@transaction.atomic
def archive_schedule(*, schedule: BellSchedule, actor, request=None) -> BellSchedule:
    """أرشفة (لا حذف) + فك ارتباط الجدول من أيام الأسبوع."""
    schedule.status = BellScheduleStatus.ARCHIVED
    schedule.save(update_fields=["status", "updated_at"])
    SchoolWeekDay.objects.filter(school=schedule.school_id, bell_schedule=schedule).update(
        bell_schedule=None
    )
    record_event(
        AuditAction.BELL_SCHEDULE_ARCHIVED,
        request=request,
        actor=actor,
        school=schedule.school,
        target_type="BellSchedule",
        target_id=schedule.id,
    )
    publish_live_schedule_change(school_id=schedule.school_id)
    return schedule


def _validate_periods(periods: list[dict]) -> None:
    sequences = [p["sequence"] for p in periods]
    if len(sequences) != len(set(sequences)):
        raise ApiError("DUPLICATE_PERIOD_SEQUENCE", "يوجد تكرار في ترتيب الحصص.")

    for p in periods:
        if p["end_time"] <= p["start_time"]:
            raise ApiError(
                "INVALID_BELL_PERIOD_TIME",
                f"وقت نهاية «{p['name']}» يجب أن يكون بعد وقت بدايتها.",
            )

    # منع التداخل بين كل الفترات (حصص وفسح) داخل الجدول نفسه
    ordered = sorted(periods, key=lambda p: p["start_time"])
    for previous, current in zip(ordered, ordered[1:], strict=False):
        if current["start_time"] < previous["end_time"]:
            raise ApiError(
                "BELL_PERIOD_OVERLAP",
                f"تداخل في الأوقات بين «{previous['name']}» و«{current['name']}».",
            )


@transaction.atomic
def replace_schedule_periods(
    *, schedule: BellSchedule, actor, periods: list[dict], request=None
) -> list[BellPeriod]:
    """استبدال كامل لحصص الجدول (واجهة التحرير ترسل الجدول كاملًا).

    Phase 3: لا Attendance بعد فالحذف آمن. لاحقًا: الحضور يأخذ snapshot
    (ADR-010) ولا يعاد بناء التاريخ من هذه الصفوف.
    """
    _validate_periods(periods)
    schedule.periods.all().delete()
    created = BellPeriod.objects.bulk_create(
        BellPeriod(
            school=schedule.school,  # denormalized من الجدول — لا يقبل من العميل
            bell_schedule=schedule,
            sequence=p["sequence"],
            name=p["name"],
            start_time=p["start_time"],
            end_time=p["end_time"],
            is_attendance_period=p.get("is_attendance_period", True),
        )
        for p in sorted(periods, key=lambda p: p["sequence"])
    )
    record_event(
        AuditAction.BELL_SCHEDULE_UPDATED,
        request=request,
        actor=actor,
        school=schedule.school,
        target_type="BellSchedule",
        target_id=schedule.id,
        metadata={"periods_count": len(created)},
    )
    publish_live_schedule_change(school_id=schedule.school_id)
    return created
