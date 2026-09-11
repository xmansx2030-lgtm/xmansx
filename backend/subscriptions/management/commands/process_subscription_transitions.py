from django.core.management.base import BaseCommand

from common.tenant_rls import tenant_context
from subscriptions.services.subscriptions import sync_expirations


class Command(BaseCommand):
    help = "Process idempotent SaaS subscription trial/active/grace expiration transitions."

    def handle(self, *args, **options):
        with tenant_context(bypass=True):
            counts = sync_expirations()
        message = (
            "Subscription transitions processed: "
            f"expired={counts['expired']} grace={counts['grace']}"
        )
        self.stdout.write(
            self.style.SUCCESS(message)
        )
