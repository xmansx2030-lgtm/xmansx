"""A real uncommitted EMAIL insert must prevent rollback from removing its guard."""

import importlib
import secrets
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from queue import Queue
from threading import Event

import pytest
from django.db import DatabaseError, connection, connections, transaction
from django.utils import timezone

from common.tenant_rls import clear_tenant_context, tenant_context
from parents.models import GuardianActivation
from parents.security import token_hash
from tests.test_parent_email_credential_boundary import restricted_role
from tests.test_parent_portal import approve, register
from tests.test_parent_portal import portal_env as _portal_env

portal_env = _portal_env
pytestmark = pytest.mark.django_db(transaction=True)


def test_uncommitted_email_insert_cannot_slip_between_rollback_check_and_guard_removal(portal_env):
    env = portal_env
    item, _ = register(env)
    approve(env, item, delivery="MANUAL")
    migration = importlib.import_module("parents.migrations.0009_email_activation")
    inserted, release_writer = Event(), Event()
    reverse_pid = Queue()

    def writer():
        connections.close_all()
        try:
            with connection.cursor() as cursor:
                cursor.execute(f"SET ROLE {quoted_role}")
            with tenant_context(school_id=env["school"].id), transaction.atomic():
                activation = GuardianActivation.objects.create(
                    school_id=env["school"].id,
                    student_id=env["student"].id,
                    request_id=item.id,
                    token_hash=token_hash(secrets.token_urlsafe(32)),
                    contact_revision=env["student"].guardian_contact_revision,
                    expires_at=timezone.now() + timedelta(hours=1),
                    delivery_channel="EMAIL",
                    email_hash=item.email_hash,
                )
                inserted.set()
                assert release_writer.wait(timeout=20)
            return activation.pk
        finally:
            clear_tenant_context()
            with connection.cursor() as cursor:
                cursor.execute("RESET ROLE")
            connections.close_all()

    def reverse():
        connections.close_all()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_backend_pid()")
                reverse_pid.put(cursor.fetchone()[0])
            try:
                with transaction.atomic(), connection.schema_editor() as editor:
                    migration.backward(None, editor)
            except DatabaseError as error:
                assert "unsafe guard rollback blocked" in str(error)
                return "blocked"
            return "removed"
        finally:
            connections.close_all()

    try:
        with restricted_role():
            with connection.cursor() as cursor:
                cursor.execute("SELECT current_user")
                quoted_role = connection.ops.quote_name(cursor.fetchone()[0])
                # The observer/migration owner needs DDL and pg_stat_activity
                # visibility; the concurrent writer remains genuinely restricted.
                cursor.execute("RESET ROLE")
            with ThreadPoolExecutor(max_workers=2) as pool:
                writer_future = pool.submit(writer)
                assert inserted.wait(timeout=10)
                reverse_future = pool.submit(reverse)
                pid = reverse_pid.get(timeout=10)
                deadline = time.monotonic() + 10
                try:
                    while True:
                        with connection.cursor() as cursor:
                            cursor.execute(
                                "SELECT wait_event_type FROM pg_stat_activity WHERE pid=%s", [pid]
                            )
                            waiting = cursor.fetchone()
                        if waiting and waiting[0] == "Lock":
                            break
                        assert time.monotonic() < deadline, "Rollback did not wait for the writer"
                        time.sleep(0.05)
                finally:
                    release_writer.set()
                activation_id = writer_future.result(timeout=20)
                outcome = reverse_future.result(timeout=20)
        assert outcome == "blocked"
        assert GuardianActivation.objects.get(pk=activation_id).delivery_channel == "EMAIL"
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) FROM pg_trigger WHERE tgname='parent_activation_email_guard'"
            )
            assert cursor.fetchone()[0] == 1
    finally:
        release_writer.set()
        # Restore the real guard after the deliberately failing pre-fix proof,
        # without changing the assertions or hiding the failed outcome.
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) FROM pg_trigger WHERE tgname='parent_activation_email_guard'"
            )
            present = cursor.fetchone()[0]
        if not present:
            with transaction.atomic(), connection.schema_editor() as editor:
                migration.forward(None, editor)
