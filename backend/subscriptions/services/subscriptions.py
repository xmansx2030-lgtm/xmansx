"""دورة حياة الاشتراك — كل انتقال صريح ومسجَّل (بنود 26-39، 48-51، 113-115).

قواعد صلبة:
- لا حذف بيانات في أي انتقال: انتهاء/إيقاف/تخفيض/إلغاء = تغيير وصول فقط (بند 148).
- التجديد لا يعدّل العقد القديم — عقد جديد يحفظ التاريخ (بند 114).
- القيد الفريد في قاعدة البيانات هو الحكم ضد عقدين حيّين (لا فحص تطبيقي وحده).
"""

from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone as dj_timezone

from audit.models import AuditAction
from audit.services import record_event
from common.errors import ApiError
from subscriptions.access import effective_status, live_subscription
from subscriptions.entitlements import invalidate_school_entitlements
from subscriptions.models import (
    LIVE_SUBSCRIPTION_STATUSES,
    PlanEntitlement,
    SaaSPlan,
    SchoolSubscription,
    SubscriptionEntitlement,
    SubscriptionEvent,
    SubscriptionEventType,
    SubscriptionStatus,
)

DEFAULT_GRACE_DAYS = 7


def _lock_school(school) -> None:
    """يقفل المستأجر نفسه حتى عندما لا يوجد عقد بعد؛ يمنع سباق أول تفعيل."""
    from schools.models import School

    School.objects.select_for_update().only("id").get(id=school.id)


def log_event(*, subscription, event_type, actor=None, reason="", metadata=None):
    return SubscriptionEvent.objects.create(
        school=subscription.school,
        subscription=subscription,
        event_type=event_type,
        actor=actor,
        reason=reason[:300],
        metadata=metadata or {},
    )


def _copy_entitlements(subscription: SchoolSubscription) -> None:
    """لقطة الحدود وقت التفعيل — تعديل الباقة لاحقًا لا يمس هذا العقد (بند 105)."""
    SubscriptionEntitlement.objects.filter(
        subscription=subscription, is_override=False
    ).delete()
    rows = PlanEntitlement.objects.filter(plan=subscription.plan)
    SubscriptionEntitlement.objects.bulk_create(
        [
            SubscriptionEntitlement(
                subscription=subscription,
                key=row.key,
                numeric_value=row.numeric_value,
                is_enabled=row.is_enabled,
            )
            for row in rows
            # التجاوز الإداري لا يُدهس عند إعادة النسخ
            if not SubscriptionEntitlement.objects.filter(
                subscription=subscription, key=row.key, is_override=True
            ).exists()
        ]
    )


def _require_no_live_subscription(school) -> None:
    existing = (
        SchoolSubscription.objects.filter(school=school)
        .order_by("-starts_at", "-id")
        .first()
    )
    if existing is not None:
        current_effective = effective_status(existing)
        if current_effective not in LIVE_SUBSCRIPTION_STATUSES:
            if existing.status in LIVE_SUBSCRIPTION_STATUSES:
                existing.status = SubscriptionStatus.EXPIRED
                existing.save(update_fields=["status", "updated_at"])
                log_event(
                    subscription=existing,
                    event_type=SubscriptionEventType.EXPIRED,
                    metadata={"effective_status": current_effective},
                )
            return
        raise ApiError(
            "SUBSCRIPTION_ALREADY_ACTIVE",
            "للمدرسة اشتراك فعّال بالفعل.",
            status_code=409,
            details={"subscription_id": existing.id},
        )


def _resolve_plan(plan_id: int) -> SaaSPlan:
    plan = SaaSPlan.objects.filter(id=plan_id).first()
    if plan is None:
        raise ApiError("PLAN_NOT_FOUND", "الباقة غير موجودة.", status_code=404)
    if not plan.is_active:
        raise ApiError("PLAN_INACTIVE", "الباقة غير متاحة للاشتراك.", status_code=409)
    return plan


