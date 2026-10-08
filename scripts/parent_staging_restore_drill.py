"""Guarded synthetic backup/restore drill using existing backup services.

The owner maintenance process restores only into a freshly created empty DB and
a separate private directory. It never overwrites the source DB or private files,
drops a DB, exports raw account data, or changes the application's restricted role.
"""

import json
import os
import sys
from pathlib import Path
from uuid import uuid4

import django
import psycopg
from django.conf import settings
from django.db import connection
from django.test import override_settings
from psycopg import sql


def counts(cursor):
    cursor.execute(
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename"
    )
    tables = [row[0] for row in cursor.fetchall()]
    result = {}
    for table in tables:
        cursor.execute(sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(table)))
        result[table] = cursor.fetchone()[0]
    return result


def content_digests(cursor, tables):
    digests = {}
    for table in tables:
        # The backup job is captured while RUNNING and finalized after pg_dump;
        # its audit metadata is expected to differ. Every other table is matched.
        if table == "operations_backuprun":
            continue
        cursor.execute(
            sql.SQL(
                "SELECT md5(string_agg(row_to_json(record)::text, '' "
                "ORDER BY row_to_json(record)::text)) "
                "FROM {} AS record"
            ).format(sql.Identifier(table))
        )
        digests[table] = cursor.fetchone()[0]
    return digests


def main():
    expected = {
        "PARENT_STAGING_LOCAL_ONLY": "1",
        "PARENT_VERIFICATION_LOCAL_ONLY": "1",
        "POSTGRES_DB": "parent_verification",
        "POSTGRES_USER": "parent_verify_owner",
        "POSTGRES_HOST": "postgres",
        "DJANGO_SETTINGS_MODULE": "config.settings.local",
    }
    if (
        any(os.environ.get(key) != value for key, value in expected.items())
        or os.getuid() != 65534
    ):
        raise RuntimeError(
            "Restore drill requires the exact non-root synthetic owner process"
        )
    os.umask(0o077)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
    django.setup()
    from operations.backups import create_database_backup, restore_database_backup
    from operations.storage_integrity import (
        backup_private_objects,
        restore_private_objects,
        verify_storage_integrity,
    )
    from school_sms.models import SchoolSmsIntegration
    from schools.models import School

    assert (
        School.objects.exists()
        and not School.objects.exclude(slug__startswith="parent-e2e-").exists()
    )
    assert SchoolSmsIntegration.objects.count() == 0
    assert settings.BACKUP_REMOTE_ENABLED is False
    assert settings.BACKUP_REQUIRE_REMOTE is False
    roots = {
        "private": Path(settings.GENERATED_DOCUMENTS_ROOT),
        "backups": Path(settings.DATABASE_BACKUP_ROOT),
        "repository": Path(settings.BACKUP_STORAGE_LOCATION),
    }
    for name, root in roots.items():
        expected_root = Path("/var/lib/xmansx-parent-staging") / name
        assert root == expected_root and root.resolve() == expected_root
        assert root.is_dir() and not root.is_symlink() and root.is_mount()
    target_name = f"parent_staging_restore_{uuid4().hex[:12]}"
    object_copy = roots["backups"] / target_name
    private_target = roots["repository"] / target_name
    assert not object_copy.exists() and not private_target.exists()
    object_run, object_manifest = backup_private_objects(object_copy)
    assert object_run.metadata["objects"] > 0
    backup = create_database_backup(local_only=True)
    dump = Path(settings.DATABASE_BACKUP_ROOT) / backup.storage_reference.removeprefix(
        "local:"
    )
    manifest = Path(settings.DATABASE_BACKUP_ROOT) / backup.metadata["manifest"]
    with connection.cursor() as cursor:
        expected_counts = counts(cursor)
        expected_content = content_digests(cursor, expected_counts)
        cursor.execute(
            "SELECT COUNT(*) FROM pg_class WHERE relrowsecurity AND relforcerowsecurity"
        )
        source_forced = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM pg_policy")
        source_policies = cursor.fetchone()[0]
    db = settings.DATABASES["default"]
    admin_args = {
        "host": db["HOST"],
        "port": db["PORT"],
        "user": db["USER"],
        "password": db["PASSWORD"],
    }
    with psycopg.connect(**admin_args, dbname="postgres", autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(target_name)))
    duration_ms = restore_database_backup(
        dump_path=dump, manifest_path=manifest, target_database=target_name
    )
    with (
        psycopg.connect(**admin_args, dbname=target_name) as restored,
        restored.cursor() as cursor,
    ):
        assert counts(cursor) == expected_counts
        assert content_digests(cursor, expected_counts) == expected_content
        cursor.execute(
            "SELECT COUNT(*) FROM pg_class WHERE relrowsecurity AND relforcerowsecurity"
        )
        assert cursor.fetchone()[0] == source_forced
        cursor.execute("SELECT COUNT(*) FROM pg_policy")
        assert cursor.fetchone()[0] == source_policies
    # This standalone maintenance process now reads only the restored database.
    # The Gunicorn/Worker connections and original database stay unchanged.
    connection.close()
    connection.settings_dict["NAME"] = target_name
    with override_settings(
        GENERATED_DOCUMENTS_ROOT=private_target,
        FILE_UPLOAD_PERMISSIONS=0o600,
        FILE_UPLOAD_DIRECTORY_PERMISSIONS=0o700,
    ):
        restored_objects = restore_private_objects(object_copy)
        integrity = verify_storage_integrity()
    assert restored_objects == {
        "restored": object_run.metadata["objects"],
        "skipped": 0,
    }
    assert integrity["checked"] == object_run.metadata["objects"]
    assert (
        integrity["missing"]
        == integrity["checksum_mismatch"]
        == integrity["errors"]
        == 0
    )
    assert object_manifest.is_file()
    print(
        json.dumps(
            {
                "drill": "ok",
                "source_database_not_overwritten": True,
                "source_private_files_not_overwritten": True,
                "restore_target": target_name,
                "restored_tables": len(expected_counts),
                "content_verified_tables": len(expected_content),
                "forced_rls_tables": source_forced,
                "rls_policies": source_policies,
                "database_restore_duration_ms": duration_ms,
                "private_objects": restored_objects["restored"],
                "private_integrity": integrity,
                "external_backup_upload": False,
                "application_role_unchanged": True,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
