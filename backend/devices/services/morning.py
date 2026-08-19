"""حساب الوصول الصباحي والتأخر — خادميًا حصرًا (الجسر يرسل occurred_at فقط).

السياسات الموثقة:
- ‏raw = دقائق ما بعد بداية الدوام (floor، ≥0)؛ counted = max(raw − grace, 0).
- الحد: ‏arrival <= start + grace يعني ON_TIME (‏07:05:00 مع سماح 5 = في الوقت).
- أول بصمة تحدد first_arrival_at؛ حدث **أقدم** يصل متأخرًا (مزامنة offline) يصحح
  الوصول ويعيد الحساب — بصمة لاحقة في نفس اليوم لا تنشئ تأخرًا ثانيًا.
- الدقائق تخزن — تغيير إعدادات الدوام لا يعيد كتابة أيام مضت.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.db import IntegrityError, transaction
from django.utils import timezone as dj_timezone

from audit.models import AuditAction
from audit.services import record_event
from common.errors import ApiError
from devices.models import (
    ArrivalSource,
    ArrivalStatus,
    SchoolArrival,
    SchoolArrivalChange,
)
from schools.services.settings import get_or_create_settings


def compute_lateness(*, settings_obj, arrival_at: datetime, attendance_date) -> dict:
    tz = ZoneInfo(settings_obj.timezone)
    start = datetime.combine(attendance_date, settings_obj.school_day_start_time, tzinfo=tz)
    grace = settings_obj.morning_late_grace_minutes
    delta_seconds = (arrival_at - start).total_seconds()
    raw = max(int(delta_seconds // 60), 0)
    on_time = arrival_at <= start + timedelta(minutes=grace)
    counted = 0 if on_time else max(raw - grace, 0)
    return {
        "raw_late_minutes": raw,
        "counted_late_minutes": counted,
        "status": ArrivalStatus.ON_TIME if on_time else ArrivalStatus.LATE,
    }


def apply_arrival_events_bulk(*, school, items: list[tuple]) -> None:
    """يطبق أقدم حدث لكل (طالب، يوم) دفعة واحدة — items: (student_id, occurred_at, event).

    استعلامات شبه ثابتة: جلب القائم مرة، إنشاء الجديد bulk، وتصحيح الأقدم فرديًا
    (نادر — مزامنة offline متأخرة فقط).
    """
    if not items:
        return
    settings_obj = get_or_create_settings(school=school)
    tz = ZoneInfo(settings_obj.timezone)

    earliest: dict[tuple[int, object], tuple] = {}
    for student_id, occurred_at, event in items:
        key = (student_id, occurred_at.astimezone(tz).date())
        current = earliest.get(key)
        if current is None or occurred_at < current[1]:
            earliest[key] = (student_id, occurred_at, event)

    dates = {key[1] for key in earliest}
    student_ids = {key[0] for key in earliest}
    with transaction.atomic():
        existing = {
            (a.student_id, a.attendance_date): a
            for a in SchoolArrival.objects.select_for_update().filter(
                school=school,
                attendance_date__in=list(dates),
                student_id__in=list(student_ids),
            )
        }
        to_create = []
        for (student_id, day), (_, occurred_at, event) in earliest.items():
            local = occurred_at.astimezone(tz)
            arrival = existing.get((student_id, day))
            if arrival is None:
                fields = compute_lateness(
                    settings_obj=settings_obj, arrival_at=local, attendance_date=day
                )
                to_create.append(
                    SchoolArrival(
                        school=school, student_id=student_id, attendance_date=day,
                        first_arrival_at=occurred_at, source=ArrivalSource.BIOMETRIC,
                        device_event=event, **fields,
                    )
                )
            elif occurred_at < arrival.first_arrival_at:
                # الحدث الأقدم هو الوصول الفعلي — تصحيح وإعادة حساب
                fields = compute_lateness(
                    settings_obj=settings_obj, arrival_at=local, attendance_date=day
                )
                arrival.first_arrival_at = occurred_at
                arrival.source = ArrivalSource.BIOMETRIC
                arrival.device_event = event
                for field_name, value in fields.items():
                    setattr(arrival, field_name, value)
                arrival.save()
        if to_create:
            SchoolArrival.objects.bulk_create(to_create, ignore_conflicts=True)


def apply_arrival_event(*, school, student, occurred_at: datetime, device_event=None):
    """يطبق حدث وصول: ينشئ سجل اليوم أو يصححه لو كان الحدث أقدم من المسجل."""
    settings_obj = get_or_create_settings(school=school)
    local = occurred_at.astimezone(ZoneInfo(settings_obj.timezone))
    attendance_date = local.date()

    with transaction.atomic():
        arrival = (
            SchoolArrival.objects.select_for_update()
            .filter(school=school, student=student, attendance_date=attendance_date)
            .first()
        )
        if arrival is None:
            fields = compute_lateness(
                settings_obj=settings_obj, arrival_at=local, attendance_date=attendance_date
            )
            try:
                return SchoolArrival.objects.create(
                    school=school,
                    student=student,
                    attendance_date=attendance_date,
                    first_arrival_at=occurred_at,
                    source=ArrivalSource.BIOMETRIC,
                    device_event=device_event,
                    **fields,
                )
            except IntegrityError:
                arrival = SchoolArrival.objects.select_for_update().get(
                    school=school, student=student, attendance_date=attendance_date
                )
        if occurred_at < arrival.first_arrival_at:
            # الحدث الأقدم هو الوصول الفعلي — تصحيح تلقائي وإعادة حساب
            fields = compute_lateness(
                settings_obj=settings_obj, arrival_at=local, attendance_date=attendance_date
            )
            arrival.first_arrival_at = occurred_at
            arrival.source = ArrivalSource.BIOMETRIC
            arrival.device_event = device_event
            for key, value in fields.items():
                setattr(arrival, key, value)
            arrival.save()
        return arrival


def create_manual_arrival(
    *, school, membership, student, attendance_date, arrival_time, reason: str, request=None
):
    """تسجيل وصول يدوي (وكيل/مدير) — بوابة أخرى/جهاز معطل/بصمة لم تعمل."""
    settings_obj = get_or_create_settings(school=school)
    tz = ZoneInfo(settings_obj.timezone)
    arrival_at = datetime.combine(attendance_date, arrival_time, tzinfo=tz)
    if SchoolArrival.objects.filter(
        school=school, student=student, attendance_date=attendance_date
    ).exists():
        raise ApiError(
            "ARRIVAL_ALREADY_EXISTS",
            "يوجد سجل وصول لهذا الطالب في هذا اليوم — استخدم «تصحيح وقت الوصول».",
            status_code=409,
        )
    fields = compute_lateness(
        settings_obj=settings_obj, arrival_at=arrival_at, attendance_date=attendance_date
    )
    arrival = SchoolArrival.objects.create(
        school=school,
        student=student,
        attendance_date=attendance_date,
        first_arrival_at=arrival_at,
        source=ArrivalSource.MANUAL,
        recorded_by_membership=membership,
        **fields,
    )
    record_event(
        AuditAction.MORNING_ARRIVAL_MANUAL_CREATED,
        request=request,
        actor=membership.user,
        school=school,
        target_type="SchoolArrival",
        target_id=arrival.id,
        metadata={"date": str(attendance_date), "reason": reason[:100]},  # لا اسم/هوية
    )
    return arrival


def correct_arrival(*, arrival, membership, new_time, reason: str, request=None):
    """تصحيح وقت وصول قائم — الحالة الحالية تتغير والتاريخ يحفظ في Change."""
    settings_obj = get_or_create_settings(school=arrival.school)
    tz = ZoneInfo(settings_obj.timezone)
    new_at = datetime.combine(arrival.attendance_date, new_time, tzinfo=tz)
    fields = compute_lateness(
        settings_obj=settings_obj, arrival_at=new_at, attendance_date=arrival.attendance_date
    )
    with transaction.atomic():
        SchoolArrivalChange.objects.create(
            school=arrival.school,
            arrival=arrival,
            actor_membership=membership,
            previous_arrival_time=arrival.first_arrival_at,
            new_arrival_time=new_at,
            previous_status=arrival.status,
            new_status=fields["status"],
            previous_counted_late_minutes=arrival.counted_late_minutes,
            new_counted_late_minutes=fields["counted_late_minutes"],
            reason=reason[:300],
        )
        arrival.first_arrival_at = new_at
        arrival.source = ArrivalSource.MANUAL
        arrival.recorded_by_membership = membership
        for key, value in fields.items():
            setattr(arrival, key, value)
        arrival.save()
    record_event(
        AuditAction.MORNING_ARRIVAL_CORRECTED,
        request=request,
        actor=membership.user,
        school=arrival.school,
        target_type="SchoolArrival",
        target_id=arrival.id,
        metadata={"date": str(arrival.attendance_date)},
    )
    return arrival


def now_utc() -> datetime:
    return dj_timezone.now()
