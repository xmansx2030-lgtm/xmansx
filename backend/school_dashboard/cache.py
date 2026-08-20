"""تخزين مؤقت قصير للوحة الإدارة.

قاعدة أمنية أولى: **مفتاح الكاش يبدأ بمعرف المدرسة دائمًا** (بند 68/69/91).
لا يمكن لطلب مدرسة أن يقرأ نتيجة مدرسة أخرى ولو تطابقت بقية المعاملات، ولا
لدور أن يقرأ نتيجة دور آخر إن كان النطاق يعتمد الدور.

آجال قصيرة عمدًا بدل نظام إبطال معقد (بند 71) — وهذا أيضًا ما يمنع عودة بيانات
طالب محذوف نهائيًا من الكاش بعد الحذف (بند 135).
"""

import hashlib
import json

from django.core.cache import cache

#: آجال قصيرة: التشغيل اليومي يتغير كل لحظة، والتاريخ أبطأ تغيرًا
TTL_TODAY = 15
TTL_OVERVIEW = 45
TTL_TREND = 180

_NAMESPACE = "dash"


def build_key(*, school_id: int, section: str, parts: dict) -> str:
    """مفتاح مستقر: المدرسة أولًا ثم بصمة بقية المعاملات."""
    payload = json.dumps(parts, sort_keys=True, ensure_ascii=False, default=str)
    digest = hashlib.sha256(payload.encode()).hexdigest()[:20]
    return f"{_NAMESPACE}:{school_id}:{section}:{digest}"


def cached(*, key: str, ttl: int, builder):
    """يعيد القيمة المخزنة أو يبنيها — بلا كاش عند ttl=0 (للاختبارات والتشخيص)."""
    if ttl <= 0:
        return builder()
    hit = cache.get(key)
    if hit is not None:
        return hit
    value = builder()
    cache.set(key, value, timeout=ttl)
    return value


def invalidate_school(school_id: int) -> None:
    """لا مسح انتقائي: الآجال القصيرة تكفي، والدالة موجودة للتوثيق والاختبار."""
    return None
