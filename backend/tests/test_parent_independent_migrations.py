"""Real baseline-data upgrade and exact PostgreSQL parent security catalog proofs."""

import re
from datetime import date

import pytest
from django.apps import apps
from django.contrib.auth.hashers import make_password
from django.db import DatabaseError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

from common.security.identifiers import (
    encrypt_national_id,
    mask_national_id,
    national_id_lookup_hash,
)
from common.tenant_rls import tenant_context
from parents.models import GuardianContactReview, GuardianStudentRelation
from students.models import Student

PARENT_TABLES = {
    "parents_parentregistrationconfig",
    "parents_guardianstudentrelation",
    "parents_guardianregistrationrequest",
    "parents_guardianactivation",
    "parents_guardiancontactreview",
    "parents_globalmobilechangerequest",
    "parents_recipientcontactblock",
    "parents_parentexcuserequest",
    "parents_parentexcuseattachment",
    "parents_attendancecorrectionrequest",
    "parents_familypublication",
    "parents_warningacknowledgement",
    "parents_familypublicationacknowledgement",
    "parents_parentnotification",
}
RECOVERY_TABLES = {
    "parents_globalaccountrecoverycase",
    "parents_recoveryevidencereference",
    "parents_recoveryreviewauthorization",
    "parents_recoveryreviewdecision",
}
EMAIL_RECOVERY_TABLES = {
    "parents_accountrecoveryemail",
    "parents_accountrecoveryemaildelivery",
}


