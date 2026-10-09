"""Refresh only an empty synthetic recovery foundation during local QA.

Not a production rollback mechanism. Refuses any existing recovery/evidence/
review row, unrelated database, or dependent migration rollback.
"""

import os
import sys
from pathlib import Path

import django
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


def main():
    expected = {
        "PARENT_STAGING_LOCAL_ONLY": "1",
        "PARENT_VERIFICATION_LOCAL_ONLY": "1",
        "POSTGRES_DB": "parent_verification",
        "POSTGRES_USER": "parent_verify_owner",
        "POSTGRES_HOST": "postgres",
        "DJANGO_SETTINGS_MODULE": "config.settings.local",
    }
    if any(os.environ.get(key) != value for key, value in expected.items()):
        raise RuntimeError(
            "Empty-schema refresh requires the exact isolated synthetic owner"
        )
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
    django.setup()
    from parents.recovery_models import (
        GlobalAccountRecoveryCase,
        RecoveryEvidenceReference,
        RecoveryReviewAuthorization,
        RecoveryReviewDecision,
    )

    models = (
        GlobalAccountRecoveryCase,
        RecoveryEvidenceReference,
        RecoveryReviewAuthorization,
        RecoveryReviewDecision,
    )
    if any(model.objects.count() for model in models):
        raise RuntimeError(
            "Refusing recovery schema refresh with any existing review or evidence row"
        )
    executor = MigrationExecutor(connection)
    plan = executor.migration_plan([("parents", "0005_immutable_relation_identity")])
    if [
        (migration.app_label, migration.name, backwards)
        for migration, backwards in plan
    ] != [("parents", "0006_review_only_account_recovery", True)]:
        raise RuntimeError(
            "Refusing anything except the single empty recovery migration"
        )
    print("All four recovery tables are empty; reverse plan contains only parents0006")
    call_command(
        "migrate", "parents", "0005_immutable_relation_identity", interactive=False
    )
    call_command("migrate", interactive=False)
    print(
        "Synthetic empty-schema refresh complete; no account/relationship data removed"
    )


if __name__ == "__main__":
    main()
