from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from common.tenant_rls import tenant_context
from operations.storage_integrity import restore_private_objects


class Command(BaseCommand):
    help = "Restore checksum-verified private objects from a protected copy."

    def add_arguments(self, parser):
        parser.add_argument("--source", type=Path, required=True)
        parser.add_argument("--confirm-restore", action="store_true")
        parser.add_argument("--overwrite", action="store_true")

    def handle(self, *args, **options):
        if not options["confirm_restore"]:
            raise CommandError("--confirm-restore is required")
        try:
            with tenant_context(bypass=True):
                result = restore_private_objects(
                    options["source"], overwrite=options["overwrite"]
                )
        except (OSError, RuntimeError, ValueError, KeyError) as exc:
            raise CommandError(f"private object restore failed: {type(exc).__name__}") from exc
        self.stdout.write(
            self.style.SUCCESS(
                f"object restore succeeded restored={result['restored']} "
                f"skipped={result['skipped']}"
            )
        )
