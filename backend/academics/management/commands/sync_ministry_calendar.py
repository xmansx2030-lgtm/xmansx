import json

from django.core.management.base import BaseCommand

from academics.services.ministry_calendar import sync_ministry_calendar


class Command(BaseCommand):
    help = "Fetch and validate the live official Ministry calendar; never invent missing dates."

    def handle(self, *args, **options):
        self.stdout.write(json.dumps(sync_ministry_calendar(), ensure_ascii=False))
