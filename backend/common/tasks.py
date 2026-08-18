"""Foundation health/test task فقط — ليست Feature.

الغرض الوحيد: التحقق أن Celery worker يعمل ويستقبل المهام.
"""

from celery import shared_task


@shared_task(name="common.foundation_ping")
def foundation_ping() -> str:
    return "pong"