@transaction.atomic
def start_trial(*, school, plan_id: int, actor, trial_days: int | None = None, request=None):
    """يبدأ فترة تجريبية — مدة الباقة الافتراضية ما لم تُحدد صراحة."""
    plan = _resolve_plan(plan_id)
    _lock_school(school)
    _require_no_live_subscription(school)
    days = trial_days if trial_days is not None else plan.trial_days_default
    if days <= 0:
        raise ApiError("VALIDATION_ERROR", "مدة التجربة يجب أن تكون أكبر من صفر.")

    now = dj_timezone.now()
    ends = now + timedelta(days=days)
    try:
        subscription = SchoolSubscription.objects.create(
            school=school,
            plan=plan,
            status=SubscriptionStatus.TRIAL,
            starts_at=now,
            ends_at=ends,
            trial_started_at=now,
            trial_ends_at=ends,
            created_by=actor,
            updated_by=actor,
        )
    except IntegrityError as exc:  # سباق: القيد الفريد هو الحكم
        raise ApiError(
            "SUBSCRIPTION_CONFLICT", "تعذر إنشاء الاشتراك — حاول مجددًا.", status_code=409
        ) from exc

    _copy_entitlements(subscription)
    log_event(
        subscription=subscription,
        event_type=SubscriptionEventType.CREATED,
        actor=actor,
        metadata={"plan_code": plan.code, "mode": SubscriptionStatus.TRIAL},
    )
    log_event(
        subscription=subscription,
        event_type=SubscriptionEventType.TRIAL_STARTED,
        actor=actor,
        metadata={"days": days, "plan_code": plan.code},
    )
    record_event(
        AuditAction.TRIAL_STARTED,
        request=request, actor=actor, school=school,
        target_type="SchoolSubscription", target_id=subscription.id,
        metadata={"plan_code": plan.code, "days": days},
    )
    invalidate_school_entitlements(school)
    return subscription


@transaction.atomic
def extend_trial(*, school, extra_days: int, actor, reason: str = "", request=None):
    """تمديد التجربة — كل تمديد يسجل القديم والجديد والفاعل والسبب (بند 38)."""
    subscription = _locked_live(school)
    if subscription.status != SubscriptionStatus.TRIAL:
        raise ApiError("TRIAL_EXPIRED", "لا توجد فترة تجريبية جارية للتمديد.", status_code=409)
    if extra_days <= 0:
        raise ApiError("VALIDATION_ERROR", "مدة التمديد يجب أن تكون أكبر من صفر.")

    old_end = subscription.trial_ends_at or subscription.ends_at
    new_end = old_end + timedelta(days=extra_days)
    subscription.trial_ends_at = new_end
    subscription.ends_at = new_end
    subscription.updated_by = actor
    subscription.save(update_fields=["trial_ends_at", "ends_at", "updated_by", "updated_at"])

    log_event(
        subscription=subscription,
        event_type=SubscriptionEventType.TRIAL_EXTENDED,
        actor=actor,
        reason=reason,
        metadata={
            "old_end": old_end.isoformat(),
            "new_end": new_end.isoformat(),
            "days": extra_days,
        },
    )
    record_event(
        AuditAction.TRIAL_EXTENDED,
        request=request, actor=actor, school=school,
        target_type="SchoolSubscription", target_id=subscription.id,
        metadata={"days": extra_days},
    )
    invalidate_school_entitlements(school)
    return subscription


def _locked_live(school) -> SchoolSubscription:
    """أحدث عقد للمدرسة مقفولًا — يمنع تنفيذ إجرائين متزامنين عليه."""
    subscription = (
        SchoolSubscription.objects.select_for_update()
        .filter(school=school)
        .order_by("-starts_at", "-id")
        .first()
    )
    if subscription is None:
        raise ApiError("SUBSCRIPTION_NOT_FOUND", "لا يوجد اشتراك لهذه المدرسة.", status_code=404)
    return subscription


