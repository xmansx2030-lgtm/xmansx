"""UUID-only Celery delivery with a fresh locked security check before transport."""

from celery import shared_task

from parents.email_recovery_provider import EmailDeliveryResult, send_recovery_email


@shared_task(name="parents.send_recovery_email", ignore_result=True, max_retries=0)
def send_parent_recovery_email(delivery_id: str) -> str:
    from parents.email_recovery_services import (
        email_delivery_send_scope,
        finalize_email_delivery,
        prepare_email_delivery,
    )

    prepared = prepare_email_delivery(delivery_id)
    if prepared is None:
        return "skipped"
    with email_delivery_send_scope(delivery_id) as permitted:
        if not permitted:
            return "skipped"
        try:
            result = send_recovery_email(
                delivery_id=prepared["delivery_id"], recipient=prepared["recipient"],
                purpose=prepared["purpose"], token=prepared["token"],
                expires_at=prepared["expires_at"],
            )
        except Exception:
            # Never allow Celery to record a provider exception carrying secrets.
            result = EmailDeliveryResult("UNKNOWN", error_code="DELIVERY_STATE_UNKNOWN")
        finalize_email_delivery(
            delivery_id, status=result.status, provider_reference=result.provider_reference,
            error_code=result.error_code,
        )
    return result.status.lower()
