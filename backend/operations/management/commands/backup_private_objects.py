from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from common.tenant_rls import tenant_context
from operations.storage_integrity import backup_private_objects


class Command(BaseCommand):
    help = "Create a streamed protected copy and manifest for private application objects."

    def add_arguments(self, parser):
        parser.add_argument("--destination", type=Path, required=True)

    def handle(self, *args, **options):
        try:
            with tenant_context(bypass=True):
                run, manifest = backup_private_objects(options["destination"])
        except (OSError, RuntimeError) as exc:
            raise CommandError(f"private object backup failed: {type(exc).__name__}") from exc
        self.stdout.write(
            self.style.SUCCESS(
                f"object backup succeeded id={run.id} objects={run.metadata['objects']} "
                f"size={run.size_bytes} manifest={manifest.name}"
            )
        )