@transaction.atomic
def activate(*, school, plan_id: int, months: int = 12, actor, request=None):
    """تفعيل اشتراك مدفوع — يحل محل التجربة أو يجدد بعد الانتهاء."""
    plan = _resolve_plan(plan_id)
    _lock_school(school)
    now = dj_timezone.now()
    current = (
        SchoolSubscription.objects.select_for_update()
        .filter(school=school)
        .order_by("-starts_at", "-id")
        .first()
    )
    if months <= 0:
        raise ApiError("INVALID_SUBSCRIPTION_DATE_RANGE", "المدة يجب أن تكون أكبر من صفر.")

    if current is not None and current.status in LIVE_SUBSCRIPTION_STATUSES:
        current_effective = effective_status(current, now=now)
        if current_effective == SubscriptionStatus.ACTIVE:
            raise ApiError(
                "SUBSCRIPTION_ALREADY_ACTIVE", "الاشتراك مفعّل بالفعل.", status_code=409
            )
        # التجربة/المهلة تُغلق كعقد تاريخي ثم يبدأ عقد مدفوع جديد (بند 30)
        current.status = SubscriptionStatus.EXPIRED
        current.save(update_fields=["status", "updated_at"])
        log_event(
            subscription=current,
            event_type=SubscriptionEventType.EXPIRED,
            actor=actor,
            metadata={
                "replaced_by_activation": True,
                "effective_status": current_effective,
            },
        )

    subscription = SchoolSubscription.objects.create(
        school=school,
        plan=plan,
        status=SubscriptionStatus.ACTIVE,
        starts_at=now,
        ends_at=now + timedelta(days=30 * months),
        created_by=actor,
        updated_by=actor,
    )
    _copy_entitlements(subscription)
    log_event(
        subscription=subscription,
        event_type=SubscriptionEventType.CREATED,
        actor=actor,
        metadata={"plan_code": plan.code, "mode": SubscriptionStatus.ACTIVE},
    )
    log_event(
        subscription=subscription,
        event_type=SubscriptionEventType.ACTIVATED,
        actor=actor,
        metadata={"plan_code": plan.code, "months": months},
    )
    record_event(
        AuditAction.SUBSCRIPTION_ACTIVATED,
        request=request, actor=actor, school=school,
        target_type="SchoolSubscription", target_id=subscription.id,
        metadata={"plan_code": plan.code, "months": months},
    )
    invalidate_school_entitlements(school)
    return subscription


@transaction.atomic
def change_plan(*, school, plan_id: int, actor, reason: str = "", request=None):
    """ترقية/تخفيض فوري — يحدّث اللقطة ولا يحذف أي بيان تجاوز الحد (بند 80)."""
    plan = _resolve_plan(plan_id)
    subscription = _locked_live(school)
    if subscription.status not in LIVE_SUBSCRIPTION_STATUSES:
        raise ApiError(
            "INVALID_PLAN_CHANGE", "لا يمكن تغيير باقة اشتراك غير فعّال.", status_code=409
        )
    if subscription.plan_id == plan.id:
        raise ApiError("INVALID_PLAN_CHANGE", "الباقة الحالية هي نفسها.", status_code=409)

    old_plan = subscription.plan
    subscription.plan = plan
    subscription.updated_by = actor
    subscription.save(update_fields=["plan", "updated_by", "updated_at"])
    _copy_entitlements(subscription)

    log_event(
        subscription=subscription,
        event_type=SubscriptionEventType.PLAN_CHANGED,
        actor=actor,
        reason=reason,
        metadata={"from": old_plan.code, "to": plan.code},
    )
    record_event(
        AuditAction.SUBSCRIPTION_PLAN_CHANGED,
        request=request, actor=actor, school=school,
        target_type="SchoolSubscription", target_id=subscription.id,
        metadata={"from": old_plan.code, "to": plan.code},
    )
    invalidate_school_entitlements(school)
    return subscription