@pytest.mark.django_db(transaction=True)
def test_upgrade_real_baseline_students_preserves_data_and_old_model_contact_guards():
    assert connection.vendor == "postgresql"
    executor = MigrationExecutor(connection)
    full_targets = executor.loader.graph.leaf_nodes()
    baseline_targets = [
        target for target in full_targets if target[0] not in {"parents", "students"}
    ]
    baseline_targets.append(("students", "0006_student_merged_into"))
    try:
        executor.migrate(baseline_targets)
        state = executor.loader.project_state(baseline_targets).apps
        LegacySchool = state.get_model("schools", "School")
        LegacyUser = state.get_model("accounts", "User")
        LegacyMembership = state.get_model("memberships", "SchoolMembership")
        LegacyYear = state.get_model("academics", "AcademicYear")
        LegacyGrade = state.get_model("students", "Grade")
        LegacySection = state.get_model("students", "Section")
        LegacyStudent = state.get_model("students", "Student")
        LegacyEnrollment = state.get_model("students", "StudentEnrollment")
        LegacySession = state.get_model("attendance", "AttendanceSession")
        LegacyMark = state.get_model("attendance", "AttendanceMark")
        assert "guardian_contact_revision" not in {
            field.name for field in LegacyStudent._meta.fields
        }
        school = LegacySchool.objects.create(name="مدرسة ترقية الاختبار", slug="migration-baseline")
        owner = LegacyUser.objects.create(
            mobile="+966551200001", password=make_password("Proof-Owner-2026!")
        )
        reviewer = LegacyUser.objects.create(
            mobile="+966551200002", password=make_password("Proof-Staff-2026!")
        )
        membership = LegacyMembership.objects.create(school=school, user=reviewer)
        year = LegacyYear.objects.create(
            school=school,
            name="سنة التاريخ المحفوظ",
            start_date=date(2026, 8, 23),
            end_date=date(2027, 6, 25),
            status="ACTIVE",
        )
        grade = LegacyGrade.objects.create(
            school=school, code="SEC_1", name="الأول الثانوي", sequence=10
        )
        section = LegacySection.objects.create(school=school, grade=grade, code="1", name="1")

        def legacy_data(suffix):
            identifier = f"PUPGRADE{suffix:04d}"
            return {
                "school_id": school.id,
                "national_id_encrypted": encrypt_national_id(identifier),
                "national_id_lookup_hash": national_id_lookup_hash(identifier),
                "national_id_masked": mask_national_id(identifier),
                "student_number": f"MIG-{suffix}",
                "full_name": f"طالب بيانات محفوظة {suffix}",
                "guardian_name": "ولي أمر تاريخي موثق",
                "guardian_mobile": owner.mobile,
            }

        existing = LegacyStudent.objects.create(**legacy_data(1))
        enrollment = LegacyEnrollment.objects.create(
            school=school,
            student=existing,
            academic_year=year,
            grade=grade,
            section=section,
            enrolled_at=date(2026, 8, 23),
            status="ACTIVE",
        )
        session = LegacySession.objects.create(
            school=school,
            academic_year=year,
            section=section,
            attendance_date=date(2026, 10, 1),
            period_sequence=1,
            bell_period_snapshot={},
            roster_fingerprint="b" * 64,
            unprepared_alert_minutes_snapshot=10,
            status="SUBMITTED",
            started_by_membership=membership,
            submitted_by_membership=membership,
            submitted_at=timezone.now(),
        )
        mark = LegacyMark.objects.create(
            school=school, session=session, student=existing, status="ABSENT"
        )
        original_fields = [field.attname for field in LegacyStudent._meta.concrete_fields]
        student_before = LegacyStudent.objects.values(*original_fields).get(pk=existing.pk)
        enrollment_before = LegacyEnrollment.objects.values().get(pk=enrollment.pk)
        session_before = LegacySession.objects.values().get(pk=session.pk)
        mark_before = LegacyMark.objects.values().get(pk=mark.pk)

        executor = MigrationExecutor(connection)
        executor.migrate(full_targets)
        assert Student.objects.values(*original_fields).get(pk=existing.pk) == student_before
        assert Student.objects.get(pk=existing.pk).guardian_contact_revision == 1
        assert (
            apps.get_model("students", "StudentEnrollment").objects.values().get(pk=enrollment.pk)
            == enrollment_before
        )
        assert (
            apps.get_model("attendance", "AttendanceSession").objects.values().get(pk=session.pk)
            == session_before
        )
        assert (
            apps.get_model("attendance", "AttendanceMark").objects.values().get(pk=mark.pk)
            == mark_before
        )
        assert not GuardianContactReview.objects.filter(student_id=existing.pk).exists()

        # Models loaded before the upgrade deliberately omit the new revision field.
        old_insert = LegacyStudent.objects.create(**legacy_data(2))
        old_bulk = LegacyStudent(**legacy_data(3))
        LegacyStudent.objects.bulk_create([old_bulk])
        assert Student.objects.get(pk=old_insert.pk).guardian_contact_revision == 1
        assert Student.objects.get(pk=old_bulk.pk).guardian_contact_revision == 1
        relation = GuardianStudentRelation.objects.create(
            school_id=school.id,
            student_id=existing.pk,
            user_id=owner.id,
            status="ACTIVE",
            approved_by_id=reviewer.id,
            approved_at=timezone.now(),
            contact_revision=1,
        )
        original_password = LegacyUser.objects.get(pk=owner.pk).password
        with tenant_context(school_id=school.id, user_id=reviewer.id):
            LegacyStudent.objects.filter(pk=existing.pk).update(guardian_mobile="+966551200009")
            relation.refresh_from_db()
            assert relation.status == "SUSPENDED_CONTACT_REVIEW"
            assert Student.objects.get(pk=existing.pk).guardian_contact_revision == 2
            assert GuardianContactReview.objects.get(student_id=existing.pk).source == "DATABASE"
            with pytest.raises(DatabaseError, match="independent verification"):
                with transaction.atomic():
                    LegacyUser.objects.filter(pk=owner.pk).update(mobile="+966551200008")
        assert LegacyUser.objects.get(pk=owner.pk).mobile == owner.mobile
        assert LegacyUser.objects.get(pk=owner.pk).password == original_password
        assert (
            apps.get_model("attendance", "AttendanceMark").objects.values().get(pk=mark.pk)
            == mark_before
        )
    finally:
        # Restore every leaf even when an assertion fails, before Django flushes
        # the test or any later suite uses the current models.
        MigrationExecutor(connection).migrate(full_targets)


def _canonical(expression):
    if expression is None:
        return None
    return re.sub(r"\s+|[()]|::text", "", expression).lower()


