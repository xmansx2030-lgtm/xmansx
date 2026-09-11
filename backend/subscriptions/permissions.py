"""صلاحية المنصة — منفصلة تمامًا عن أدوار المدرسة (ADR-003).

مدير المنصة يدير المستأجرين والعقود فقط. لا يمنحه هذا الدور أي وصول لبيانات
الطلاب أو الحضور أو الإرشاد (بند 14) — تلك تمر عبر عضوية مدرسية لا تملكها المنصة.
"""

from rest_framework.permissions import BasePermission
from rest_framework.views import APIView

from common.errors import ApiError
from platform_team.access import has_platform_capability


class PlatformAdminRequired(BasePermission):
    def has_permission(self, request, view) -> bool:
        user = request.user
        if not (user and user.is_authenticated):
            return False  # → AUTHENTICATION_REQUIRED
        capability = getattr(view, "platform_capabilities_by_method", {}).get(
            request.method, getattr(view, "platform_capability", None)
        )
        if not has_platform_capability(user, capability):
            raise ApiError(
                "PERMISSION_DENIED",
                "لا تملك الصلاحية المطلوبة لتنفيذ هذا الإجراء في المنصة.",
                status_code=403,
            )
        if user.must_change_password:
            raise ApiError(
                "INITIAL_PASSWORD_CHANGE_REQUIRED",
                "يجب تغيير كلمة المرور المؤقتة أولاً.",
                status_code=403,
            )
        return True


class PlatformAPIView(APIView):
    """أساس كل واجهات `/platform/*` — لا سياق مدرسة ولا عضوية."""

    permission_classes = [PlatformAdminRequired]
