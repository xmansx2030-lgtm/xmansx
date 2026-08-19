from django.apps import AppConfig


class StudentWarningsConfig(AppConfig):
    """الوحدة تسمى student_warnings لا warnings: حزمة عليا بهذا الاسم تُظلّل وحدة
    بايثون القياسية `warnings` التي يستوردها Django نفسه (backend/ جذر sys.path)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "student_warnings"
    verbose_name = "الإنذارات الطلابية"

    def ready(self):
        from student_warnings.purge_integration import register_purge_steps

        register_purge_steps()
