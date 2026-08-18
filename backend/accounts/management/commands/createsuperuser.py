"""createsuperuser يقبل الجوال بأي صيغة شائعة (05x / 9665x / +9665x) ويطبّعه.

يغلف أمر Django القياسي — التحقق والتخزين يبقيان على الصيغة الموحدة.
"""

from django.contrib.auth.management.commands import createsuperuser as django_createsuperuser
from django.core.exceptions import ValidationError
from django.core.management.base import CommandError

from accounts.mobile import normalize_mobile


class Command(django_createsuperuser.Command):
    def get_input_data(self, field, message, default=None):
        value = super().get_input_data(field, message, default)
        if field.name == "mobile" and value:
            try:
                value = normalize_mobile(value)
            except ValidationError:
                pass  # يترك للتحقق القياسي إظهار الرسالة وإعادة الطلب
        return value

    def handle(self, *args, **options):
        if options.get("mobile"):
            try:
                options["mobile"] = normalize_mobile(options["mobile"])
            except ValidationError as exc:
                raise CommandError(exc.messages[0]) from exc
        return super().handle(*args, **options)
