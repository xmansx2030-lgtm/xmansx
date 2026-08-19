"""استقبال دفعات أحداث الأجهزة — idempotent، والنتيجة لكل حدث (بلا PII طلاب).

الحمايات: هوية المدرسة من الجسر الموثق؛ جهاز مدرسة أخرى يرفض (invalid)؛ طابع زمني
مستقبلي يرفض (تلاعب/replay)؛ مفتاح UNIQUE يمنع مضاعفة الحدث ولو أعيد إرساله 5 مرات.

الأداء: جلب مسبق للمفاتيح والهويات (استعلامان للدفعة كلها)، وتطبيق الوصول مرة
واحدة لكل (طالب، يوم) بأقدم حدث في الدفعة — لا معالجة لكل بصمة على حدة.
"""

import hashlib
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone as dj_timezone

from devices.models import (
    AttendanceDevice,
    DeviceEvent,
    EventProcessingStatus,
    IdentityStatus,
    StudentDeviceIdentity,
    VerificationMethod,
)
from devices.services.morning import apply_arrival_event, apply_arrival_events_bulk

MAX_BATCH_SIZE = 1000
FUTURE_SKEW = timedelta(minutes=10)  # سماحية انحراف ساعة الجهاز


def _dedupe_key(event: dict) -> str:
    external_id = (event.get("external_event_id") or "").strip()
    if external_id:
        return f"ext:{external_id}"
    # بصمة حتمية عند غياب معرف للحدث — التصادم يعني نفس (مستخدم، لحظة، نوع)
    # على نفس الجهاز = نفس الحدث فعليًا
    payload = "|".join(
        [
            str(event.get("external_user_id", "")),
            str(event.get("occurred_at", "")),
            str(event.get("event_type", "CHECK_IN")),
        ]
    )
    return "fp:" + hashlib.sha256(payload.encode()).hexdigest()


