from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from django.core.cache import cache
from django.core.files import File
from django.utils import timezone

from documents.models import GeneratedDocument
from excuses.models import AbsenceExcuseAttachment
from operations.error_tracking import capture_operational_failure
from operations.models import BackupRun, BackupStatus, BackupType


def _records():
    yield "excuse_attachment", AbsenceExcuseAttachment, "file"
    yield "generated_document", GeneratedDocument, "file"


def _storage_checksum(storage, name: str) -> str:
    digest = hashlib.sha256()
    with storage.open(name, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _local_checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_storage_integrity(*, verify_checksums: bool = True) -> dict:
    result = {"checked": 0, "missing": 0, "checksum_mismatch": 0, "errors": 0}
    for _, model, field_name in _records():
        queryset = model.objects.exclude(**{field_name: ""}).exclude(
            **{f"{field_name}__isnull": True}
        )
        for instance in queryset.iterator(chunk_size=200):
            result["checked"] += 1
            field = getattr(instance, field_name)
            try:
                if not field.storage.exists(field.name):
                    result["missing"] += 1
                    continue
                expected = getattr(instance, "checksum", "")
                if (
                    verify_checksums
                    and expected
                    and _storage_checksum(field.storage, field.name) != expected
                ):
                    result["checksum_mismatch"] += 1
            except Exception:
                result["errors"] += 1
    if any(result[key] for key in ("missing", "checksum_mismatch", "errors")):
        capture_operational_failure("STORAGE_INTEGRITY_FAILED")
    cache.set(
        "operations:storage-integrity",
        {
            "status": "ok"
            if not any(result[key] for key in ("missing", "checksum_mismatch", "errors"))
            else "failed",
            "checked_at": timezone.now().isoformat(),
            **result,
        },
        timeout=7 * 24 * 60 * 60,
    )
    return result


def backup_private_objects(destination: Path) -> tuple[BackupRun, Path]:
    started_at = timezone.now()
    run = BackupRun.objects.create(
        backup_type=BackupType.PRIVATE_OBJECTS,
        status=BackupStatus.RUNNING,
        started_at=started_at,
    )
    began = time.perf_counter()
    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    entries = []
    total_size = 0
    try:
        for kind, model, field_name in _records():
            queryset = model.objects.exclude(**{field_name: ""}).exclude(
                **{f"{field_name}__isnull": True}
            )
            for instance in queryset.iterator(chunk_size=200):
                field = getattr(instance, field_name)
                relative = Path("objects") / kind / str(instance.pk) / Path(field.name).name
                target = destination / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                digest = hashlib.sha256()
                size = 0
                with field.storage.open(field.name, "rb") as source, target.open("wb") as output:
                    while chunk := source.read(1024 * 1024):
                        output.write(chunk)
                        digest.update(chunk)
                        size += len(chunk)
                expected = getattr(instance, "checksum", "")
                if expected and digest.hexdigest() != expected:
                    raise RuntimeError("source object checksum mismatch")
                entries.append(
                    {
                        "kind": kind,
                        "id": instance.pk,
                        "storage_key": field.name,
                        "copy": relative.as_posix(),
                        "size_bytes": size,
                        "sha256": digest.hexdigest(),
                    }
                )
                total_size += size
        manifest = {
            "schema_version": 1,
            "created_at": started_at.isoformat(),
            "objects": entries,
        }
        manifest_path = destination / "private-objects.json"
        encoded = json.dumps(manifest, indent=2, sort_keys=True).encode()
        manifest_path.write_bytes(encoded)
        run.status = BackupStatus.SUCCEEDED
        run.finished_at = timezone.now()
        run.size_bytes = total_size
        run.checksum = hashlib.sha256(encoded).hexdigest()
        run.storage_reference = "local:private-objects.json"
        run.duration_ms = int((time.perf_counter() - began) * 1000)
        run.metadata = {"objects": len(entries)}
        run.save()
        return run, manifest_path
    except Exception:
        run.status = BackupStatus.FAILED
        run.finished_at = timezone.now()
        run.duration_ms = int((time.perf_counter() - began) * 1000)
        run.error_code = "OBJECT_BACKUP_FAILED"
        run.save()
        capture_operational_failure(run.error_code)
        raise


def restore_private_objects(source: Path, *, overwrite: bool = False) -> dict:
    source = source.resolve()
    manifest = json.loads((source / "private-objects.json").read_text(encoding="utf-8"))
    restored = skipped = 0
    models = {kind: (model, field) for kind, model, field in _records()}
    for entry in manifest["objects"]:
        model, field_name = models[entry["kind"]]
        instance = model.objects.get(pk=entry["id"])
        field = getattr(instance, field_name)
        copy_path = (source / entry["copy"]).resolve()
        if source not in copy_path.parents or not copy_path.is_file():
            raise RuntimeError("object backup path is invalid or missing")
        if _local_checksum(copy_path) != entry["sha256"]:
            raise RuntimeError("object backup checksum mismatch")
        if field.storage.exists(entry["storage_key"]):
            if not overwrite:
                skipped += 1
                continue
            field.storage.delete(entry["storage_key"])
        with copy_path.open("rb") as stream:
            stored_name = field.storage.save(entry["storage_key"], File(stream))
        if stored_name != entry["storage_key"]:
            raise RuntimeError("storage backend changed the restored object key")
        restored += 1
    return {"restored": restored, "skipped": skipped}
