"""الاستحقاقات: مصدر واحد للحدود والميزات (بنود 23-25).

ممنوع في كل المشروع: `if plan.code == "PRO"`. القرار من المفتاح لا من اسم الباقة.
الحدود تُقرأ من **لقطة العقد** لا من الباقة الحالية، فتعديل الباقة لا يغير عقدًا قائمًا.
"""

from django.core.cache import cache
from django.db import transaction

from common.errors import ApiError
from subscriptions.access import live_subscription
from subscriptions.models import (
    NUMERIC_ENTITLEMENTS,
    EntitlementKey,
    SubscriptionEntitlement,
)

#: أجل قصير: الترقية يجب أن تظهر بسرعة، والإبطال الصريح يسبقه على أي حال
ENTITLEMENT_TTL = 60

_NAMESPACE = "entl"


def _cache_key(school_id: int, subscription_id: int, version: str) -> str:
    return f"{_NAMESPACE}:school:{school_id}:subscription:{subscription_id}:{version}"


def _pointer_key(school_id: int) -> str:
    return f"{_NAMESPACE}:school:{school_id}:current"


def _version(subscription) -> str:
    """يتغير مع كل تعديل على العقد — ترقية اليوم لا تُقرأ بحدود الأمس."""
    return subscription.updated_at.isoformat()


def get_school_entitlements(school) -> dict:
    """كل استحقاقات المدرسة الحالية: {key: {"numeric": int|None, "enabled": bool}}."""
    pointer_key = _pointer_key(school.id)
    value_key = cache.get(pointer_key)
    expected_prefix = f"{_NAMESPACE}:school:{school.id}:subscription:"
    if isinstance(value_key, str) and value_key.startswith(expected_prefix):
        cached = cache.get(value_key)
        if cached is not None:
            return cached
    elif value_key is not None:
        cache.delete(pointer_key)

    subscription = live_subscription(school)
    if subscription is None:
        return {}
    key = _cache_key(school.id, subscription.id, _version(subscription))
    cached = cache.get(key)
    if cached is not None:
        return cached
    rows = SubscriptionEntitlement.objects.filter(subscription=subscription)
    value = {
        row.key: {"numeric": row.numeric_value, "enabled": row.is_enabled} for row in rows
    }
    cache.set_many({key: value, pointer_key: key}, timeout=ENTITLEMENT_TTL)
    return value


def invalidate_school_entitlements(school) -> None:
    """يبطل المؤشر والقيمة قبل التعديل وبعد تثبيت المعاملة."""
    pointer_key = _pointer_key(school.id)
    expected_prefix = f"{_NAMESPACE}:school:{school.id}:subscription:"

    def clear() -> None:
        value_key = cache.get(pointer_key)
        keys = [pointer_key]
        if isinstance(value_key, str) and value_key.startswith(expected_prefix):
            keys.append(value_key)
        cache.delete_many(keys)

    clear()
    transaction.on_commit(clear)


def has_entitlement(school, key: str) -> bool:
    """ميزة منطقية: غياب المفتاح = مسموح (لا نعطل ميزة قائمة بصمت — بند 78)."""
    entry = get_school_entitlements(school).get(key)
    if entry is None:
        return True
    return bool(entry["enabled"])


def get_limit(school, key: str) -> int | None:
    """حد رقمي — None تعني بلا حد."""
    if key not in NUMERIC_ENTITLEMENTS:
        raise ValueError(f"{key} ليس حدًا رقميًا")
    entry = get_school_entitlements(school).get(key)
    if entry is None:
        return None
    return entry["numeric"]


def require_feature(school, key: str) -> None:
    """بوابة خادمية للميزة — إخفاء القائمة في الواجهة ليس حماية (بند 75)."""
    if not has_entitlement(school, key):
        raise ApiError(
            "FEATURE_NOT_INCLUDED_IN_PLAN",
            f"هذه الميزة غير مشمولة في باقة المدرسة ({EntitlementKey(key).label}).",
            status_code=403,
        )


#: رمز الخطأ لكل حد — رسالة واضحة بدل رفض عام
_LIMIT_ERRORS = {
    EntitlementKey.MAX_STUDENTS: ("STUDENT_LIMIT_EXCEEDED", "عدد الطلاب"),
    EntitlementKey.MAX_STAFF: ("STAFF_LIMIT_EXCEEDED", "عدد الموظفين"),
    EntitlementKey.MAX_DEVICES: ("DEVICE_LIMIT_EXCEEDED", "عدد الأجهزة"),
    EntitlementKey.MAX_STORAGE_GB: ("STORAGE_LIMIT_EXCEEDED", "سعة التخزين"),
}


def require_capacity(school, key: str, *, current: int, adding: int = 1) -> None:
    """يمنع التجاوز عند الإضافة فقط — الموجود فوق الحد لا يُحذف ولا يُعطل (بنود 80-82)."""
    limit = get_limit(school, key)
    if limit is None:
        return
    if current + adding <= limit:
        return
    code, label = _LIMIT_ERRORS[key]
    raise ApiError(
        code,
        f"تجاوز {label} حد الباقة ({current + adding} من {limit}). يرجى ترقية الباقة.",
        status_code=409,
        details={"limit": limit, "current": current, "requested": adding},
    )


def require_storage_capacity(school, *, adding_bytes: int) -> None:
    """حد التخزين يُعرّف بالجيجابايت لكنه يُفرض بالبايت عند الرفع/التوليد."""
    limit_gb = get_limit(school, EntitlementKey.MAX_STORAGE_GB)
    if limit_gb is None:
        return

    from subscriptions.usage import BYTES_PER_GB, storage_used_bytes

    current = storage_used_bytes(school)
    requested_total = current + adding_bytes
    limit_bytes = limit_gb * BYTES_PER_GB
    if requested_total <= limit_bytes:
        return
    raise ApiError(
        "STORAGE_LIMIT_EXCEEDED",
        "تجاوزت ملفات المدرسة حد التخزين في الباقة. يرجى ترقية الباقة.",
        status_code=409,
        details={
            "limit_bytes": limit_bytes,
            "current_bytes": current,
            "requested_bytes": adding_bytes,
        },
    )
