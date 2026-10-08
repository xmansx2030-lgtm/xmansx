"""Minimal global credential ownership checks for administrative write guards."""

from common.tenant_rls import tenant_context


def has_guardian_credentials(user_id):
    """Keep credentials protected after a school removes the last guardian relation.

    Read only the exact account's existence bits, including a pending recovery
    email. No school/platform bypass or decrypted recovery address is involved.
    Credential writers must hold the account's User row lock before this check.
    """
    from parents.email_recovery_models import AccountRecoveryEmail
    from parents.models import GuardianStudentRelation

    with tenant_context(user_id=user_id):
        return (
            GuardianStudentRelation.objects.filter(user_id=user_id).exists()
            or AccountRecoveryEmail.objects.filter(user_id=user_id).exists()
        )
