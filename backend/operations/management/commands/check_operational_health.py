from django.core.management.base import BaseCommand, CommandError

from operations.health import check_beat, check_worker


class Command(BaseCommand):
    help = "Exit non-zero when the selected operational component is unhealthy."

    def add_arguments(self, parser):
        parser.add_argument("--component", choices=["worker", "beat"], required=True)

    def handle(self, *args, **options):
        component = options["component"]
        status = check_worker() if component == "worker" else check_beat()[0]
        if status != "ok":
            raise CommandError(f"{component} health is {status}")
        self.stdout.write(self.style.SUCCESS(f"{component}: ok"))