@transaction.atomic
def extend(*, school, extra_days: int, actor, reason: str = "", request=None):
    subscription = _locked_live(school)
    if subscription.status in (SubscriptionStatus.CANCELLED, SubscriptionStatus.SUSPENDED):
        raise ApiError(
            "INVALID_PLAN_CHANGE", "لا يمكن تمديد اشتراك ملغى أو موقوف.", status_code=409
        )
    if extra_days <= 0:
        raise ApiError("INVALID_SUBSCRIPTION_DATE_RANGE", "مدة التمديد يجب أن تكون موجبة.")

    old_end = subscription.ends_at
    extension_base = max(old_end, dj_timezone.now())
    subscription.ends_at = extension_base + timedelta(days=extra_days)
    # التمديد يعيد الحياة لعقد منتهٍ دون فقد أي بيان
    if subscription.status == SubscriptionStatus.EXPIRED:
        subscription.status = SubscriptionStatus.ACTIVE
    subscription.updated_by = actor
    subscription.save(update_fields=["ends_at", "status", "updated_by", "updated_at"])

    log_event(
        subscription=subscription,
        event_type=SubscriptionEventType.EXTENDED,
        actor=actor,
        reason=reason,
        metadata={"old_end": old_end.isoformat(), "new_end": subscription.ends_at.isoformat()},
    )
    record_event(
        AuditAction.SUBSCRIPTION_EXTENDED,
        request=request, actor=actor, school=school,
        target_type="SchoolSubscription", target_id=subscription.id,
        metadata={"days": extra_days},
    )
    invalidate_school_entitlements(school)
    return subscription


@transaction.atomic
def suspend(*, school, actor, reason: str, request=None):
    """إيقاف إداري — قرار المنصة، مختلف عن الانتهاء، ولا يحذف شيئًا (بنود 48-50)."""
    if not (reason or "").strip():
        raise ApiError("VALIDATION_ERROR", "سبب الإيقاف مطلوب.")
    subscription = _locked_live(school)
    if subscription.status == SubscriptionStatus.SUSPENDED:
        raise ApiError("SUBSCRIPTION_CONFLICT", "الاشتراك موقوف بالفعل.", status_code=409)

    subscription.status = SubscriptionStatus.SUSPENDED
    subscription.suspended_at = dj_timezone.now()
    subscription.suspension_reason = reason.strip()[:300]
    subscription.updated_by = actor
    subscription.save(
        update_fields=[
            "status", "suspended_at", "suspension_reason", "updated_by", "updated_at",
        ]
    )
    log_event(
        subscription=subscription,
        event_type=SubscriptionEventType.SUSPENDED,
        actor=actor,
        reason=reason,
    )
    record_event(
        AuditAction.SUBSCRIPTION_SUSPENDED,
        request=request, actor=actor, school=school,
        target_type="SchoolSubscription", target_id=subscription.id,
        metadata={},
    )
    invalidate_school_entitlements(school)
    return subscription


@transaction.atomic
def reactivate(*, school, actor, reason: str = "", request=None):
    """إعادة تفعيل صريحة — الحالة تعود بحسب التواريخ لا بافتراض «نشط»."""
    subscription = _locked_live(school)
    if subscription.status != SubscriptionStatus.SUSPENDED:
        raise ApiError("SUBSCRIPTION_CONFLICT", "الاشتراك ليس موقوفًا.", status_code=409)

    now = dj_timezone.now()
    subscription.status = (
        SubscriptionStatus.ACTIVE if subscription.ends_at > now else SubscriptionStatus.EXPIRED
    )
    subscription.suspended_at = None
    subscription.suspension_reason = ""
    subscription.updated_by = actor
    subscription.save(
        update_fields=[
            "status", "suspended_at", "suspension_reason", "updated_by", "updated_at",
        ]
    )
    log_event(
        subscription=subscription,
        event_type=SubscriptionEventType.REACTIVATED,
        actor=actor,
        reason=reason,
    )
    record_event(
        AuditAction.SUBSCRIPTION_REACTIVATED,
        request=request, actor=actor, school=school,
        target_type="SchoolSubscription", target_id=subscription.id,
        metadata={"status": subscription.status},
    )
    invalidate_school_entitlements(school)
    return subscription


