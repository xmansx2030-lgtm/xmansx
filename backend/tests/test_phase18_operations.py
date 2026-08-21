import hashlib
import json
import logging
import subprocess
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from django.core.cache import cache as django_cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import CommandError, call_command
from django.test import Client, override_settings
from django.utils import timezone

from common.logging import JsonFormatter
from devices.models import AttendanceDevice, DeviceBridgeInstallation
from documents.models import DocumentStatus, DocumentType, GeneratedDocument
from excuses.models import AbsenceExcuse, AbsenceExcuseAttachment, ExcuseReasonType
from operations.backups import (
    BackupAlreadyRunning,
    BackupUploadError,
    ChecksumMismatch,
    DatabaseDumpError,
    RestoreSafetyError,
    create_database_backup,
    restore_database_backup,
    retry_backup_upload,
)
from operations.error_tracking import before_send
from operations.health import bridge_health, check_beat, check_worker
from operations.metrics import registry
from operations.models import BackupRun, BackupStatus
from operations.restore_verification import capture_restore_manifest, verify_restore_manifest
from operations.retention import retained_backup_ids
from operations.storage_integrity import (
    backup_private_objects,
    restore_private_objects,
    verify_storage_integrity,
)
from operations.tasks import BEAT_HEARTBEAT_CACHE_KEY, system_heartbeat
from students.models import Student

pytestmark = pytest.mark.django_db


def test_canonical_liveness_is_process_only_and_safe():
    with patch("common.health._check_database") as database:
        response = Client().get("/api/v1/health/live/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    database.assert_not_called()


def test_canonical_readiness_reports_dependency_failure():
    with (
        patch("common.health._check_database", return_value=True),
        patch("common.health._check_redis", return_value=False),
    ):
        response = Client().get("/api/v1/health/ready/")
    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "checks": {"database": "ok", "redis": "error"},
    }


def test_request_metrics_use_route_template_instead_of_resource_id():
    registry.reset()
    Client().get("/api/v1/health/live/")
    snapshot = registry.snapshot()
    assert snapshot["request_count"] == 1
    assert snapshot["series"][0]["route"] == "api/v1/health/live/"
    assert snapshot["series"][0]["status_class"] == "2xx"


def test_request_id_is_preserved_across_the_health_boundary():
    response = Client().get(
        "/api/v1/health/live/", HTTP_X_REQUEST_ID="phase18-release-request-01"
    )
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "phase18-release-request-01"


def test_json_logging_redacts_sensitive_extra_fields():
    record = logging.LogRecord("test", logging.INFO, __file__, 1, "safe", (), None)
    record.password = "NotForLogs"
    record.metadata = {"national_id": "1234567890", "count": 2}
    payload = json.loads(JsonFormatter().format(record))
    assert payload["password"] == "[Filtered]"
    assert payload["metadata"] == {"national_id": "[Filtered]", "count": 2}
    assert "1234567890" not in json.dumps(payload)


def test_system_heartbeat_proves_beat_to_worker_delivery():
    value = system_heartbeat()
    assert django_cache.get(BEAT_HEARTBEAT_CACHE_KEY) == value
    assert check_beat()[0] == "ok"


@override_settings(OPERATIONAL_HEARTBEAT_MAX_AGE_SECONDS=60)
def test_stale_beat_heartbeat_is_detected():
    django_cache.set(
        BEAT_HEARTBEAT_CACHE_KEY,
        (timezone.now() - timedelta(minutes=5)).isoformat(),
        timeout=600,
    )
    assert check_beat()[0] == "stale"


def test_worker_down_is_reported_predictably():
    inspector = Mock()
    inspector.ping.return_value = None
    with patch("operations.health.current_app.control.inspect", return_value=inspector):
        assert check_worker() == "unavailable"


