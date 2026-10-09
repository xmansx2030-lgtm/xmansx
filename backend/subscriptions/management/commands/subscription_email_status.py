"""Inspect delivery counts, or explicitly requeue a known rejected delivery."""

from uuid import UUID

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count
from django.utils import timezone

from common.tenant_rls import tenant_context
from subscriptions.models import SubscriptionEmailDelivery


class Command(BaseCommand):
    help = "Show mail counts; --retry-failed UUID requeues known failures only."

    def add_arguments(self, parser):
        parser.add_argument("--retry-failed", type=UUID)

    def handle(self, *args, **options):
        with tenant_context(bypass=True):
            if options["retry_failed"]:
                changed = SubscriptionEmailDelivery.objects.filter(
                    pk=options["retry_failed"], status="FAILED",
                ).update(status="PENDING", error_code="", updated_at=timezone.now())
                if not changed:
                    raise CommandError("Only an existing FAILED delivery may be requeued.")
            for row in SubscriptionEmailDelivery.objects.values("status").annotate(
                count=Count("pk"),
            ).order_by("status"):
                self.stdout.write(f"{row['status']}: {row['count']}")
