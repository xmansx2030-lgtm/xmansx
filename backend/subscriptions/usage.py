"""قياس الاستخدام الفعلي — استعلامات لا عدادات مخزنة (بنود 59-61).

تعريف موثق:
- الطلاب: `ACTIVE` فقط. المتخرج/المنقول/المنسحب تاريخ لا يستهلك مقعدًا (بند 65).
- الموظفون: عضويات فعالة داخل هذه المدرسة — المستخدم في مدرستين يُحسب مرة هنا (بند 67).
- الأجهزة: أجهزة الحضور المفعّلة.
- التخزين: ملفات تملكها المدرسة (مرفقات الأعذار + المستندات المولدة).
"""

from django.db.models import Sum

from subscriptions.entitlements import get_school_entitlements
from subscriptions.models import EntitlementKey

BYTES_PER_GB = 1024**3
NEAR_LIMIT_RATIO = 0.8


def count_active_students(school) -> int:
    from students.models import Student, StudentStatus

    return Student.objects.filter(school=school, status=StudentStatus.ACTIVE).count()


def count_active_staff(school) -> int:
    from memberships.models import MembershipStatus, SchoolMembership

    return SchoolMembership.objects.filter(
        school=school, status=MembershipStatus.ACTIVE
    ).count()


def count_active_devices(school) -> int:
    from devices.models import AttendanceDevice

    return AttendanceDevice.objects.filter(school=school, is_active=True).count()


def storage_used_bytes(school) -> int:
    """مرفقات الأعذار (حجم مخزّن) + المستندات المولدة — لا أصول النظام المشتركة (بند 72)."""
    from documents.models import GeneratedDocument
    from excuses.models import AbsenceExcuseAttachment

    attachments = (
        AbsenceExcuseAttachment.objects.filter(school=school).aggregate(
            total=Sum("size_bytes")
        )["total"]
        or 0
    )
    documents = (
        GeneratedDocument.objects.filter(school=school).aggregate(total=Sum("size_bytes"))[
            "total"
        ]
        or 0
    )
    return int(attachments) + int(documents)


def _entry(used: int, limit: int | None) -> dict:
    over_limit = limit is not None and used > limit
    return {
        "used": used,
        "limit": limit,
        # تجاوز الحد حالة تُعرض ولا تُعالج بالحذف (بند 70)
        "over_limit": over_limit,
        "near_limit": (
            limit is not None
            and limit > 0
            and not over_limit
            and used / limit >= NEAR_LIMIT_RATIO
        ),
        "remaining": None if limit is None else max(limit - used, 0),
    }


def student_capacity_preview(school, *, adding: int) -> dict:
    """سعة الطلاب في معاينة نور؛ تعرض التجاوز ولا تمنع بناء المعاينة."""
    entitlements = get_school_entitlements(school)
    entry = entitlements.get(EntitlementKey.MAX_STUDENTS)
    limit = entry["numeric"] if entry is not None else None
    used = count_active_students(school)
    projected = used + adding
    return {
        "used": used,
        "adding": adding,
        "projected": projected,
        "limit": limit,
        "over_limit": limit is not None and projected > limit,
    }


def get_school_usage(school) -> dict:
    """الاستخدام مقابل الحدود — عدد استعلامات ثابت مهما كبرت المدرسة."""
    entitlements = get_school_entitlements(school)

    def limit(key: str) -> int | None:
        entry = entitlements.get(key)
        return entry["numeric"] if entry is not None else None

    storage_limit_gb = limit(EntitlementKey.MAX_STORAGE_GB)
    storage_limit_bytes = (
        None if storage_limit_gb is None else storage_limit_gb * BYTES_PER_GB
    )
    used_bytes = storage_used_bytes(school)
    return {
        "students": _entry(
            count_active_students(school), limit(EntitlementKey.MAX_STUDENTS)
        ),
        "staff": _entry(
            count_active_staff(school), limit(EntitlementKey.MAX_STAFF)
        ),
        "devices": _entry(
            count_active_devices(school), limit(EntitlementKey.MAX_DEVICES)
        ),
        "storage": {
            **_entry(used_bytes, storage_limit_bytes),
            "used_gb": round(used_bytes / BYTES_PER_GB, 3),
            "limit_gb": storage_limit_gb,
        },
    }