def test_error_tracking_removes_pii_and_credentials():
    event = {
        "request": {
            "data": {"password": "secret"},
            "cookies": {"sessionid": "secret"},
            "headers": {"Authorization": "secret", "Accept": "application/json"},
        },
        "user": {"id": "student-1"},
        "extra": {"national_id": "1099999999", "count": 1},
    }
    scrubbed = before_send(event, {})
    encoded = json.dumps(scrubbed)
    assert "secret" not in encoded
    assert "1099999999" not in encoded
    assert "user" not in scrubbed
    assert scrubbed["extra"]["count"] == 1


def test_bridge_health_derives_online_stale_offline(make_school):
    school = make_school()
    now = timezone.now()
    bridge = DeviceBridgeInstallation.objects.create(
        school=school,
        installation_name="Phase 18",
        installation_identifier="phase18bridge000000000000000001",
        credential_hash="a" * 64,
        last_seen_at=now,
    )
    AttendanceDevice.objects.create(school=school, name="Online", last_seen_at=now)
    AttendanceDevice.objects.create(
        school=school, name="Stale", last_seen_at=now - timedelta(minutes=3)
    )
    AttendanceDevice.objects.create(
        school=school, name="Offline", last_seen_at=now - timedelta(minutes=10)
    )
    result = bridge_health()
    assert result["bridges"] == {"total": 1, "online": 1, "stale": 0, "offline": 0}
    assert result["devices"] == {"total": 3, "online": 1, "stale": 1, "offline": 1}
    assert bridge.credential_hash not in json.dumps(result)


def test_system_health_is_platform_admin_only(make_user):
    admin = make_user("0550180001", is_superuser=True, is_staff=True)
    client = Client()
    client.force_login(admin)
    with patch("operations.api.operational_snapshot", return_value={"backend": "ok"}):
        assert client.get("/api/v1/platform/system-health/").status_code == 200

    ordinary = make_user("0550180002")
    client.force_login(ordinary)
    assert client.get("/api/v1/platform/system-health/").status_code == 403


def _fake_dump(command, **kwargs):
    output = Path(command[command.index("--file") + 1])
    output.write_bytes(b"PGDMP-phase18-test")
    return subprocess.CompletedProcess(command, 0, b"", b"")


def test_database_backup_writes_checksum_manifest_and_metadata(tmp_path):
    with (
        override_settings(DATABASE_BACKUP_ROOT=str(tmp_path)),
        patch("operations.backups.subprocess.run", side_effect=_fake_dump),
    ):
        run = create_database_backup(local_only=True)
    dump = next(tmp_path.glob("*.dump"))
    manifest = json.loads(next(tmp_path.glob("*.json")).read_text())
    assert run.status == BackupStatus.SUCCEEDED
    assert run.size_bytes == dump.stat().st_size
    assert run.checksum == hashlib.sha256(dump.read_bytes()).hexdigest()
    assert manifest["sha256"] == run.checksum
    assert "password" not in json.dumps(manifest).lower()


def test_pg_dump_failure_is_recorded_as_failed(tmp_path):
    failure = subprocess.CalledProcessError(2, ["pg_dump"])
    with (
        override_settings(DATABASE_BACKUP_ROOT=str(tmp_path)),
        patch("operations.backups.subprocess.run", side_effect=failure),
        pytest.raises(DatabaseDumpError),
    ):
        create_database_backup(local_only=True)
    run = BackupRun.objects.latest("id")
    assert run.status == BackupStatus.FAILED
    assert run.error_code == "PG_DUMP_FAILED"
    assert not list(tmp_path.glob("*.partial"))


def test_concurrent_full_backup_fails_safe(tmp_path):
    with (
        override_settings(DATABASE_BACKUP_ROOT=str(tmp_path)),
        patch(
            "operations.backups.database_backup_lock",
            side_effect=BackupAlreadyRunning("busy"),
        ),
        pytest.raises(BackupAlreadyRunning),
    ):
        create_database_backup(local_only=True)
    run = BackupRun.objects.latest("id")
    assert run.status == BackupStatus.FAILED
    assert run.error_code == "BACKUP_ALREADY_RUNNING"


