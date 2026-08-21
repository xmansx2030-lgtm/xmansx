from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from operations.restore_verification import capture_restore_manifest, write_manifest


class Command(BaseCommand):
    help = "Capture safe representative record relationships before a restore drill."

    def add_arguments(self, parser):
        parser.add_argument("--school-slug", required=True)
        parser.add_argument("--output", type=Path, required=True)

    def handle(self, *args, **options):
        try:
            manifest = capture_restore_manifest(options["school_slug"])
            write_manifest(options["output"], manifest)
        except Exception as exc:
            raise CommandError(f"restore manifest capture failed: {type(exc).__name__}") from exc
        self.stdout.write(self.style.SUCCESS("restore verification manifest captured"))
