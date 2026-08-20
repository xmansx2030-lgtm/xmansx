from django.apps import AppConfig


class ReferralsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "referrals"
    verbose_name = "إحالات الطلاب"

    def ready(self):
        from referrals.purge_integration import register_purge_steps

        register_purge_steps()
