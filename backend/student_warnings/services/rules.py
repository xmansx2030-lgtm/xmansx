"""قواعد الإنذارات: الافتراضات، التحقق التصاعدي، والتحديث الذري (م11).

- التحديث الذري إلزامي: لا تحفظ عتبة المستوى الأول ثم تفشل الثانية فتترك قواعد
  متناقضة (البند 71) — كل النوع يحدث داخل transaction واحدة بعد التحقق الكامل.
- تغيير القواعد لا يمس أي إنذار صادر (Snapshot في StudentWarning).
"""

from django.db import transaction

from audit.models import AuditAction
from audit.services import record_event
from common.errors import ApiError
from student_warnings.models import (
    DEFAULT_THRESHOLDS,
    LEVEL_ORDER,
    MAX_THRESHOLD,
    WarningRule,
    WarningRuleType,
)


def ensure_default_rules(*, school) -> list[WarningRule]:
    """ينشئ القواعد الافتراضية (3/5/10) لأي نوع/مستوى غير معرف — idempotent."""
    existing = {
        (rule.rule_type, rule.level): rule
        for rule in WarningRule.objects.filter(school=school)
    }
    missing = [
        WarningRule(
            school=school,
            rule_type=rule_type,
            level=level,
            threshold=DEFAULT_THRESHOLDS[rule_type][level],
        )
        for rule_type in WarningRuleType.values
        for level in LEVEL_ORDER
        if (rule_type, level) not in existing
    ]
    if missing:
        WarningRule.objects.bulk_create(missing, ignore_conflicts=True)
    return list(WarningRule.objects.filter(school=school).order_by("rule_type", "level"))


def get_rules_map(*, school) -> dict:
    """{rule_type: {"is_enabled": bool, "levels": {level: threshold}}} — استعلام واحد."""
    rules = ensure_default_rules(school=school)
    result: dict[str, dict] = {}
    for rule in rules:
        bucket = result.setdefault(
            rule.rule_type, {"is_enabled": True, "levels": {}}
        )
        bucket["levels"][rule.level] = rule.threshold
        # النوع مفعل فقط إذا كانت كل مستوياته مفعلة (الإيقاف يتم على مستوى النوع)
        bucket["is_enabled"] = bucket["is_enabled"] and rule.is_enabled
    return result


def _validate_thresholds(rule_type: str, levels: dict) -> None:
    values = []
    for level in LEVEL_ORDER:
        value = levels.get(level)
        if value is None:
            raise ApiError(
                "INVALID_WARNING_THRESHOLD",
                "يجب تحديد حدود المستويات الثلاثة لكل نوع إنذار.",
            )
        if not isinstance(value, int) or value < 1 or value > MAX_THRESHOLD:
            raise ApiError(
                "INVALID_WARNING_THRESHOLD",
                f"حد الإنذار يجب أن يكون رقمًا بين 1 و{MAX_THRESHOLD}.",
            )
        values.append(value)
    if not (values[0] < values[1] < values[2]):
        raise ApiError(
            "INVALID_WARNING_THRESHOLD_ORDER",
            "يجب أن تكون حدود الإنذارات مرتبة تصاعدياً (الأول < الثاني < الثالث).",
            details={"rule_type": rule_type},
        )


@transaction.atomic
def update_rules(*, school, actor, payload: dict, request=None) -> dict:
    """تحديث ذري لأنواع القواعد — يتحقق من كل الأنواع قبل حفظ أي شيء."""
    ensure_default_rules(school=school)
    changes: dict[str, dict] = {}
    updates: list[WarningRule] = []

    for rule_type, config in payload.items():
        if rule_type not in WarningRuleType.values:
            raise ApiError("WARNING_RULE_NOT_FOUND", "نوع الإنذار غير معروف.", status_code=404)
        levels = config.get("levels") or {}
        _validate_thresholds(rule_type, levels)
        is_enabled = config.get("is_enabled")

        rules = {
            rule.level: rule
            for rule in WarningRule.objects.select_for_update().filter(
                school=school, rule_type=rule_type
            )
        }
        type_changes: dict[str, dict] = {}
        for level in LEVEL_ORDER:
            rule = rules[level]
            new_threshold = levels[level]
            new_enabled = rule.is_enabled if is_enabled is None else bool(is_enabled)
            if rule.threshold != new_threshold or rule.is_enabled != new_enabled:
                type_changes[level] = {
                    "from": {"threshold": rule.threshold, "is_enabled": rule.is_enabled},
                    "to": {"threshold": new_threshold, "is_enabled": new_enabled},
                }
                rule.threshold = new_threshold
                rule.is_enabled = new_enabled
                updates.append(rule)
        if type_changes:
            changes[rule_type] = type_changes

    if updates:
        WarningRule.objects.bulk_update(updates, ["threshold", "is_enabled", "updated_at"])
        record_event(
            AuditAction.WARNING_RULES_UPDATED,
            request=request,
            actor=actor,
            school=school,
            metadata={"changed": changes},  # عتبات فقط — لا بيانات طلاب
        )
    return get_rules_map(school=school)
