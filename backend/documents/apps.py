from django.apps import AppConfig


class DocumentsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "documents"
    verbose_name = "المستندات المولدة"

    def ready(self):
        from documents.purge_integration import register_purge_steps

        register_purge_steps()
