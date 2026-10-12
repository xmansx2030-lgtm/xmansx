"""Archive actual local media/document bytes and verify their private R2 copy.

Missing historical files are recorded as a recovery gap, never reconstructed or
marked recovered. Credentials come from the existing application environment.
"""

import hashlib
import json
import sys
import tarfile
import tempfile
from pathlib import Path

sys.path.insert(0, "/app")
import django

django.setup()

from django.apps import apps
from django.conf import settings
from django.core.files import File
from django.core.files.storage import storages
from django.db import connection, models
from django.utils import timezone


def digest_stream(stream):
    digest = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(chunk)
    return digest.hexdigest()


def main():
    assert not settings.R2_ENABLED, "This archive is for local-file deployments"
    assert settings.BACKUP_REMOTE_ENABLED, "A private remote backup is required"
    roots = {
        "media": Path(settings.MEDIA_ROOT).resolve(),
        "documents": Path(settings.GENERATED_DOCUMENTS_ROOT).resolve(),
    }
    assert len(set(roots.values())) == 2
    stamp = timezone.now()
    missing = []
    with connection.cursor() as cursor:
        cursor.execute("SET app.rls_bypass = 'on'")
    try:
        for model in apps.get_models():
            for field in model._meta.fields:
                if isinstance(field, models.FileField):
                    records = model.objects.exclude(**{field.name: ""}).exclude(
                        **{f"{field.name}__isnull": True}
                    )
                    for record in records.iterator(chunk_size=200):
                        obj = getattr(record, field.name)
                        if not obj.storage.exists(obj.name):
                            missing.append(
                                {
                                    "model": model._meta.label,
                                    "id": record.pk,
                                    "field": field.name,
                                    "key": obj.name,
                                }
                            )
    finally:
        with connection.cursor() as cursor:
            cursor.execute("SET app.rls_bypass = 'off'")

    entries = []
    with tempfile.TemporaryDirectory(prefix="mowadhabah-files-") as directory:
        archive = Path(directory) / f"{stamp:%Y%m%dT%H%M%S%fZ}_files.tar.gz"
        with tarfile.open(archive, "w:gz") as bundle:
            for root_name, root in roots.items():
                assert root.is_dir(), f"Storage root unavailable: {root_name}"
                for path in sorted(root.rglob("*")):
                    assert not path.is_symlink(), "Refusing to follow storage symlinks"
                    if not path.is_file():
                        continue
                    before = path.stat()
                    relative = f"{root_name}/{path.relative_to(root).as_posix()}"
                    with path.open("rb") as stream:
                        checksum = digest_stream(stream)
                    bundle.add(path, arcname=relative, recursive=False)
                    after = path.stat()
                    assert (before.st_size, before.st_mtime_ns) == (
                        after.st_size,
                        after.st_mtime_ns,
                    ), "Storage changed during backup; retry"
                    entries.append(
                        {"path": relative, "size_bytes": before.st_size, "sha256": checksum}
                    )
        with archive.open("rb") as stream:
            checksum = digest_stream(stream)
        manifest = {
            "schema_version": 1,
            "created_at": stamp.isoformat(),
            "filename": archive.name,
            "sha256": checksum,
            "size_bytes": archive.stat().st_size,
            "files": entries,
            "missing_references": missing,
            "historical_storage_complete": not missing,
        }
        encoded = json.dumps(manifest, sort_keys=True, indent=2).encode()
        manifest_path = archive.with_suffix(".json")
        manifest_path.write_bytes(encoded)
        storage = storages["backups"]
        prefix = f"filesystem/{stamp:%Y/%m}"
        archive_key = f"{prefix}/{archive.name}"
        manifest_key = f"{prefix}/{manifest_path.name}"
        assert not storage.exists(archive_key) and not storage.exists(manifest_key)
        with archive.open("rb") as stream:
            assert storage.save(archive_key, File(stream)) == archive_key
        with manifest_path.open("rb") as stream:
            assert storage.save(manifest_key, File(stream)) == manifest_key
        with storage.open(archive_key, "rb") as stream:
            assert digest_stream(stream) == checksum, "Remote storage archive checksum mismatch"
        with storage.open(manifest_key, "rb") as stream:
            assert stream.read() == encoded, "Remote archive manifest mismatch"
        # Verify the tar members against the manifest without extracting them.
        with tarfile.open(archive, "r:gz") as bundle:
            assert set(bundle.getnames()) == {entry["path"] for entry in entries}
            for entry in entries:
                with bundle.extractfile(entry["path"]) as stream:
                    assert digest_stream(stream) == entry["sha256"]
        result = {
            "remote_verified": True,
            "archive_key": archive_key,
            "sha256": checksum,
            "files_archived": len(entries),
            "missing_historical_references": len(missing),
        }
        print(json.dumps(result, sort_keys=True))
        return result


if __name__ == "__main__":
    main()
