"""الحالة الفعالة وسياسة الوصول — مصدر الحقيقة الوحيد (بنود 119، 130-133).

قاعدة حاكمة: الحالة تُحسب من الوقت الفعلي لا من الحقل المخزّن وحده. توقف Celery
ساعتين لا يجعل اشتراكًا منتهيًا «نشطًا»، ولا يفتح مدرسة موقوفة.
"""

from django.utils import timezone as dj_timezone

from subscriptions.models import SchoolSubscription, SubscriptionStatus

#: أوضاع الوصول المعتمدة
FULL = "FULL"
READ_ONLY = "READ_ONLY"
BLOCKED = "BLOCKED"

#: الحالة الفعالة ← وضع الوصول (موثق في SUBSCRIPTION_ACCESS_POLICY.md)
ACCESS_MODES = {
    SubscriptionStatus.TRIAL: FULL,
    SubscriptionStatus.ACTIVE: FULL,
    SubscriptionStatus.GRACE_PERIOD: FULL,
    SubscriptionStatus.EXPIRED: READ_ONLY,
    SubscriptionStatus.CANCELLED: READ_ONLY,
    SubscriptionStatus.SUSPENDED: BLOCKED,
}

#: مدرسة بلا اشتراك إطلاقًا: تبقى مفتوحة للتوافق مع المدارس القائمة قبل م16.
# الاشتراكات الجديدة من لوحة المنصة تحصل على عقد صريح، أما بيانات ما قبل المرحلة
# فلا تُغلق فجأة بسبب غياب سجل تاريخي.
NO_SUBSCRIPTION_MODE = FULL


def live_subscription(school) -> SchoolSubscription | None:
    """العقد الحالي للمدرسة — الأحدث بدءًا، أيًا كانت حالته."""
    return (
        SchoolSubscription.objects.filter(school=school)
        .select_related("plan")
        .order_by("-starts_at", "-id")
        .first()
    )


def effective_status(subscription: SchoolSubscription | None, *, now=None) -> str | None:
    """الحالة الفعالة بحساب الوقت — لا تكتب في قاعدة البيانات.

    الإيقاف والإلغاء قراران إداريان لا يبطلهما مرور الوقت، فيُعادان كما هما.
    """
    if subscription is None:
        return None
    now = now or dj_timezone.now()
    stored = subscription.status
    if stored in (SubscriptionStatus.SUSPENDED, SubscriptionStatus.CANCELLED):
        return stored
    if stored == SubscriptionStatus.EXPIRED:
        return stored

    if stored == SubscriptionStatus.TRIAL:
        trial_end = subscription.trial_ends_at or subscription.ends_at
        if now < trial_end:
            return SubscriptionStatus.TRIAL
        return _after_end(subscription, now)

    if stored in (SubscriptionStatus.ACTIVE, SubscriptionStatus.GRACE_PERIOD):
        if now < subscription.ends_at:
            return SubscriptionStatus.ACTIVE
        return _after_end(subscription, now)

    return stored


def _after_end(subscription: SchoolSubscription, now) -> str:
    """بعد النهاية: مهلة سماح إن وُجدت ولم تنتهِ، وإلا منتهٍ."""
    if subscription.grace_ends_at is not None and now < subscription.grace_ends_at:
        return SubscriptionStatus.GRACE_PERIOD
    return SubscriptionStatus.EXPIRED


def get_school_access_mode(school, *, now=None) -> str:
    """وضع الوصول التشغيلي للمدرسة — نقطة القرار الوحيدة لكل الميزات."""
    subscription = live_subscription(school)
    status = effective_status(subscription, now=now)
    if status is None:
        return NO_SUBSCRIPTION_MODE
    return ACCESS_MODES.get(status, READ_ONLY)


def subscription_state(school, *, now=None) -> dict:
    """ملخص معلن للواجهات — الحالة الفعالة والمدة المتبقية بلا أسرار تجارية."""
    subscription = live_subscription(school)
    status = effective_status(subscription, now=now)
    now = now or dj_timezone.now()
    if subscription is None:
        return {
            "has_subscription": False,
            "status": None,
            "access_mode": NO_SUBSCRIPTION_MODE,
            "plan": None,
            "starts_at": None,
            "ends_at": None,
            "days_remaining": None,
            "grace_ends_at": None,
            "trial_ends_at": None,
        }
    reference_end = (
        subscription.trial_ends_at
        if status == SubscriptionStatus.TRIAL and subscription.trial_ends_at
        else subscription.ends_at
    )
    remaining = (reference_end - now).days if reference_end > now else 0
    return {
        "has_subscription": True,
        "status": status,
        "status_label": SubscriptionStatus(status).label,
        "access_mode": ACCESS_MODES.get(status, READ_ONLY),
        "plan": {
            "code": subscription.plan.code,
            "name": subscription.plan.name_ar,
            "billing_period": subscription.plan.billing_period,
        },
        "starts_at": subscription.starts_at.isoformat(),
        "ends_at": subscription.ends_at.isoformat(),
        "days_remaining": remaining,
        "grace_ends_at": (
            subscription.grace_ends_at.isoformat() if subscription.grace_ends_at else None
        ),
        "trial_ends_at": (
            subscription.trial_ends_at.isoformat() if subscription.trial_ends_at else None
        ),
    }
