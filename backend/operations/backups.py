from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path

import psycopg
from django.conf import settings
from django.core.files import File
from django.core.files.storage import storages
from django.db import connection, transaction
from django.utils import timezone

from operations.error_tracking import capture_operational_failure
from operations.models import BackupRun, BackupStatus, BackupType

BACKUP_LOCK_ID = 8_814_218_018
_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,62}$")
logger = logging.getLogger("xmansx.backups")


class BackupError(RuntimeError):
    code = "BACKUP_FAILED"


class BackupAlreadyRunning(BackupError):
    code = "BACKUP_ALREADY_RUNNING"


class BackupUploadError(BackupError):
    code = "UPLOAD_FAILED"


class DatabaseDumpError(BackupError):
    code = "PG_DUMP_FAILED"


class RestoreExecutionError(BackupError):
    code = "PG_RESTORE_FAILED"


class ChecksumMismatch(BackupError):
    code = "CHECKSUM_MISMATCH"


class RestoreSafetyError(BackupError):
    code = "RESTORE_SAFETY_CHECK_FAILED"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_checksum(path: Path, expected: str) -> None:
    if not re.fullmatch(r"[0-9a-f]{64}", expected) or sha256_file(path) != expected:
        raise ChecksumMismatch("backup checksum mismatch")


def _safe_environment() -> str:
    value = re.sub(r"[^A-Za-z0-9_-]", "-", settings.BACKUP_ENVIRONMENT)[:32]
    return value or "unknown"


def _database_config() -> dict:
    return settings.DATABASES["default"]


def _postgres_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PGPASSWORD"] = str(_database_config()["PASSWORD"])
    # pg_dump opens a separate connection, so it cannot inherit the Django
    # connection context. Backups are an explicit, audited cross-tenant operation.
    existing_options = env.get("PGOPTIONS", "").strip()
    bypass_option = "-c app.rls_bypass=on"
    env["PGOPTIONS"] = f"{existing_options} {bypass_option}".strip()
    return env


def _postgres_args() -> list[str]:
    config = _database_config()
    return [
        "--host",
        str(config["HOST"]),
        "--port",
        str(config["PORT"]),
        "--username",
        str(config["USER"]),
    ]


@contextmanager
def database_backup_lock():
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s)", [BACKUP_LOCK_ID])
        if not cursor.fetchone()[0]:
            raise BackupAlreadyRunning("another full database backup is already running")
    try:
        yield
    finally:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock(%s)", [BACKUP_LOCK_ID])


def _upload_backup(dump_path: Path, manifest_path: Path, prefix: str) -> str:
    storage = storages["backups"]
    dump_key = f"{prefix}/{dump_path.name}"
    manifest_key = f"{prefix}/{manifest_path.name}"
    try:
        dump_exists = storage.exists(dump_key)
        manifest_exists = storage.exists(manifest_key)
        if dump_exists and manifest_exists:
            return dump_key
        if dump_exists or manifest_exists:
            storage.delete(dump_key)
            storage.delete(manifest_key)
        with dump_path.open("rb") as stream:
            stored_dump_key = storage.save(dump_key, File(stream))
        with manifest_path.open("rb") as stream:
            storage.save(manifest_key, File(stream))
    except Exception as exc:
        try:
            storage.delete(dump_key)
            storage.delete(manifest_key)
        except Exception:
            logger.warning("partial_backup_upload_cleanup_failed")
        raise BackupUploadError("backup repository upload failed") from exc
    return stored_dump_key