@pytest.mark.django_db
def test_migrated_parent_catalog_has_exact_forced_policies_and_all_identity_guards():
    assert connection.vendor == "postgresql"
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class "
            "WHERE relnamespace = 'public'::regnamespace AND relname LIKE 'parents_%' "
            "AND relkind = 'r'"
        )
        tables = cursor.fetchall()
        assert {name for name, _, _ in tables} == (
            PARENT_TABLES | RECOVERY_TABLES | EMAIL_RECOVERY_TABLES
        )
        assert len(tables) == 20 and all(enabled and forced for _, enabled, forced in tables)
        cursor.execute(
            "SELECT tablename, policyname, cmd, qual, with_check, permissive, roles "
            "FROM pg_policies WHERE schemaname='public' AND tablename LIKE 'parents_%'"
        )
        policies = cursor.fetchall()
        cursor.execute(
            "SELECT table_row.relname, trigger_row.tgname, trigger_row.tgenabled, "
            "trigger_row.tgdeferrable, trigger_row.tginitdeferred, "
            "pg_get_triggerdef(trigger_row.oid) FROM pg_trigger trigger_row "
            "JOIN pg_class table_row ON table_row.oid=trigger_row.tgrelid "
            "WHERE NOT trigger_row.tgisinternal AND table_row.relnamespace='public'::regnamespace"
        )
        triggers = {(row[0], row[1]): row[2:] for row in cursor.fetchall()}
    bypass = "current_setting('app.rls_bypass', true) = 'on'"
    school = "NULLIF(current_setting('app.current_school_id', true), '')::bigint"
    user = "NULLIF(current_setting('app.current_user_id', true), '')::bigint"
    scope = f"{bypass} OR school_id = {school}"
    expected_policies = {}
    for table in PARENT_TABLES:
        select = scope
        if table in {"parents_guardianstudentrelation", "parents_parentnotification"}:
            select += f" OR user_id = {user}"
        elif table == "parents_parentregistrationconfig":
            select = "true"
        elif table == "parents_guardianactivation":
            select += (
                " OR token_hash = NULLIF(current_setting('app.parent_activation_hash', true), '')"
            )
        elif table == "parents_guardianregistrationrequest":
            select += (
                " OR receipt_hash = NULLIF(current_setting('app.parent_receipt_hash', true), '')"
            )
        expected_policies[(table, "parent_select")] = ("SELECT", _canonical(select), None)
        expected_policies[(table, "parent_insert")] = ("INSERT", None, _canonical(scope))
        expected_policies[(table, "parent_update")] = (
            "UPDATE",
            _canonical(scope),
            _canonical(scope),
        )
        expected_policies[(table, "parent_delete")] = ("DELETE", _canonical(scope), None)
    legacy = [row for row in policies if row[1].startswith("parent_")]
    assert len(legacy) == 56
    assert {(row[0], row[1]) for row in legacy} == set(expected_policies)
    for table, name, command, qual, check, permissive, roles in legacy:
        assert (command, _canonical(qual), _canonical(check)) == expected_policies[(table, name)]
        assert permissive == "PERMISSIVE" and roles == ["public"]

    central = "xmansx_recovery_review_stage() IS NOT NULL"
    intake = "xmansx_recovery_school_intake(school_id)"
    purge = "xmansx_recovery_purge_allowed(school_id, student_id)"
    case = "parents_globalaccountrecoverycase"
    new = {
        (case, "recovery_select"): (
            "SELECT",
            _canonical(f"{central} OR {intake} OR {purge}"),
            None,
        ),
        (case, "recovery_insert"): (
            "INSERT",
            None,
            _canonical(f"{intake} AND requested_by_id = {user} AND user_id <> {user}"),
        ),
        (case, "recovery_update"): (
            "UPDATE",
            _canonical(f"({central} AND school_id = {school}) OR {intake}"),
            _canonical(f"({central} AND school_id = {school}) OR {intake}"),
        ),
        (case, "recovery_delete"): ("DELETE", _canonical(purge), None),
        ("parents_globalmobilechangerequest", "recovery_central_source_select"): (
            "SELECT",
            _canonical(central),
            None,
        ),
    }
    for table in {"parents_recoveryevidencereference", "parents_recoveryreviewdecision"}:
        purge_case = (
            "EXISTS (SELECT 1 FROM parents_globalaccountrecoverycase c "  # noqa: S608
            f"WHERE c.id = {table}.case_id "
            "AND xmansx_recovery_purge_allowed(c.school_id, c.student_id))"
        )
        new[(table, "recovery_select")] = ("SELECT", _canonical(f"{central} OR {purge_case}"), None)
        new[(table, "recovery_insert")] = (
            "INSERT",
            None,
            _canonical(f"{central} AND school_id = {school}"),
        )
        new[(table, "recovery_update")] = (
            "UPDATE",
            _canonical(f"{central} AND school_id = {school}"),
            _canonical(f"{central} AND school_id = {school}"),
        )
        new[(table, "recovery_delete")] = ("DELETE", _canonical(purge_case), None)
    grant = "parents_recoveryreviewauthorization"
    new[(grant, "recovery_select")] = ("SELECT", _canonical(f"reviewer_id = {user}"), None)
    new[(grant, "recovery_insert")] = ("INSERT", None, "false")
    new[(grant, "recovery_update")] = ("UPDATE", "false", None)
    new[(grant, "recovery_delete")] = ("DELETE", "false", None)
    additions = [
        row for row in policies
        if row[1].startswith("recovery_") and not row[1].startswith("recovery_email_")
    ]
    assert len(additions) == 17 and len(policies) == 79
    email_policies = [row for row in policies if row[0] in EMAIL_RECOVERY_TABLES]
    assert len(email_policies) == 6
    assert {(row[0], row[2]) for row in email_policies} == {
        (table, command) for table in EMAIL_RECOVERY_TABLES
        for command in ("SELECT", "INSERT", "UPDATE")
    }
    assert all(row[5] == "PERMISSIVE" and row[6] == ["public"] for row in email_policies)
    assert {(row[0], row[1]) for row in additions} == set(new)
    for table, name, command, qual, check, permissive, roles in additions:
        assert (command, _canonical(qual), _canonical(check)) == new[(table, name)]
        assert permissive == "PERMISSIVE" and roles == ["public"]
        assert "rls_bypass" not in (qual or "") + (check or "")

    required = {
        ("students_student", "parent_contact_guard"): "xmansx_parent_contact_guard",
        ("accounts_user", "parent_global_mobile_guard"): "xmansx_parent_global_mobile_guard",
        (
            "parents_guardianstudentrelation",
            "parent_relation_guard",
        ): "xmansx_parent_relation_guard",
        (
            "parents_guardianstudentrelation",
            "parent_identity_immutable",
        ): "xmansx_parent_relation_identity_guard",
    }
    exact_tables = {
        "parents_parentexcuserequest",
        "parents_attendancecorrectionrequest",
        "parents_parentnotification",
        "parents_warningacknowledgement",
        "parents_familypublicationacknowledgement",
        "parents_parentexcuseattachment",
        "parents_familypublication",
        "parents_guardianactivation",
        "parents_guardianregistrationrequest",
        "parents_globalmobilechangerequest",
    }
    for table in exact_tables:
        required[(table, "parent_exact_identity")] = "xmansx_parent_exact_identity_guard"
    for table, guard in (
        ("parents_globalmobilechangerequest", "source"),
        ("parents_globalaccountrecoverycase", "case"),
        ("parents_recoveryevidencereference", "reference"),
        ("parents_recoveryreviewdecision", "decision"),
        ("parents_recoveryreviewauthorization", "authority"),
    ):
        required[(table, f"recovery_{guard}_guard")] = f"xmansx_recovery_{guard}_guard"
    for key, function in required.items():
        enabled, _, _, definition = triggers[key]
        assert enabled == "O" and f"EXECUTE FUNCTION {function}()" in definition
        assert "BEFORE" in definition and "FOR EACH ROW" in definition
    enabled, _, _, definition = triggers[
        ("parents_recoveryevidencereference", "recovery_reference_version")
    ]
    assert enabled == "O" and "AFTER INSERT OR UPDATE" in definition
    assert "EXECUTE FUNCTION xmansx_recovery_reference_version()" in definition
    for model in apps.get_app_config("parents").get_models():
        for field in model._meta.fields:
            if not field.many_to_one or field.related_model is None:
                continue
            if not any(
                candidate.name == "school" for candidate in field.related_model._meta.fields
            ):
                continue
            name = f"same_school_{model._meta.db_table}_{field.column}"[:63]
            enabled, deferrable, deferred, definition = triggers[(model._meta.db_table, name)]
            assert enabled == "O" and deferrable and not deferred
            expected_function = (
                "xmansx_recovery_same_case_school"
                if field.target_field.get_internal_type() == "UUIDField"
                else "xmansx_enforce_same_school_fk"
            )
            assert expected_function in definition
