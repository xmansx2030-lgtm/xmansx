from django.apps import AppConfig


class ExcusesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "excuses"
    verbose_name = "أعذار الغياب"

    def ready(self):
        from excuses.purge_integration import register_purge_steps

        register_purge_steps()
