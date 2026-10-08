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
    from django.conf import settings
    from django.db import connection
    from operations.health import check_beat, check_worker

    assert settings.DEBUG is False
    assert settings.DATABASE_RLS_ENFORCED is True
    assert settings.SECURE_SSL_REDIRECT is True
    assert settings.SESSION_COOKIE_SECURE is True
    assert settings.CSRF_COOKIE_SECURE is True
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
    for name in ("private", "backups", "repository"):
        root = Path("/tmp/parent-verification") / name
        assert root.is_dir() and not root.is_symlink()
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
