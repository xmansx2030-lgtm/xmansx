from pathlib import Path

from django.conf import settings
from django.core.files.storage import storages
from django.core.management.base import BaseCommand, CommandError

from operations.models import BackupRun, BackupStatus, BackupType
from operations.retention import retained_backup_ids


class Command(BaseCommand):
    help = "Apply the 7 daily / 4 weekly / 3 monthly backup retention policy."

    def add_arguments(self, parser):
        mode = parser.add_mutually_exclusive_group(required=True)
        mode.add_argument("--dry-run", action="store_true")
        mode.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        runs = list(
            BackupRun.objects.filter(
                backup_type=BackupType.DATABASE,
                status=BackupStatus.SUCCEEDED,
            ).exclude(storage_reference="")
        )
        keep = retained_backup_ids(runs)
        candidates = [run for run in runs if run.id not in keep]
        if options["dry_run"]:
            self.stdout.write(f"dry-run candidates={len(candidates)} kept={len(keep)}")
            return
        for run in candidates:
            self._delete_artifacts(run)
            run.storage_reference = ""
            run.metadata = {**run.metadata, "retained": False}
            run.save(update_fields=["storage_reference", "metadata", "updated_at"])
        self.stdout.write(self.style.SUCCESS(f"deleted={len(candidates)} kept={len(keep)}"))

    def _delete_artifacts(self, run):
        reference = run.storage_reference
        if reference.startswith("local:"):
            root = Path(settings.DATABASE_BACKUP_ROOT).resolve()
            dump_path = (root / reference.removeprefix("local:")).resolve()
            if dump_path.parent != root:
                raise CommandError("unsafe local backup path")
            dump_path.unlink(missing_ok=True)
            manifest = run.metadata.get("manifest")
            if manifest:
                manifest_path = (root / manifest).resolve()
                if manifest_path.parent != root:
                    raise CommandError("unsafe local manifest path")
                manifest_path.unlink(missing_ok=True)
            return
        storage = storages["backups"]
        storage.delete(reference)
        manifest_name = run.metadata.get("manifest")
        if manifest_name:
            prefix = reference.rsplit("/", 1)[0]
            storage.delete(f"{prefix}/{manifest_name}")
