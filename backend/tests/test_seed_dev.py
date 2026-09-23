import pytest
from django.core.management import call_command
from django.test import override_settings

from accounts.models import User
from memberships.models import (
    MembershipStatus,
    SchoolCapability,
    SchoolMembership,
    SchoolMembershipCapability,
    SchoolMembershipRole,
    SchoolRole,
)


@override_settings(DEBUG=True)
@pytest.mark.django_db
def test_seed_dev_restores_canonical_teacher_credentials_roles_and_capabilities():
    original_password = "Seed-Original-2026!"
    restored_password = "Seed-Restored-2026!"
    call_command("seed_dev", password=original_password)

    user = User.objects.get(mobile="+966550000001")
    membership = SchoolMembership.objects.get(user=user, school__slug="school-a")
    SchoolMembershipRole.objects.create(
        membership=membership,
        role=SchoolRole.VICE_PRINCIPAL,
    )
    SchoolMembershipCapability.objects.create(
        membership=membership,
        capability=SchoolCapability.MORNING_ATTENDANCE,
        granted_by=user,
    )
    membership.status = MembershipStatus.SUSPENDED
    membership.save(update_fields=["status", "updated_at"])
    user.set_password("Changed-By-Test-2026!")
    user.save(update_fields=["password", "updated_at"])

    call_command("seed_dev", password=restored_password)

    user.refresh_from_db()
    membership.refresh_from_db()
    assert user.check_password(restored_password)
    assert membership.status == MembershipStatus.ACTIVE
    assert set(membership.role_codes()) == {SchoolRole.TEACHER}
    assert membership.capability_codes() == []
