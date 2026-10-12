"""Prove a synthetic file round trip in an isolated container and R2 prefix."""

import io
import json
import os
import sys
import tarfile
from pathlib import Path

assert os.environ["POSTGRES_DB"] == "mowadhabah_registration_drill_20261012"
assert os.environ["R2_BACKUPS_PREFIX"] == "migration-drill-20261012-storage"
assert os.environ["MEDIA_ROOT"] == "/tmp/storage-drill/media"
assert os.environ["GENERATED_DOCUMENTS_ROOT"] == "/tmp/storage-drill/documents"
samples = {
    "media/restore-drill.bin": bytes(range(256)),
    "documents/restore-drill.txt": "اختبار استعادة الملفات".encode(),
}
for name, content in samples.items():
    path = Path("/tmp/storage-drill") / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)

sys.path.insert(0, "/tmp")
import backup_storage
from django.core.files.storage import storages

result = backup_storage.main()
with storages["backups"].open(result["archive_key"], "rb") as remote:
    encoded = remote.read()
with tarfile.open(fileobj=io.BytesIO(encoded), mode="r:gz") as bundle:
    restored = {member.name: bundle.extractfile(member).read() for member in bundle}
assert restored == samples, "Remote archive bytes differ from synthetic source files"
print(
    json.dumps(
        {
            "synthetic_files_recovered_exactly": len(samples),
            "production_files_created": 0,
            "production_database_modified": False,
        }
    )
)
