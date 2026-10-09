"""Queue committed lifecycle events and deduplicate manager reminders."""

import hashlib
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.crypto import salted_hmac

from accounts.contact_email import normalize_contact_email
from common.errors import ApiError
from memberships.models import MembershipStatus, SchoolMembership, SchoolRole
from subscriptions.access import effective_status, live_subscription
from subscriptions.models import SubscriptionEmailDelivery, SubscriptionStatus

DETAIL_EVENTS = {"TRIAL_STARTED", "TRIAL_EXTENDED", "ACTIVATED", "PLAN_CHANGED", "EXTENDED",
                 "REACTIVATED"}


def contact_hash(email):
    return salted_hmac("subscription-contact-email-v1", email, algorithm="sha256").hexdigest()


def verified_manager_address(user):
    from common.tenant_rls import tenant_context
    from parents.email_recovery_models import AccountRecoveryEmail
    from parents.security import decrypt_value

    with tenant_context(user_id=user.pk):
        item = AccountRecoveryEmail.objects.filter(user=user, verified_at__isnull=False).first()
        if item is None:
            return ""
        return normalize_contact_email(decrypt_value(item.current_email_encrypted))


def snapshot_for(subscription):
    def date(value):
        return timezone.localtime(value).strftime("%Y-%m-%d %H:%M") if value else ""

    return {
        "school_name": subscription.school.name, "plan_name": subscription.plan.name_ar,
        "status": subscription.status, "status_label": subscription.get_status_display(),
        "starts_at": date(subscription.starts_at), "ends_at": date(subscription.ends_at),
        "grace_ends_at": date(subscription.grace_ends_at),
        "duration": f"{subscription.duration_value} {subscription.get_duration_unit_display()}",
        "price": f"{subscription.plan.price_amount} {subscription.plan.currency}",
        "contract_version": f"{subscription.plan_id}:{subscription.status}:"
                            f"{subscription.ends_at.isoformat()}:"
                            f"{subscription.grace_ends_at}",
    }


def queue_message(subscription, *, kind, key):
    managers = SchoolMembership.objects.filter(
        school_id=subscription.school_id, status=MembershipStatus.ACTIVE,
        roles__role=SchoolRole.SCHOOL_MANAGER, user__is_active=True,
    ).select_related("user").distinct()
    rows = []
    for membership in managers:
        try:
            address = verified_manager_address(membership.user)
        except ApiError:
            continue
        if not address:
            continue
        row, _ = SubscriptionEmailDelivery.objects.get_or_create(
            deduplication_key=hashlib.sha256(f"{key}:{membership.user_id}".encode()).hexdigest(),
            defaults={"school_id": subscription.school_id, "subscription": subscription,
                      "recipient": membership.user, "recipient_hash": contact_hash(address),
                      "kind": kind, "snapshot": snapshot_for(subscription)},
        )
        rows.append(row)
    return rows


def queue_event(event):
    kind = "DETAILS" if event.event_type in DETAIL_EVENTS else event.event_type
    if kind not in {"DETAILS", "GRACE_STARTED", "EXPIRED", "SUSPENDED", "CANCELLED"}:
        return []
    return queue_message(event.subscription, kind=kind, key=f"event:{event.pk}")


def queue_reminders(*, now=None):
    from subscriptions.models import SchoolSubscription

    now = now or timezone.now()
    count = 0
    for subscription in SchoolSubscription.objects.filter(
        status__in=[SubscriptionStatus.TRIAL, SubscriptionStatus.ACTIVE],
        ends_at__gt=now, ends_at__lte=now + timedelta(days=7),
    ).select_related("school", "plan").iterator():
        if live_subscription(subscription.school).pk != subscription.pk:
            continue
        remaining = subscription.ends_at - now
        kind = "REMINDER_1" if remaining <= timedelta(days=1) else "REMINDER_7"
        count += len(queue_message(subscription, kind=kind,
                                  key=f"reminder:{subscription.pk}:{subscription.ends_at}:{kind}"))
    return count


def queue_initial_manager_details(user):
    # Caller is in the authenticated user's context. Each outbox write is scoped
    # to that user's actual manager school, never a school supplied by the client.
    from common.tenant_rls import tenant_context

    school_ids = list(SchoolMembership.objects.filter(
        user=user, status=MembershipStatus.ACTIVE, roles__role=SchoolRole.SCHOOL_MANAGER,
    ).values_list("school_id", flat=True))
    for school_id in school_ids:
        with tenant_context(school_id=school_id, user_id=user.pk):
            from schools.models import School

            subscription = live_subscription(School.objects.get(pk=school_id))
            if subscription:
                address = verified_manager_address(user)
                if not address:
                    continue
                queue_message(subscription, kind="DETAILS",
                              key=f"initial-contact:{subscription.pk}:"
                                  f"{snapshot_for(subscription)['contract_version']}:"
                                  f"{contact_hash(address)}")


def send_delivery(delivery_id):
    from subscriptions.email_provider import send_subscription_email

    if not settings.SUBSCRIPTION_EMAIL_ENABLED:
        return "disabled"
    with transaction.atomic():
        row = SubscriptionEmailDelivery.objects.select_for_update().filter(pk=delivery_id).first()
        if row is None or row.status != "PENDING":
            return "ignored"
        membership = SchoolMembership.objects.filter(
            school_id=row.school_id, user_id=row.recipient_id,
            status=MembershipStatus.ACTIVE, roles__role=SchoolRole.SCHOOL_MANAGER,
            user__is_active=True,
        ).select_related("user").first()
        subscription = row.subscription
        current = live_subscription(subscription.school)
        valid = membership is not None and current is not None and current.pk == subscription.pk
        try:
            address = verified_manager_address(membership.user) if membership else ""
        except ApiError:
            valid = False
            address = ""
        valid = (valid and bool(address) and contact_hash(address) == row.recipient_hash
                 and snapshot_for(subscription)["contract_version"]
                 == row.snapshot["contract_version"])
        if row.kind.startswith("REMINDER_"):
            remaining = subscription.ends_at - timezone.now()
            valid = valid and effective_status(subscription) in {"TRIAL", "ACTIVE"}
            valid = valid and timedelta(0) < remaining <= timedelta(days=7)
            if row.kind == "REMINDER_7":
                valid = valid and remaining > timedelta(days=1)
            else:
                valid = valid and remaining <= timedelta(days=1)
        row.status = "SENDING" if valid else "CANCELLED"
        row.save(update_fields=["status", "updated_at"])
        if not valid:
            return "cancelled"
        kind, snapshot = row.kind, row.snapshot
    # Never hold a database transaction open over provider I/O.
    result = send_subscription_email(delivery_id=row.pk, recipient=address,
                                     kind=kind, snapshot=snapshot)
    SubscriptionEmailDelivery.objects.filter(pk=row.pk, status="SENDING").update(
        status=result.status, provider_reference=result.provider_reference,
        error_code=result.error_code, updated_at=timezone.now(),
    )
    return result.status
