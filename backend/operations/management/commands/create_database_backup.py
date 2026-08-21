from django.core.management.base import BaseCommand, CommandError

from operations.backups import BackupError, create_database_backup


class Command(BaseCommand):
    help = "Create a PostgreSQL custom-format backup and checksum manifest."

    def add_arguments(self, parser):
        parser.add_argument(
            "--local-only",
            action="store_true",
            help="Use only the local drill repository; forbidden when remote storage is required.",
        )

    def handle(self, *args, **options):
        try:
            run = create_database_backup(local_only=options["local_only"])
        except (BackupError, OSError) as exc:
            raise CommandError(f"database backup failed: {type(exc).__name__}") from exc
        self.stdout.write(
            self.style.SUCCESS(
                f"backup succeeded id={run.id} size={run.size_bytes} "
                f"sha256={run.checksum} duration_ms={run.duration_ms}"
            )
        )
