from uuid import uuid4

import pytest
from django.db import DatabaseError, connection, transaction
from django.test import override_settings

from common.health import _check_database
from common.tenant_rls import clear_tenant_context, tenant_context
from students.models import Grade, Section, Student


def _student(school, suffix: str) -> Student:
    return Student.objects.create(
        school=school,
        national_id_encrypted=f"encrypted-{suffix}",
        national_id_lookup_hash=suffix * 64,
        national_id_masked=f"******{suffix * 4}",
        full_name=f"طالب {suffix}",
    )


@pytest.mark.django_db(transaction=True)
def test_postgres_rls_fails_closed_and_isolates_each_school(
    make_school, make_user, make_membership
):
    school_a = make_school("مدرسة عزل أ")
    school_b = make_school("مدرسة عزل ب")
    student_a = _student(school_a, "a")
    student_b = _student(school_b, "b")
    user_a = make_user("0550088001")
    user_b = make_user("0550088002")
    membership_a = make_membership(user_a, school_a)
    make_membership(user_b, school_b)

    role_name = f"rls_test_{uuid4().hex}"
    quoted_role = connection.ops.quote_name(role_name)
    try:
        with connection.cursor() as cursor:
            # The local Docker owner is a PostgreSQL superuser and therefore
            # always bypasses RLS. Switch to a least-privileged application-like
            # role so this exercises PostgreSQL's real policy enforcement.
            cursor.execute(f"CREATE ROLE {quoted_role} NOSUPERUSER NOBYPASSRLS")
            cursor.execute(f"GRANT USAGE ON SCHEMA public TO {quoted_role}")
            cursor.execute(f"GRANT SELECT ON students_student TO {quoted_role}")
            cursor.execute(f"GRANT SELECT ON schools_school TO {quoted_role}")
            cursor.execute(
                f"GRANT SELECT ON memberships_schoolmembership TO {quoted_role}"
            )
            cursor.execute(f"SET ROLE {quoted_role}")
        clear_tenant_context()
        with override_settings(DATABASE_RLS_ENFORCED=True):
            assert _check_database()
        # Missing scope is not an accidental all-schools query.
        assert Student.objects.count() == 0
        from schools.models import School

        assert School.objects.count() == 0
        with tenant_context(school_id=school_a.id):
            assert list(Student.objects.values_list("id", flat=True)) == [student_a.id]
            assert list(School.objects.values_list("id", flat=True)) == [school_a.id]
        with tenant_context(school_id=school_b.id):
            assert list(Student.objects.values_list("id", flat=True)) == [student_b.id]
        with tenant_context(user_id=user_a.id):
            from memberships.models import SchoolMembership

            assert list(
                SchoolMembership.objects.values_list("id", flat=True)
            ) == [membership_a.id]
            assert list(School.objects.values_list("id", flat=True)) == [school_a.id]
        with tenant_context(bypass=True):
            assert set(Student.objects.values_list("id", flat=True)) == {
                student_a.id,
                student_b.id,
            }
    finally:
        with connection.cursor() as cursor:
            cursor.execute("RESET ROLE")
            cursor.execute(f"DROP OWNED BY {quoted_role}")
            cursor.execute(f"DROP ROLE IF EXISTS {quoted_role}")
        clear_tenant_context()


@pytest.mark.django_db(transaction=True)
def test_database_rejects_cross_school_foreign_keys(make_school):
    school_a = make_school("مدرسة العلاقة أ")
    school_b = make_school("مدرسة العلاقة ب")
    foreign_grade = Grade.objects.create(
        school=school_b, name="أول", code="G1", sequence=1
    )

    with pytest.raises(DatabaseError, match="cross-school foreign key rejected"):
        with transaction.atomic():
            Section.objects.create(
                school=school_a,
                grade=foreign_grade,
                name="1",
                code="S1",
            )

    assert not Section.objects.filter(school=school_a).exists()
