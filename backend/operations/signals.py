import logging

from celery.signals import task_failure, task_retry

logger = logging.getLogger("xmansx.jobs")


@task_failure.connect
def log_task_failure(sender=None, task_id=None, exception=None, **kwargs) -> None:
    logger.error(
        "celery_task_failed",
        extra={
            "task_name": getattr(sender, "name", "unknown")[:160],
            "task_id": str(task_id or "")[:64],
            "error_type": type(exception).__name__ if exception else "unknown",
        },
    )


@task_retry.connect
def log_task_retry(sender=None, request=None, reason=None, **kwargs) -> None:
    logger.warning(
        "celery_task_retrying",
        extra={
            "task_name": getattr(sender, "name", "unknown")[:160],
            "task_id": str(getattr(request, "id", ""))[:64],
            "error_type": type(reason).__name__ if reason else "unknown",
        },
    )
