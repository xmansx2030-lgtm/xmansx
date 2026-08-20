"""إدارة الباقات — التعطيل بدل الحذف حين تكون الباقة مستخدمة تاريخيًا (بند 103)."""

from django.db import transaction

from audit.models import AuditAction
from audit.services import record_event
from common.errors import ApiError
from subscriptions.models import (
    NUMERIC_ENTITLEMENTS,
    EntitlementKey,
    PlanEntitlement,
    SaaSPlan,
)


def _validate_entitlements(entitlements: dict) -> dict:
    clean: dict = {}
    for key, value in (entitlements or {}).items():
        if key not in EntitlementKey.values:
            raise ApiError("VALIDATION_ERROR", f"مفتاح استحقاق غير معروف: {key}")
        if key in NUMERIC_ENTITLEMENTS:
            if value is not None and (not isinstance(value, int) or value < 0):
                raise ApiError("VALIDATION_ERROR", f"قيمة {key} يجب أن تكون عددًا غير سالب.")
            clean[key] = {"numeric_value": value, "is_enabled": True}
        else:
            clean[key] = {"numeric_value": None, "is_enabled": bool(value)}
    return clean


def _apply_entitlements(plan: SaaSPlan, entitlements: dict) -> None:
    for key, values in _validate_entitlements(entitlements).items():
        PlanEntitlement.objects.update_or_create(plan=plan, key=key, defaults=values)


@transaction.atomic
def create_plan(*, actor, code: str, name_ar: str, entitlements=None, request=None, **fields):
    if SaaSPlan.objects.filter(code=code).exists():
        raise ApiError("VALIDATION_ERROR", "رمز الباقة مستخدم مسبقاً.", status_code=409)
    plan = SaaSPlan.objects.create(code=code, name_ar=name_ar, **fields)
    _apply_entitlements(plan, entitlements or {})
    record_event(
        AuditAction.PLAN_CREATED,
        request=request, actor=actor, school=None,
        target_type="SaaSPlan", target_id=plan.id, metadata={"code": plan.code},
    )
    return plan


@transaction.atomic
def update_plan(*, plan: SaaSPlan, actor, entitlements=None, request=None, **fields):
    """تعديل الباقة لا يمس عقود المدارس القائمة — لقطاتها محفوظة (بند 106)."""
    changed = {}
    for field, value in fields.items():
        if value is not None and getattr(plan, field) != value:
            changed[field] = value
            setattr(plan, field, value)
    if changed:
        plan.save(update_fields=[*changed.keys(), "updated_at"])
    if entitlements:
        _apply_entitlements(plan, entitlements)
    record_event(
        AuditAction.PLAN_UPDATED,
        request=request, actor=actor, school=None,
        target_type="SaaSPlan", target_id=plan.id,
        metadata={"changed": sorted(changed.keys()), "entitlements": bool(entitlements)},
    )
    return plan


@transaction.atomic
def disable_plan(*, plan: SaaSPlan, actor, request=None):
    plan.is_active = False
    plan.is_public = False
    plan.save(update_fields=["is_active", "is_public", "updated_at"])
    record_event(
        AuditAction.PLAN_DISABLED,
        request=request, actor=actor, school=None,
        target_type="SaaSPlan", target_id=plan.id, metadata={"code": plan.code},
    )
    return plan


def plan_entitlements(plan: SaaSPlan) -> dict:
    return {
        row.key: (row.numeric_value if row.key in NUMERIC_ENTITLEMENTS else row.is_enabled)
        for row in PlanEntitlement.objects.filter(plan=plan)
    }
