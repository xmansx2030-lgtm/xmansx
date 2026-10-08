from django.apps import AppConfig


class ParentsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "parents"
    verbose_name = "بوابة ولي الأمر"

    def ready(self):
        from parents.purge_integration import register_purge_steps

        register_purge_steps()
