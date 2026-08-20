from django.apps import AppConfig


class CounselingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "counseling"
    verbose_name = "الإرشاد وإدارة الحالات"

    def ready(self):
        from counseling.purge_integration import register_purge_steps

        register_purge_steps()
