import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from common.tenant_rls import tenant_context
from operations.restore_verification import verify_restore_manifest


class Command(BaseCommand):
    help = "Compare restored representative records with a pre-backup manifest."

    def add_arguments(self, parser):
        parser.add_argument("--manifest", type=Path, required=True)

    def handle(self, *args, **options):
        try:
            expected = json.loads(options["manifest"].read_text(encoding="utf-8"))
            with tenant_context(bypass=True):
                result = verify_restore_manifest(expected)
        except Exception as exc:
            raise CommandError(f"restored data verification failed: {type(exc).__name__}") from exc
        self.stdout.write(json.dumps(result, sort_keys=True))
