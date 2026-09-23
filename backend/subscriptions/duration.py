"""حساب مدة الباقة بوحدات مفهومة للمستخدم مع احترام حدود الأشهر والسنوات."""

from calendar import monthrange
from datetime import datetime, timedelta

from common.errors import ApiError
from subscriptions.models import PlanDurationUnit


def add_duration(start: datetime, value: int, unit: str) -> datetime:
    if value <= 0:
        raise ApiError("INVALID_SUBSCRIPTION_DATE_RANGE", "مدة الباقة يجب أن تكون أكبر من صفر.")
    if unit == PlanDurationUnit.DAYS:
        return start + timedelta(days=value)
    if unit not in (PlanDurationUnit.MONTHS, PlanDurationUnit.YEARS):
        raise ApiError("VALIDATION_ERROR", "وحدة مدة الباقة غير صحيحة.")

    months = value if unit == PlanDurationUnit.MONTHS else value * 12
    month_index = start.year * 12 + start.month - 1 + months
    year, zero_based_month = divmod(month_index, 12)
    month = zero_based_month + 1
    day = min(start.day, monthrange(year, month)[1])
    return start.replace(year=year, month=month, day=day)
