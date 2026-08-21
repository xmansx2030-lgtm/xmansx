from django.apps import AppConfig


class OperationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "operations"

    def ready(self) -> None:
        from operations import signals  # noqa: F401
        from operations.error_tracking import initialize_error_tracking

        initialize_error_tracking()
