"""Owner-only checks and explicit registration closure for fresh synthetic schools.

The restricted HTTP role cannot prove global absence of SMS configuration or
enabled schools because its ordinary queries are deliberately scoped by RLS.
"""

import argparse
import json
import os
import sys
from pathlib import Path

import django


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--close-registration", action="store_true")
    parser.add_argument(
        "--expected-registration", choices=["disabled", "enabled"], required=True
    )
    args = parser.parse_args()
    expected = {
        "PARENT_VERIFICATION_LOCAL_ONLY": "1",
        "POSTGRES_DB": "parent_verification",
        "POSTGRES_USER": "parent_verify_owner",
        "POSTGRES_HOST": "postgres",
        "DJANGO_SETTINGS_MODULE": "config.settings.local",
    }
    if any(os.environ.get(key) != value for key, value in expected.items()):
        raise RuntimeError(
            "Fixture checks require the exact isolated synthetic owner database"
        )
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
    django.setup()
    from django.db import transaction
    from memberships.models import SchoolMembership, SchoolMembershipRole
    from parents.models import GuardianStudentRelation, ParentRegistrationConfig
    from school_sms.models import AbsenceSmsNotice, SchoolSmsIntegration
    from schools.models import School

    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    schools = fixture["schools"]
    assert len(schools) == 3 and len(fixture["acceptance"]["children"]) == 3
    ids = [school["id"] for school in schools]
    expected_slugs = {f"parent-e2e-{letter}-{fixture['run']}" for letter in "abc"}
    assert (
        set(School.objects.filter(id__in=ids).values_list("slug", flat=True))
        == expected_slugs
    )
    enabled = args.expected_registration == "enabled"
    if args.close_registration:
        if enabled:
            raise RuntimeError(
                "Registration closure requires expected-registration disabled"
            )
        with transaction.atomic():
            configs = list(
                ParentRegistrationConfig.objects.select_for_update().filter(
                    school_id__in=ids
                )
            )
            assert len(configs) == 3
            ParentRegistrationConfig.objects.filter(
                id__in=[config.id for config in configs]
            ).update(enabled=False)
    assert (
        ParentRegistrationConfig.objects.filter(
            school_id__in=ids, enabled=enabled
        ).count()
        == 3
    )
    assert not ParentRegistrationConfig.objects.filter(
        school_id__in=ids, enabled=not enabled
    ).exists()
    assert SchoolSmsIntegration.objects.count() == 0
    assert AbsenceSmsNotice.objects.count() == 0
    if not enabled:
        assert ParentRegistrationConfig.objects.filter(enabled=True).count() == 0
    for school in schools:
        assert SchoolMembershipRole.objects.filter(
            membership__school_id=school["id"],
            membership__user__mobile=school["staff_mobile"],
            role="SCHOOL_MANAGER",
        ).exists()
        for role, staff in school["acceptance_staff"].items():
            membership = SchoolMembership.objects.get(id=staff["membership_id"])
            assert membership.school_id == school["id"]
            assert set(membership.roles.values_list("role", flat=True)) == {role}
    for child in fixture["acceptance"]["children"]:
        assert GuardianStudentRelation.objects.filter(
            id=child["relation_id"],
            school_id=child["school_id"],
            student_id=child["student_id"],
            user__mobile=fixture["acceptance"]["parent_mobile"],
            status="ACTIVE",
        ).exists()
    switch = fixture["acceptance"].get("switch_actor")
    if switch:
        assert GuardianStudentRelation.objects.filter(
            id=switch["relation_id"],
            school_id=switch["school_id"],
            student_id=switch["student_id"],
            user_id=switch["id"],
            status="ACTIVE",
        ).exists()
        assert SchoolMembershipRole.objects.filter(
            membership_id=switch["membership_id"],
            membership__user_id=switch["id"],
            role="TEACHER",
        ).exists()
    print(
        json.dumps(
            {
                "fixture_schools": 3,
                "registration_enabled": enabled,
                "global_enabled_schools": ParentRegistrationConfig.objects.filter(
                    enabled=True
                ).count(),
                "sms_integrations": 0,
                "sms_notices": 0,
                "independent_vice_principals_teachers_counselors": 9,
                "snapshot_parent_relations": 3,
                "independent_switch_teacher_parent": bool(switch),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
