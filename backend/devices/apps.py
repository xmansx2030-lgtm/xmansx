from django.apps import AppConfig


class DevicesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "devices"
    verbose_name = "أجهزة الحضور"

    def ready(self) -> None:
        from devices.purge_integration import register_purge_steps

        register_purge_steps()
