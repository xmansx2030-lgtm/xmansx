"""الأساس الموحد لـ endpoints المدرسية — يمنع نسيان العزل أو الصلاحيات.

كل View مدرسي يرث SchoolScopedAPIView ويحدد أدوار القراءة/الكتابة.
المدرسة تؤخذ حصرًا من request.school (سياق الجلسة الموثق) — أبدًا من العميل.
"""

from rest_framework.views import APIView

from memberships.models import SchoolRole
from memberships.permissions import school_role_required

SETTINGS_READ_ROLES = (
    SchoolRole.SCHOOL_MANAGER,
    SchoolRole.VICE_PRINCIPAL,
    SchoolRole.COUNSELOR,
)
SETTINGS_WRITE_ROLES = (SchoolRole.SCHOOL_MANAGER,)


class SchoolScopedAPIView(APIView):
    """قراءة حسب read_roles، كتابة حسب write_roles — TEACHER محجوب افتراضيًا عن الإعدادات."""

    read_roles: tuple = SETTINGS_READ_ROLES
    write_roles: tuple = SETTINGS_WRITE_ROLES

    def get_permissions(self):
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            roles = self.read_roles
        else:
            roles = self.write_roles
        return [school_role_required(*roles)()]
