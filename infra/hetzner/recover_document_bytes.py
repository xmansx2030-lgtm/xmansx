"""Recover a missing PDF only when its exact bytes match the issued SHA-256.

The stored snapshot, template version, filename, status and checksum remain
unchanged. A mismatch is reported and never saved as a replacement document.
"""

import argparse
import hashlib
import json
import logging
import sys

sys.path.insert(0, "/app")

import django

django.setup()

from django.core.files.base import ContentFile

from common.tenant_rls import tenant_context
from documents.models import GeneratedDocument
from documents.templates_registry import template_of
from documents.services.generation import _render

parser = argparse.ArgumentParser()
parser.add_argument("--save-matching", action="store_true")
options = parser.parse_args()
logging.getLogger("fontTools").setLevel(logging.ERROR)
result = {
    "checked": 0,
    "already_present": 0,
    "exact_matches": 0,
    "saved": 0,
    "mismatches": 0,
    "template_mismatches": 0,
    "errors": 0,
}
with tenant_context(bypass=True):
    for document in (
        GeneratedDocument.objects.exclude(file="").exclude(file__isnull=True).iterator()
    ):
        if document.file.storage.exists(document.file.name):
            result["already_present"] += 1
            continue
        result["checked"] += 1
        try:
            template = template_of(document)
            if (
                template.key != document.template_key
                or template.version != document.template_version
            ):
                result["template_mismatches"] += 1
                continue
            pdf = _render(template=template, snapshot=document.snapshot_data)
            if (
                len(pdf) != document.size_bytes
                or hashlib.sha256(pdf).hexdigest() != document.checksum
            ):
                result["mismatches"] += 1
                continue
            result["exact_matches"] += 1
            if options.save_matching:
                name = document.file.storage.save(document.file.name, ContentFile(pdf))
                assert name == document.file.name, "Storage changed the original key"
                result["saved"] += 1
        except Exception:
            result["errors"] += 1
print(json.dumps(result, sort_keys=True))
