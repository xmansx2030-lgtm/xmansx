"""الأساس الموحد لـ endpoints المدرسية — يمنع نسيان العزل أو الصلاحيات.

كل View مدرسي يرث SchoolScopedAPIView ويحدد أدوار القراءة/الكتابة.
المدرسة تؤخذ حصرًا من request.school (سياق الجلسة الموثق) — أبدًا من العميل.
"""

from rest_framework.views import APIView

from common.errors import ApiError
from memberships.models import SchoolRole
from memberships.permissions import school_role_or_capability_required
from subscriptions.access import FULL, get_school_access_mode, subscription_state

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
    read_capabilities: tuple = ()
    write_capabilities: tuple = ()

    def get_permissions(self):
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            roles = self.read_roles
            capabilities = self.read_capabilities
        else:
            roles = self.write_roles
            capabilities = self.write_capabilities
        return [school_role_or_capability_required(*roles, capabilities=capabilities)()]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return
        mode = get_school_access_mode(request.school)
        if mode != FULL:
            state = subscription_state(request.school)
            codes = {
                "EXPIRED": "SUBSCRIPTION_EXPIRED",
                "SUSPENDED": "SCHOOL_SUSPENDED",
                "CANCELLED": "SUBSCRIPTION_CANCELLED",
            }
            raise ApiError(
                codes.get(state["status"], "SUBSCRIPTION_WRITE_BLOCKED"),
                "اشتراك المدرسة لا يسمح بتنفيذ عمليات جديدة حالياً.",
                status_code=403,
                details={"access_mode": mode, "subscription_status": state["status"]},
            )
