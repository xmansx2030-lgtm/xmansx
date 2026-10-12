"""Write private file recovery metadata; never include document contents."""

import json
import sys

sys.path.insert(0, "/app")
import django

django.setup()

from django.apps import apps
from django.db import models

from common.tenant_rls import tenant_context

files = []
with tenant_context(bypass=True):
    for model in apps.get_models():
        for field in model._meta.fields:
            if not isinstance(field, models.FileField):
                continue
            queryset = model.objects.exclude(**{field.name: ""}).exclude(
                **{f"{field.name}__isnull": True}
            )
            for instance in queryset.iterator():
                value = getattr(instance, field.name)
                files.append(
                    {
                        "model": model._meta.label,
                        "field": field.name,
                        "id": instance.pk,
                        "storage_key": value.name,
                        "size": getattr(instance, "size_bytes", None),
                        "sha256": getattr(instance, "checksum", ""),
                    }
                )
print(json.dumps({"files": files}, sort_keys=True))
