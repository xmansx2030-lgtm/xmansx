"""A security migration cannot reverse its guard over retained credential data."""

import pytest
from django.db import DatabaseError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.recorder import MigrationRecorder
from django.utils import timezone

from accounts.models import User
from parents.email_recovery_models import AccountRecoveryEmail
from parents.email_recovery_services import recovery_email_hash
from parents.security import encrypt_value

pytestmark = pytest.mark.django_db(transaction=True)
GUARD_MIGRATION = "0008_retained_recovery_credential_mobile_guard"


@pytest.mark.parametrize("verified", [False, True])
def test_mobile_guard_rollback_refuses_existing_recovery_data_and_preserves_protection(verified):
    executor = MigrationExecutor(connection)
    full_targets = executor.loader.graph.leaf_nodes()
    owner = User.objects.create_user(mobile="0551800601", password="Retained-Owner-2026!")
    address = "migration-owner@example.invalid"
    item = AccountRecoveryEmail.objects.create(
        user=owner,
        current_email_encrypted=encrypt_value(address) if verified else "",
        current_email_hash=recovery_email_hash(address) if verified else None,
        verified_at=timezone.now() if verified else None,
        pending_email_encrypted=encrypt_value(address) if not verified else "",
        pending_email_hash=recovery_email_hash(address) if not verified else "",
    )
    snapshot = AccountRecoveryEmail.objects.values().get(pk=item.pk)
    try:
        with pytest.raises(DatabaseError, match="unsafe guard rollback blocked"):
            executor.migrate(
                [("parents", "0007_guardianregistrationrequest_email_encrypted_and_more")]
            )
        assert MigrationRecorder.Migration.objects.filter(
            app="parents", name=GUARD_MIGRATION
        ).exists()
        assert AccountRecoveryEmail.objects.values().get(pk=item.pk) == snapshot
        with pytest.raises(DatabaseError, match="independent verification"), transaction.atomic():
            User.objects.filter(pk=owner.pk).update(mobile="+966551800609")
        owner.refresh_from_db()
        assert owner.mobile == "+966551800601"
    finally:
        MigrationExecutor(connection).migrate(full_targets)
