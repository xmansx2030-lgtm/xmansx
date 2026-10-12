"""Capture aggregate restore evidence without exposing school or student details."""

import hashlib
import json
import sys

sys.path.insert(0, "/app")

import django
from django.apps import apps
from django.db import connection, models

django.setup()

result = {
    "models": {},
    "row_digests": {},
    "files": {},
    "encrypted_identifiers": {"checked": 0, "errors": 0},
}
with connection.cursor() as cursor:
    cursor.execute("SELECT set_config('app.rls_bypass', 'on', false)")
    cursor.execute(
        "SELECT current_user, rolsuper, rolbypassrls FROM pg_roles WHERE rolname=current_user"
    )
    _, superuser, bypass = cursor.fetchone()
    result["role"] = {"superuser": superuser, "bypassrls": bypass}
    cursor.execute("SELECT count(*) FROM django_migrations")
    result["migration_count"] = cursor.fetchone()[0]

for model in apps.get_models():
    if not model._meta.managed or model._meta.proxy:
        continue
    result["models"][model._meta.label] = model.objects.count()
    digest = hashlib.sha256()
    for row in model.objects.order_by("pk").values().iterator(chunk_size=250):
        digest.update(json.dumps(row, sort_keys=True, default=str).encode())
        digest.update(b"\n")
    result["row_digests"][model._meta.label] = digest.hexdigest()
    for field in model._meta.fields:
        if isinstance(field, models.FileField):
            result["files"][f"{model._meta.label}.{field.name}"] = (
                model.objects.exclude(**{field.name: ""})
                .exclude(**{f"{field.name}__isnull": True})
                .count()
            )

from common.security.identifiers import decrypt_national_id, national_id_lookup_hash
from schools.models import School
from students.models import Student

for school_id in School.objects.values_list("pk", flat=True):
    sample = (
        Student.objects.filter(school_id=school_id)
        .order_by("pk")
        .values("national_id_encrypted", "national_id_lookup_hash")
        .first()
    )
    if sample:
        result["encrypted_identifiers"]["checked"] += 1
        try:
            plaintext = decrypt_national_id(sample["national_id_encrypted"])
            if national_id_lookup_hash(plaintext) != sample["national_id_lookup_hash"]:
                result["encrypted_identifiers"]["errors"] += 1
            del plaintext
        except Exception:
            result["encrypted_identifiers"]["errors"] += 1

with connection.cursor() as cursor:
    cursor.execute("SELECT set_config('app.rls_bypass', 'off', false)")
result["tenant_context_empty"] = {
    "schools_visible": School.objects.count(),
    "students_visible": Student.objects.count(),
}
print(json.dumps(result, sort_keys=True))