def test_remote_upload_failure_never_reports_success(tmp_path):
    with (
        override_settings(
            DATABASE_BACKUP_ROOT=str(tmp_path),
            BACKUP_REMOTE_ENABLED=True,
            BACKUP_REQUIRE_REMOTE=True,
        ),
        patch("operations.backups.subprocess.run", side_effect=_fake_dump),
        patch(
            "operations.backups._upload_backup",
            side_effect=BackupUploadError("repository unavailable"),
        ),
        pytest.raises(BackupUploadError),
    ):
        create_database_backup()
    run = BackupRun.objects.latest("id")
    assert run.status == BackupStatus.FAILED
    assert run.error_code == "UPLOAD_FAILED"
    assert run.checksum
    assert run.size_bytes > 0


def test_failed_upload_retry_is_idempotent(tmp_path):
    with (
        override_settings(
            DATABASE_BACKUP_ROOT=str(tmp_path),
            BACKUP_REMOTE_ENABLED=True,
            BACKUP_REQUIRE_REMOTE=True,
        ),
        patch("operations.backups.subprocess.run", side_effect=_fake_dump),
        patch(
            "operations.backups._upload_backup",
            side_effect=BackupUploadError("repository unavailable"),
        ),
        pytest.raises(BackupUploadError),
    ):
        create_database_backup()
    run = BackupRun.objects.latest("id")
    with (
        override_settings(DATABASE_BACKUP_ROOT=str(tmp_path)),
        patch("operations.backups._upload_backup", return_value="database/safe.dump") as upload,
    ):
        recovered = retry_backup_upload(run.id)
        again = retry_backup_upload(run.id)
    assert recovered.status == BackupStatus.SUCCEEDED
    assert again.id == recovered.id
    upload.assert_called_once()


def test_corrupt_backup_is_rejected_before_restore(tmp_path):
    dump = tmp_path / "safe.dump"
    dump.write_bytes(b"corrupted")
    manifest = tmp_path / "safe.json"
    manifest.write_text(json.dumps({"filename": dump.name, "sha256": "0" * 64}), encoding="utf-8")
    with (
        patch("operations.backups.assert_restore_target_safe") as safety,
        patch("operations.backups.subprocess.run") as process,
        pytest.raises(ChecksumMismatch),
    ):
        restore_database_backup(
            dump_path=dump, manifest_path=manifest, target_database="phase18_restore"
        )
    safety.assert_not_called()
    process.assert_not_called()


def test_restore_refuses_current_database(settings):
    from operations.backups import assert_restore_target_safe

    with pytest.raises(RestoreSafetyError):
        assert_restore_target_safe(settings.DATABASES["default"]["NAME"])


def test_restore_command_requires_explicit_confirmation(tmp_path):
    with pytest.raises(CommandError, match="confirm-target-empty"):
        call_command(
            "restore_database_backup",
            backup=tmp_path / "x.dump",
            manifest=tmp_path / "x.json",
            target_db="phase18_restore",
        )


def test_retention_keeps_latest_daily_weekly_monthly_and_latest():
    now = timezone.now()
    runs = [SimpleNamespace(id=i, started_at=now - timedelta(days=i)) for i in range(100)]
    kept = retained_backup_ids(runs)
    assert 0 in kept
    assert len(kept) <= 14
    assert set(range(7)).issubset(kept)


def test_cleanup_dry_run_never_deletes(tmp_path):
    run = BackupRun.objects.create(
        backup_type="DATABASE",
        status=BackupStatus.SUCCEEDED,
        started_at=timezone.now() - timedelta(days=100),
        finished_at=timezone.now() - timedelta(days=100),
        storage_reference="local:old.dump",
    )
    artifact = tmp_path / "old.dump"
    artifact.write_bytes(b"old")
    with override_settings(DATABASE_BACKUP_ROOT=str(tmp_path)):
        call_command("cleanup_backups", "--dry-run")
    run.refresh_from_db()
    assert artifact.exists()
    assert run.storage_reference == "local:old.dump"


