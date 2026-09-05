"""Create the first platform administrator from deployment-only environment values."""

import os

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from accounts.mobile import normalize_mobile


class Command(BaseCommand):
    help = "Create the initial platform administrator without changing an existing account."

    def handle(self, *args, **options):
        raw_mobile = os.environ.get("INITIAL_ADMIN_MOBILE", "")
        password = os.environ.get("INITIAL_ADMIN_PASSWORD", "")
        if not raw_mobile or not password:
            raise CommandError("INITIAL_ADMIN_MOBILE and INITIAL_ADMIN_PASSWORD are required")

        try:
            mobile = normalize_mobile(raw_mobile)
            validate_password(password)
        except ValidationError as exc:
            raise CommandError("Initial administrator credentials are invalid") from exc

        User = get_user_model()
        existing = User.objects.filter(mobile=mobile).first()
        if existing:
            if not existing.is_superuser:
                raise CommandError("The initial administrator mobile belongs to a non-admin user")
            self.stdout.write(
                "Platform administrator already exists; credentials were not changed."
            )
            return

        user = User.objects.create_superuser(mobile=mobile, password=password)
        display_name = os.environ.get("INITIAL_ADMIN_NAME", "").strip()
        if display_name:
            user.first_name = display_name
            user.save(update_fields=["first_name", "updated_at"])
        self.stdout.write(self.style.SUCCESS("Initial platform administrator created."))
