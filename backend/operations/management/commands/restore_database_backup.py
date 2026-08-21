from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from operations.backups import BackupError, restore_database_backup


class Command(BaseCommand):
    help = "Restore a verified backup into an explicitly named, empty, non-current database."

    def add_arguments(self, parser):
        parser.add_argument("--backup", type=Path, required=True)
        parser.add_argument("--manifest", type=Path, required=True)
        parser.add_argument("--target-db", required=True)
        parser.add_argument("--confirm-target-empty", action="store_true")
        parser.add_argument("--allow-production-host", action="store_true")

    def handle(self, *args, **options):
        if not options["confirm_target_empty"]:
            raise CommandError("--confirm-target-empty is required")
        if settings.BACKUP_ENVIRONMENT == "production" and not options["allow_production_host"]:
            raise CommandError("production-host restore requires --allow-production-host")
        try:
            duration = restore_database_backup(
                dump_path=options["backup"].resolve(),
                manifest_path=options["manifest"].resolve(),
                target_database=options["target_db"],
            )
        except (BackupError, OSError, ValueError) as exc:
            raise CommandError(f"restore failed safely: {type(exc).__name__}") from exc
        self.stdout.write(self.style.SUCCESS(f"restore succeeded duration_ms={duration}"))
