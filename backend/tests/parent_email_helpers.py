"""Owner-provisioned verified credentials for legacy family regression fixtures.

This is test setup, never a production backfill or an application verification
path. New enrollment/recovery tests exercise the actual token flow separately.
"""

from django.utils import timezone


def provision_verified_recovery_email(user, email=None):
    from parents.email_recovery_models import AccountRecoveryEmail
    from parents.email_recovery_services import normalize_email, recovery_email_hash
    from parents.security import encrypt_value

    normalized = normalize_email(email or f"legacy-fixture-{user.pk}@parent.invalid")
    return AccountRecoveryEmail.objects.update_or_create(
        user=user,
        defaults={
            "current_email_encrypted": encrypt_value(normalized),
            "current_email_hash": recovery_email_hash(normalized),
            "verified_at": timezone.now(),
            "pending_email_encrypted": "",
            "pending_email_hash": "",
        },
    )[0]
