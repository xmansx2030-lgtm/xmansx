from django.apps import AppConfig


class StudentLeavesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "student_leaves"
    verbose_name = "استئذانات الطلاب"

    def ready(self):
        from student_leaves.purge_integration import register_purge_steps

        register_purge_steps()