def _private_records(make_school, make_user, make_membership):
    school = make_school()
    user = make_user("0550180010")
    membership = make_membership(user, school, ["VICE_PRINCIPAL"])
    student = Student.objects.create(
        school=school,
        national_id_encrypted="encrypted",
        national_id_lookup_hash="1" * 64,
        national_id_masked="******0010",
        full_name="Phase 18 Student",
    )
    excuse = AbsenceExcuse.objects.create(
        school=school,
        student=student,
        reason_type=ExcuseReasonType.OFFICIAL,
        recorded_by_membership=membership,
        recorded_at=timezone.now(),
    )
    attachment_bytes = b"phase18-private-attachment"
    attachment = AbsenceExcuseAttachment.objects.create(
        school=school,
        excuse=excuse,
        file=SimpleUploadedFile("proof.pdf", attachment_bytes, "application/pdf"),
        original_filename="proof.pdf",
        mime_type="application/pdf",
        size_bytes=len(attachment_bytes),
        checksum=hashlib.sha256(attachment_bytes).hexdigest(),
        uploaded_by_membership=membership,
    )
    document_bytes = b"%PDF-1.4 phase18 immutable document"
    document = GeneratedDocument.objects.create(
        school=school,
        student=student,
        document_type=DocumentType.STUDENT_ATTENDANCE_REPORT,
        template_key="phase18",
        template_version="v1",
        status=DocumentStatus.PENDING,
        file=SimpleUploadedFile("document.pdf", document_bytes, "application/pdf"),
        mime_type="application/pdf",
        size_bytes=len(document_bytes),
        checksum=hashlib.sha256(document_bytes).hexdigest(),
        generated_by_membership=membership,
    )
    return attachment, document


def test_private_object_integrity_backup_and_restore(
    tmp_path, make_school, make_user, make_membership
):
    media = tmp_path / "media"
    documents = tmp_path / "documents"
    protected = tmp_path / "protected"
    with override_settings(MEDIA_ROOT=media, GENERATED_DOCUMENTS_ROOT=documents):
        attachment, document = _private_records(make_school, make_user, make_membership)
        assert verify_storage_integrity() == {
            "checked": 2,
            "missing": 0,
            "checksum_mismatch": 0,
            "errors": 0,
        }
        run, manifest = backup_private_objects(protected)
        assert run.status == BackupStatus.SUCCEEDED
        assert manifest.exists()
        attachment.file.storage.delete(attachment.file.name)
        document.file.storage.delete(document.file.name)
        assert verify_storage_integrity()["missing"] == 2
        assert restore_private_objects(protected) == {"restored": 2, "skipped": 0}
        assert verify_storage_integrity()["missing"] == 0
        restored_document = document.file.storage.open(document.file.name).read()
        assert hashlib.sha256(restored_document).hexdigest() == document.checksum


def test_representative_restore_fixture_manifest(tmp_path, monkeypatch):
    monkeypatch.setenv("RESTORE_DRILL_MANAGER_PASSWORD", "Restore-Drill-Pass-2026")
    with override_settings(
        MEDIA_ROOT=tmp_path / "media",
        GENERATED_DOCUMENTS_ROOT=tmp_path / "documents",
    ):
        call_command("seed_restore_drill")
        manifest = capture_restore_manifest("phase18-restore-school-a")
        assert verify_restore_manifest(manifest)["status"] == "pass"
        assert manifest["counts"] == {
            "students": 1,
            "enrollments": 1,
            "attendance": 1,
            "excuses": 1,
            "warnings": 1,
            "documents": 1,
            "referrals": 1,
            "counselor_cases": 1,
            "devices": 1,
        }
        assert len(manifest["subscription"]["entitlements"]) == 13
