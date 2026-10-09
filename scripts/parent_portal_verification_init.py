"""Prepare an isolated synthetic verification database and restricted HTTP role.

Run only via docker-compose.parent-verification.yml's tests service. Credentials
are public local-test constants. No production storage/provider is configured.
"""

import os
import sys
from pathlib import Path

import django
from django.core.management import call_command
from django.db import connection
from psycopg import sql


def main():
    if os.environ.get("PARENT_VERIFICATION_LOCAL_ONLY") != "1":
        raise RuntimeError("Explicit local verification environment required")
    expected = {
        "POSTGRES_DB": "parent_verification",
        "POSTGRES_USER": "parent_verify_owner",
        "POSTGRES_HOST": "postgres",
    }
    if any(os.environ.get(key) != value for key, value in expected.items()):
        raise RuntimeError("Refusing to initialize an unrelated database")
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
    os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings.local"
    django.setup()
    call_command("migrate", interactive=False)
    role = "parent_verify_app"
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", [role])
        verb = "ALTER" if cursor.fetchone() else "CREATE"
        cursor.execute(
            sql.SQL("{} ROLE {} LOGIN NOSUPERUSER NOBYPASSRLS NOINHERIT PASSWORD {}").format(
                sql.SQL(verb), sql.Identifier(role), sql.Literal("parent-verify-app-local-only")
            )
        )
        cursor.execute(
            sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                sql.Identifier("parent_verification"), sql.Identifier(role)
            )
        )
        cursor.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(role)))
        cursor.execute(
            sql.SQL("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {}")
            .format(sql.Identifier(role))
        )
        cursor.execute(
            sql.SQL("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {}")
            .format(sql.Identifier(role))
        )
        cursor.execute("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = %s", [role])
        assert cursor.fetchone() == (False, False)
    print("Isolated verification database ready; HTTP role NOSUPERUSER NOBYPASSRLS")


if __name__ == "__main__":
    main()
