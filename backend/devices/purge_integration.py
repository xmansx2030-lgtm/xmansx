"""تسجيل بيانات الحضور الصباحي في دورة الحذف النهائي (إلزام المرحلة 4.1).

السياسة (البند 95 موثقة): حذف الطالب يحذف هويات أجهزته ووصولاته وتعديلاتها
**وأحداث الأجهزة المرتبطة به** — الحدث المرتبط + الهوية يعيدان التعرف على الطالب
عبر external_user_id فيحذفان معًا؛ الأحداث غير المطابقة (بلا student) تبقى تشغيلية.
الأجهزة والجسور تبقى (مستوى المدرسة بلا PII طلاب).
"""

from devices.models import (
    DeviceEvent,
    DeviceRosterSyncItem,
    SchoolArrival,
    SchoolArrivalChange,
    StudentDeviceIdentity,
)

_LABELS = {
    "roster_items": "عناصر مزامنة أجهزة الطالب",
    "identities": "هويات أجهزة الطالب",
    "events": "أحداث الأجهزة المرتبطة بالطالب",
    "changes": "تعديلات الوصول الصباحي",
    "arrivals": "الوصول الصباحي",
}


def register_purge_steps() -> None:
    from students.services import purge as purge_service

    existing = {label for label, _ in purge_service.PURGE_STEPS}
    if _LABELS["arrivals"] in existing:
        return  # idempotent

    steps = [
        (
            _LABELS["roster_items"],
            lambda ids: DeviceRosterSyncItem.objects.filter(student_id__in=ids),
        ),
        (
            _LABELS["changes"],
            lambda ids: SchoolArrivalChange.objects.filter(arrival__student_id__in=ids),
        ),
        (
            _LABELS["arrivals"],
            lambda ids: SchoolArrival.objects.filter(student_id__in=ids),
        ),
        (
            _LABELS["events"],
            lambda ids: DeviceEvent.objects.filter(student_id__in=ids),
        ),
        (
            _LABELS["identities"],
            lambda ids: StudentDeviceIdentity.objects.filter(student_id__in=ids),
        ),
    ]
    for step in reversed(steps):
        purge_service.PURGE_STEPS.insert(0, step)
