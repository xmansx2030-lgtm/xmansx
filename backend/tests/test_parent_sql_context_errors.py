"""Raw SQL failures retain their cause and restore scopes after atomic rollback."""

import pytest
from django.db import DataError, connection, transaction

from common.tenant_rls import tenant_context
from parents.contact_security import contact_write_context
from parents.services import bearer_context


@pytest.mark.django_db(transaction=True)
def test_raw_sql_abort_preserves_original_error_and_restores_outer_context(make_school, make_user):
    school = make_school()
    actor = make_user("0551900091")
    with tenant_context(school_id=school.id, user_id=actor.id):
        with pytest.raises(DataError, match="division by zero"):
            with (
                transaction.atomic(),
                contact_write_context(source="TEST", actor=actor),
                bearer_context("activation", "a" * 64),
            ):
                with connection.cursor() as cursor:
                    cursor.execute("SELECT 1/0")
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT current_setting('app.current_school_id', true), "
                "current_setting('app.current_user_id', true), "
                "current_setting('app.parent_activation_hash', true), "
                "current_setting('app.parent_contact_source', true)"
            )
            scoped_school, scoped_user, bearer, source = cursor.fetchone()
        assert scoped_school == str(school.id)
        assert scoped_user == str(actor.id)
        assert not bearer and not source
