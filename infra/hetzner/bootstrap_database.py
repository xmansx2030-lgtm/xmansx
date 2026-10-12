"""Create the restricted application role only in an empty replacement database."""

import os

import psycopg
from psycopg import sql

database = os.environ["POSTGRES_DB"]
app_user = os.environ["POSTGRES_USER"]
app_password = os.environ["POSTGRES_PASSWORD"]
assert database == "mowadhabah", "Unexpected replacement database"
assert app_user == "mowadhabah_app", "Unexpected application role"
connection_options = {
    "host": "postgres",
    "port": 5432,
    "user": "postgres",
    "password": os.environ["POSTGRES_ADMIN_PASSWORD"],
    "connect_timeout": 10,
    "autocommit": True,
}
with psycopg.connect(dbname=database, **connection_options) as connection:
    with connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM pg_tables WHERE schemaname = 'public'")
        assert cursor.fetchone()[0] == 0, "Refusing to initialize a non-empty database"
        cursor.execute("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = %s", [app_user])
        existing_role = cursor.fetchone()
        if existing_role is None:
            cursor.execute(
                sql.SQL(
                    "CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE"
                ).format(sql.Identifier(app_user), sql.Literal(app_password))
            )
        else:
            assert existing_role == (False, False), (
                "Application role must preserve tenant isolation"
            )
        cursor.execute(
            sql.SQL("ALTER DATABASE {} OWNER TO {}").format(
                sql.Identifier(database), sql.Identifier(app_user)
            )
        )
        cursor.execute(sql.SQL("ALTER SCHEMA public OWNER TO {}").format(sql.Identifier(app_user)))
print("Replacement database is empty; application role is NOSUPERUSER NOBYPASSRLS")
