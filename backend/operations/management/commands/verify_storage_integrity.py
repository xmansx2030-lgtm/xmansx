import json

from django.core.management.base import BaseCommand, CommandError

from common.tenant_rls import tenant_context
from operations.storage_integrity import verify_storage_integrity


class Command(BaseCommand):
    help = "Verify that private DB-backed objects exist and match stored checksums."

    def add_arguments(self, parser):
        parser.add_argument("--existence-only", action="store_true")

    def handle(self, *args, **options):
        with tenant_context(bypass=True):
            result = verify_storage_integrity(
                verify_checksums=not options["existence_only"]
            )
        self.stdout.write(json.dumps(result, sort_keys=True))
        if result["missing"] or result["checksum_mismatch"] or result["errors"]:
            raise CommandError("storage integrity verification failed")