def ingest_batch(*, bridge, events: list[dict]) -> list[dict]:
    """يعالج دفعة أحداث ويعيد نتيجة لكل حدث: accepted/duplicate/invalid/unmatched."""
    now = dj_timezone.now()
    school = bridge.school
    devices = {
        d.id: d for d in AttendanceDevice.objects.filter(school=school, is_active=True)
    }
    events = events[:MAX_BATCH_SIZE]

    # (1) تحقق أولي + مفاتيح التكرار
    prepared: list[tuple[int, dict, str] | None] = []
    keys_by_device: dict[int, set[str]] = {}
    results: list[dict | None] = []
    for event in events:
        device = devices.get(event.get("device_id"))
        if device is None:
            # جهاز غير موجود أو تابع لمدرسة أخرى — نفس الرد (لا استكشاف)
            results.append({"result": "invalid", "reason": "unknown_device"})
            prepared.append(None)
            continue
        occurred_at = event.get("occurred_at")
        external_user_id = str(event.get("external_user_id", "")).strip()
        if occurred_at is None or not external_user_id:
            results.append({"result": "invalid", "reason": "missing_fields"})
            prepared.append(None)
            continue
        if occurred_at > now + FUTURE_SKEW:
            results.append({"result": "invalid", "reason": "future_timestamp"})
            prepared.append(None)
            continue
        key = _dedupe_key(event)[:128]
        keys_by_device.setdefault(device.id, set()).add(key)
        prepared.append((device.id, event, key))
        results.append(None)  # تحدد لاحقًا

    # (2) المكرر المعروف مسبقًا — استعلام واحد لكل الدفعة
    existing_keys: set[tuple[int, str]] = set()
    for device_id, keys in keys_by_device.items():
        existing_keys.update(
            (device_id, k)
            for k in DeviceEvent.objects.filter(
                device_id=device_id, dedupe_key__in=list(keys)
            ).values_list("dedupe_key", flat=True)
        )

    # (3) الهويات دفعة واحدة
    external_ids = {
        (item[0], str(item[1]["external_user_id"]).strip()[:64])
        for item in prepared
        if item is not None
    }
    identities = {
        (i.device_id, i.external_user_id): i
        for i in StudentDeviceIdentity.objects.filter(
            device_id__in={d for d, _ in external_ids},
            external_user_id__in={u for _, u in external_ids},
        ).select_related("student")
    }

    # (4) بناء الأحداث الجديدة (النتيجة لكل حدث تحدد هنا)
    unmatched_to_create: set[tuple[int, str]] = set()
    touched: set[int] = set()
    seen_in_batch: set[tuple[int, str]] = set()
    new_rows: list[tuple[int, DeviceEvent]] = []  # (result_index, row)

    for index, item in enumerate(prepared):
        if item is None:
            continue
        device_id, event, key = item
        if (device_id, key) in existing_keys or (device_id, key) in seen_in_batch:
            results[index] = {"result": "duplicate"}
            continue
        seen_in_batch.add((device_id, key))
        external_user_id = str(event["external_user_id"]).strip()[:64]
        method = event.get("verification_method", "UNKNOWN")
        if method not in VerificationMethod.values:
            method = VerificationMethod.UNKNOWN
        row = DeviceEvent(
            school=school,
            device_id=device_id,
            external_event_id=(event.get("external_event_id") or "")[:100],
            dedupe_key=key,
            external_user_id=external_user_id,
            occurred_at=event["occurred_at"],
            verification_method=method,
            event_type=str(event.get("event_type", "CHECK_IN"))[:20],
        )
        identity = identities.get((device_id, external_user_id))
        if identity is None or identity.status != IdentityStatus.MATCHED:
            row.processing_status = EventProcessingStatus.UNMATCHED
            if identity is None:
                unmatched_to_create.add((device_id, external_user_id))
            results[index] = {"result": "unmatched"}
        elif identity.student.status != "ACTIVE":
            row.student = identity.student
            row.processing_status = EventProcessingStatus.IGNORED
            results[index] = {"result": "accepted"}
        else:
            row.student = identity.student
            row.processing_status = EventProcessingStatus.PROCESSED
            results[index] = {"result": "accepted"}
        new_rows.append((index, row))
        touched.add(device_id)

    # (5) إدراج دفعة واحدة — سباق متزامن نادر يسقط للفردي (savepoint لكل صف)
    inserted: list[DeviceEvent] = []
    if new_rows:
        try:
            with transaction.atomic():
                DeviceEvent.objects.bulk_create([row for _, row in new_rows])
            inserted = [row for _, row in new_rows]
        except IntegrityError:
            for index, row in new_rows:
                row.pk = None
                try:
                    with transaction.atomic():
                        row.save()
                    inserted.append(row)
                except IntegrityError:
                    results[index] = {"result": "duplicate"}

    # (6) الوصول: أقدم حدث لكل (طالب، يوم) — دفعة واحدة (استعلامات شبه ثابتة)
    apply_arrival_events_bulk(
        school=school,
        items=[
            (row.student_id, row.occurred_at, row)
            for row in inserted
            if row.processing_status == EventProcessingStatus.PROCESSED
            and row.event_type == "CHECK_IN"
        ],
    )

    # (7) صفوف هوية غير مطابقة للمعالجة اليدوية لاحقًا
    if unmatched_to_create:
        StudentDeviceIdentity.objects.bulk_create(
            (
                StudentDeviceIdentity(
                    school=school, device_id=d, external_user_id=u
                )
                for d, u in unmatched_to_create
            ),
            ignore_conflicts=True,
        )
    if touched:
        for device_id in touched:
            devices[device_id].last_seen_at = now
            devices[device_id].last_successful_sync_at = now
        AttendanceDevice.objects.bulk_update(
            [devices[i] for i in touched], ["last_seen_at", "last_successful_sync_at"]
        )
    return [r or {"result": "invalid", "reason": "unknown"} for r in results]


def reprocess_unmatched(*, identity: StudentDeviceIdentity) -> int:
    """بعد مطابقة هوية: يعالج أحداثها غير المطابقة القديمة بالترتيب الزمني."""
    if identity.status != IdentityStatus.MATCHED or identity.student_id is None:
        return 0
    events = list(
        DeviceEvent.objects.filter(
            device=identity.device,
            external_user_id=identity.external_user_id,
            processing_status=EventProcessingStatus.UNMATCHED,
        ).order_by("occurred_at")
    )
    student = identity.student
    for event_row in events:
        if student.status != "ACTIVE":
            event_row.processing_status = EventProcessingStatus.IGNORED
            event_row.student = student
            event_row.save(update_fields=["processing_status", "student", "updated_at"])
            continue
        event_row.student = student
        event_row.processing_status = EventProcessingStatus.PROCESSED
        event_row.save(update_fields=["student", "processing_status", "updated_at"])
        if event_row.event_type == "CHECK_IN":
            apply_arrival_event(
                school=event_row.school,
                student=student,
                occurred_at=event_row.occurred_at,
                device_event=event_row,
            )
    return len(events)