def create_database_backup(*, local_only: bool = False) -> BackupRun:
    started_at = timezone.now()
    run = BackupRun.objects.create(
        backup_type=BackupType.DATABASE,
        status=BackupStatus.RUNNING,
        started_at=started_at,
    )
    root = Path(settings.DATABASE_BACKUP_ROOT).resolve()
    root.mkdir(parents=True, exist_ok=True)
    timestamp = started_at.strftime("%Y%m%dT%H%M%SZ")
    database_id = re.sub(r"[^A-Za-z0-9_-]", "-", str(_database_config()["NAME"]))[:32]
    stem = f"{timestamp}_{_safe_environment()}_{database_id}"
    partial = root / f"{stem}.dump.partial"
    dump_path = root / f"{stem}.dump"
    manifest_path = root / f"{stem}.json"
    began = time.perf_counter()
    try:
        with database_backup_lock():
            command = [
                settings.PG_DUMP_BINARY,
                *_postgres_args(),
                "--format=custom",
                "--no-owner",
                "--no-privileges",
                "--file",
                str(partial),
                str(_database_config()["NAME"]),
            ]
            try:
                subprocess.run(  # noqa: S603 - fixed executable and argument list, no shell
                    command,
                    env=_postgres_env(),
                    check=True,
                    capture_output=True,
                    timeout=settings.BACKUP_COMMAND_TIMEOUT_SECONDS,
                )
            except (OSError, subprocess.SubprocessError) as exc:
                raise DatabaseDumpError("PostgreSQL dump command failed") from exc
            partial.replace(dump_path)
            checksum = sha256_file(dump_path)
            size = dump_path.stat().st_size
            manifest = {
                "schema_version": 1,
                "backup_type": "postgresql",
                "created_at": started_at.isoformat(),
                "environment": _safe_environment(),
                "database_id": database_id,
                "filename": dump_path.name,
                "format": "custom",
                "sha256": checksum,
                "size_bytes": size,
            }
            manifest_path.write_text(
                json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
            )
            run.size_bytes = size
            run.checksum = checksum
            run.duration_ms = int((time.perf_counter() - began) * 1000)
            run.metadata = {"manifest": manifest_path.name, "format": "custom"}
            run.save(
                update_fields=["size_bytes", "checksum", "duration_ms", "metadata", "updated_at"]
            )
            if settings.BACKUP_REQUIRE_REMOTE and local_only:
                raise BackupUploadError("local-only backups are forbidden by this environment")
            if settings.BACKUP_REMOTE_ENABLED and not local_only:
                storage_reference = _upload_backup(
                    dump_path, manifest_path, f"database/{started_at:%Y/%m}"
                )
            elif settings.BACKUP_REQUIRE_REMOTE:
                raise BackupUploadError("remote backup repository is required")
            else:
                storage_reference = f"local:{dump_path.name}"
            run.status = BackupStatus.SUCCEEDED
            run.finished_at = timezone.now()
            run.storage_reference = storage_reference
            run.duration_ms = int((time.perf_counter() - began) * 1000)
            run.save()
            return run
    except Exception as exc:
        partial.unlink(missing_ok=True)
        run.status = BackupStatus.FAILED
        run.finished_at = timezone.now()
        run.duration_ms = int((time.perf_counter() - began) * 1000)
        run.error_code = getattr(exc, "code", "PG_DUMP_FAILED")
        run.save()
        capture_operational_failure(run.error_code)
        raise


def retry_backup_upload(run_id: int) -> BackupRun:
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", [BACKUP_LOCK_ID])
        run = BackupRun.objects.select_for_update().get(pk=run_id)
        if run.status == BackupStatus.SUCCEEDED:
            return run
        if run.status != BackupStatus.FAILED or run.error_code != "UPLOAD_FAILED":
            raise BackupUploadError("only failed repository uploads can be retried")
        root = Path(settings.DATABASE_BACKUP_ROOT).resolve()
        manifest_name = run.metadata.get("manifest", "")
        manifest_path = (root / manifest_name).resolve()
        if manifest_path.parent != root or not manifest_path.is_file():
            raise BackupUploadError("backup manifest is unavailable for retry")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        dump_path = (root / str(manifest.get("filename", ""))).resolve()
        if dump_path.parent != root or not dump_path.is_file():
            raise BackupUploadError("backup dump is unavailable for retry")
        verify_checksum(dump_path, run.checksum)
        reference = _upload_backup(dump_path, manifest_path, f"database/{run.started_at:%Y/%m}")
        run.status = BackupStatus.SUCCEEDED
        run.finished_at = timezone.now()
        run.storage_reference = reference
        run.error_code = ""
        run.save(
            update_fields=[
                "status",
                "finished_at",
                "storage_reference",
                "error_code",
                "updated_at",
            ]
        )
        return run


def _target_connection_kwargs(target_database: str) -> dict:
    config = _database_config()
    return {
        "dbname": target_database,
        "user": config["USER"],
        "password": config["PASSWORD"],
        "host": config["HOST"],
        "port": config["PORT"],
    }


def assert_restore_target_safe(target_database: str) -> None:
    if not _SAFE_IDENTIFIER.fullmatch(target_database):
        raise RestoreSafetyError("target database name is invalid")
    if target_database == str(_database_config()["NAME"]):
        raise RestoreSafetyError("refusing to restore over the running application database")
    with psycopg.connect(**_target_connection_kwargs(target_database)) as target:
        with target.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_schema NOT IN ('pg_catalog', 'information_schema')"
            )
            if cursor.fetchone()[0]:
                raise RestoreSafetyError("target database must be empty")


def restore_database_backup(*, dump_path: Path, manifest_path: Path, target_database: str) -> int:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("filename") != dump_path.name:
        raise ChecksumMismatch("backup manifest does not match the dump filename")
    verify_checksum(dump_path, str(manifest.get("sha256", "")))
    assert_restore_target_safe(target_database)
    command = [
        settings.PG_RESTORE_BINARY,
        *_postgres_args(),
        "--dbname",
        target_database,
        "--exit-on-error",
        "--no-owner",
        "--no-privileges",
        str(dump_path),
    ]
    began = time.perf_counter()
    try:
        subprocess.run(  # noqa: S603 - validated DB name and fixed argument list, no shell
            command,
            env=_postgres_env(),
            check=True,
            capture_output=True,
            timeout=settings.RESTORE_COMMAND_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RestoreExecutionError("PostgreSQL restore command failed") from exc
    return int((time.perf_counter() - began) * 1000)
