"""Read-only runtime checks for the exact restricted synthetic TLS application.

Run in staging-app, not in the owner/tests container. Never prints key material,
connection strings, account data or file names. Worker/Beat checks use the real
broker and the existing heartbeat written by a real scheduled task.
"""

import json
import os
import stat
import sys
from pathlib import Path
from urllib.parse import urlsplit

import django
import redis
from django.conf import settings
from django.core.files.storage import FileSystemStorage, storages
from django.db import connection


def main():
    if (
        os.environ.get("DJANGO_SETTINGS_MODULE") != "config.settings.parent_staging"
        or os.environ.get("PARENT_STAGING_LOCAL_ONLY") != "1"
        or os.getuid() != 65534
    ):
        raise RuntimeError(
            "Runtime checks require the isolated non-root staging application"
        )
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
    django.setup()
    from common.health import _check_database, _check_redis
    from common.redis_services import configured_redis_urls
    from operations.health import check_beat, check_worker

    assert settings.DEBUG is False
    assert settings.DATABASE_RLS_ENFORCED is True
    assert settings.SECURE_SSL_REDIRECT is True
    assert settings.SESSION_COOKIE_SECURE is True
    assert settings.CSRF_COOKIE_SECURE is True
    assert settings.SELF_REGISTRATION_ENABLED is False
    assert settings.PARENT_RECOVERY_EMAIL_ENABLED is True
    assert settings.PARENT_RECOVERY_EMAIL_ADAPTER == "synthetic-file"
    assert not settings.RESEND_API_KEY
    assert settings.ALLOWED_HOSTS == ["localhost"]
    assert settings.CSRF_TRUSTED_ORIGINS == ["https://localhost:8445"]
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT current_user, rolsuper, rolbypassrls FROM pg_roles "
            "WHERE rolname = current_user"
        )
        assert cursor.fetchone() == ("parent_verify_app", False, False)
        cursor.execute("SHOW row_security")
        assert cursor.fetchone() == ("on",)
        cursor.execute(
            "SELECT COUNT(*) FROM pg_class WHERE relkind = 'r' "
            "AND relrowsecurity AND relforcerowsecurity"
        )
        forced_tables = cursor.fetchone()[0]
        assert forced_tables >= 59
    routes = Path("/proc/net/route").read_text().splitlines()[1:]
    assert all(route.split()[1] != "00000000" for route in routes)
    redis_roles = {}
    for role, url in configured_redis_urls().items():
        parsed = urlsplit(url)
        assert parsed.hostname == "redis"
        redis_roles[role] = int(parsed.path.lstrip("/") or "0")
    assert redis_roles == {
        "cache": 0,
        "security": 1,
        "celery_broker": 3,
        "celery_results": 4,
        "legacy": 0,
    }
    client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        assert client.config_get("maxmemory-policy") == {
            "maxmemory-policy": "noeviction"
        }
    finally:
        client.close()
    assert settings.STORAGES["backups"]["BACKEND"] == "django.core.files.storage.FileSystemStorage"
    repository = storages["backups"]
    assert isinstance(repository, FileSystemStorage)
    roots = {
        "private": Path(settings.GENERATED_DOCUMENTS_ROOT),
        "backups": Path(settings.DATABASE_BACKUP_ROOT),
        "repository": Path(repository.location),
        "email-outbox": Path(settings.PARENT_RECOVERY_SYNTHETIC_EMAIL_ROOT),
    }
    for name, root in roots.items():
        expected_root = Path("/var/lib/xmansx-parent-staging") / name
        assert root == expected_root and root.resolve() == expected_root
        assert root.is_dir() and not root.is_symlink() and root.is_mount()
        for path in [root, *root.rglob("*")]:
            assert not path.is_symlink() and path.resolve().is_relative_to(root)
            metadata = path.stat()
            assert metadata.st_uid == 65534
            assert stat.S_IMODE(metadata.st_mode) == (0o700 if path.is_dir() else 0o600)
    assert _check_database() and _check_redis()
    assert check_worker() == "ok"
    beat, age = check_beat()
    assert beat == "ok"
    print(
        json.dumps(
            {
                "runtime": "ok",
                "uid": os.getuid(),
                "debug": False,
                "database_role": "NOSUPERUSER NOBYPASSRLS",
                "forced_rls_tables": forced_tables,
                "https_secure_cookies": True,
                "public_school_self_registration": False,
                "recovery_email_provider": "synthetic-file; no external sending",
                "external_default_route": False,
                "redis_policy": "noeviction",
                "redis_logical_databases": redis_roles,
                "private_storage_permissions": "0700 directories / 0600 files",
                "worker": "ok",
                "beat": "ok",
                "beat_heartbeat_age_seconds": round(age, 1),
                "existing_database_redis_readiness": "ok",
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
