from django.core.management.base import BaseCommand, CommandError

from operations.backups import BackupError, retry_backup_upload


class Command(BaseCommand):
    help = "Retry only the remote upload stage of a checksum-valid failed backup."

    def add_arguments(self, parser):
        parser.add_argument("--run-id", type=int, required=True)

    def handle(self, *args, **options):
        try:
            run = retry_backup_upload(options["run_id"])
        except (BackupError, OSError) as exc:
            raise CommandError(f"backup upload retry failed: {type(exc).__name__}") from exc
        self.stdout.write(self.style.SUCCESS(f"backup upload succeeded id={run.id}"))
