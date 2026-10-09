"""Subscription mail is opt-in at runtime, isolated from parent recovery and SMS."""

from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from common.tenant_rls import tenant_context


@shared_task(name="subscriptions.send_manager_email", ignore_result=True)
def send_manager_email(delivery_id):
    from subscriptions.email_services import send_delivery

    with tenant_context(bypass=True):
        return send_delivery(delivery_id)


@shared_task(name="subscriptions.process_manager_emails", ignore_result=True)
def process_manager_emails():
    if not settings.SUBSCRIPTION_EMAIL_ENABLED:
        return "disabled"
    from subscriptions.email_services import queue_reminders
    from subscriptions.models import SubscriptionEmailDelivery
    from subscriptions.services.subscriptions import sync_expirations

    with tenant_context(bypass=True):
        sync_expirations()
        queue_reminders()
        SubscriptionEmailDelivery.objects.filter(
            status="SENDING", updated_at__lt=timezone.now() - timedelta(minutes=10),
        ).update(status="UNKNOWN", error_code="STALE_SENDING", updated_at=timezone.now())
        ids = list(SubscriptionEmailDelivery.objects.filter(status="PENDING")
                   .order_by("created_at").values_list("pk", flat=True)[:100])
    for delivery_id in ids:
        send_manager_email.delay(str(delivery_id))
    return len(ids)