@transaction.atomic
def cancel(*, school, actor, reason: str, request=None):
    if not (reason or "").strip():
        raise ApiError("VALIDATION_ERROR", "سبب الإلغاء مطلوب.")
    subscription = _locked_live(school)
    if subscription.status == SubscriptionStatus.CANCELLED:
        raise ApiError("SUBSCRIPTION_CANCELLED", "الاشتراك ملغى بالفعل.", status_code=409)

    subscription.status = SubscriptionStatus.CANCELLED
    subscription.cancelled_at = dj_timezone.now()
    subscription.cancel_reason = reason.strip()[:300]
    subscription.updated_by = actor
    subscription.save(
        update_fields=["status", "cancelled_at", "cancel_reason", "updated_by", "updated_at"]
    )
    log_event(
        subscription=subscription,
        event_type=SubscriptionEventType.CANCELLED,
        actor=actor,
        reason=reason,
    )
    record_event(
        AuditAction.SUBSCRIPTION_CANCELLED,
        request=request, actor=actor, school=school,
        target_type="SchoolSubscription", target_id=subscription.id,
        metadata={},
    )
    invalidate_school_entitlements(school)
    return subscription


@transaction.atomic
def set_entitlement_override(*, school, key: str, numeric_value=None, is_enabled=True, actor,
                             request=None):
    """تجاوز إداري لمدرسة بعينها فوق قيمة الباقة (بنود 110-112)."""
    subscription = _locked_live(school)
    row, _ = SubscriptionEntitlement.objects.update_or_create(
        subscription=subscription,
        key=key,
        defaults={
            "numeric_value": numeric_value,
            "is_enabled": is_enabled,
            "is_override": True,
        },
    )
    subscription.save(update_fields=["updated_at"])  # يبطل الـ cache
    log_event(
        subscription=subscription,
        event_type=SubscriptionEventType.ENTITLEMENT_OVERRIDDEN,
        actor=actor,
        metadata={"key": key, "numeric_value": numeric_value, "is_enabled": is_enabled},
    )
    record_event(
        AuditAction.ENTITLEMENT_OVERRIDE_CHANGED,
        request=request, actor=actor, school=school,
        target_type="SubscriptionEntitlement", target_id=row.id,
        metadata={"key": key},
    )
    invalidate_school_entitlements(school)
    return row


def sync_expirations(*, now=None) -> dict:
    """يوائم الحالة المخزنة مع الحالة الفعالة — **Idempotent** (بنود 200-202).

    ليست مصدر الحقيقة: كل طلب يحسب الحالة الفعالة بنفسه، وهذه المهمة للأرشفة
    والتنبيهات فقط، فتأخر Celery لا يفتح مدرسة منتهية.
    """
    now = now or dj_timezone.now()
    counts = {"expired": 0, "grace": 0}
    candidates = SchoolSubscription.objects.filter(
        status__in=LIVE_SUBSCRIPTION_STATUSES
    ).select_related("school")
    for subscription in candidates:
        current = effective_status(subscription, now=now)
        if current == subscription.status:
            continue
        subscription.status = current
        subscription.save(update_fields=["status", "updated_at"])
        if current == SubscriptionStatus.EXPIRED:
            counts["expired"] += 1
            log_event(subscription=subscription, event_type=SubscriptionEventType.EXPIRED)
        elif current == SubscriptionStatus.GRACE_PERIOD:
            counts["grace"] += 1
            log_event(subscription=subscription, event_type=SubscriptionEventType.GRACE_STARTED)
    return counts


def current_subscription(school):
    return live_subscription(school)
