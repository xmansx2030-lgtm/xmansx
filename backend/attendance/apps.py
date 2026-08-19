from django.apps import AppConfig


class AttendanceConfig(AppConfig):
    name = "attendance"
    verbose_name = "الحضور"

    def ready(self) -> None:
        # إلزام المرحلة 4.1: تسجيل بيانات الحضور في دورة الحذف النهائي —
        # النسيان يفشل صاخبًا (student FK بـ PROTECT)
        from attendance.purge_integration import register_purge_steps

        register_purge_steps()
