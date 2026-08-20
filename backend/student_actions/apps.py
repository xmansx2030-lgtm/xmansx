from django.apps import AppConfig


class StudentActionsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "student_actions"
    verbose_name = "الإجراءات الطلابية"

    def ready(self):
        from student_actions.purge_integration import register_purge_steps

        register_purge_steps()
