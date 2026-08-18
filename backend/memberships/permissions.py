"""Permission helpers مركزية — ممنوع تكرار `if role == ...` داخل Views.

الأدوار مقيدة بالعضوية/المدرسة: دور في مدرسة A لا يمنح شيئًا في مدرسة B،
لأن request.school_roles تُشتق حصرًا من عضوية المدرسة النشطة الحالية.
"""

from rest_framework.permissions import BasePermission

from common.errors import ApiError

_CONTEXT_ERROR_MESSAGES = {
    "ACTIVE_SCHOOL_REQUIRED": "يجب اختيار مدرسة أولاً.",
    "INVALID_SCHOOL_MEMBERSHIP": "لا تملك عضوية فعالة في هذه المدرسة.",
    "MEMBERSHIP_SUSPENDED": "عضويتك في هذه المدرسة موقوفة.",
    "SCHOOL_SUSPENDED": "هذه المدرسة موقوفة حالياً.",
}


def raise_school_context_error(request) -> None:
    """يرفع الخطأ الدقيق لسياق المدرسة (403) — أو ACTIVE_SCHOOL_REQUIRED إن لم يوجد سبب أدق."""
    code = getattr(request, "school_context_error", None) or "ACTIVE_SCHOOL_REQUIRED"
    raise ApiError(code, _CONTEXT_ERROR_MESSAGES[code], status_code=403)


def has_school_role(request, role: str) -> bool:
    """هل يحمل المستخدم الدور في المدرسة النشطة الحالية؟"""
    return request.school is not None and role in request.school_roles


def has_any_school_role(request, roles: list[str]) -> bool:
    return request.school is not None and any(r in request.school_roles for r in roles)


def require_school_role(request, role: str) -> None:
    """يرفع خطأ واضحًا إن لم يحمل المستخدم الدور في المدرسة النشطة."""
    if request.school is None:
        raise_school_context_error(request)
    if role not in request.school_roles:
        raise ApiError(
            "PERMISSION_DENIED",
            "ليست لديك صلاحية لتنفيذ هذا الإجراء.",
            status_code=403,
        )


class ActiveSchoolRequired(BasePermission):
    """Endpoint مدرسي: يتطلب مصادقة + سياق مدرسة نشطة صالحًا."""

    def has_permission(self, request, view) -> bool:
        if not (request.user and request.user.is_authenticated):
            return False  # → AUTHENTICATION_REQUIRED من DRF
        if request.user.must_change_password:
            raise ApiError(
                "INITIAL_PASSWORD_CHANGE_REQUIRED",
                "يجب تغيير كلمة المرور المؤقتة قبل متابعة استخدام المنصة.",
                status_code=403,
            )
        if request.school is None:
            raise_school_context_error(request)
        return True


def school_role_required(*roles: str):
    """مصنع Permission لدور أو أكثر: SchoolRolePermission = school_role_required("TEACHER")."""

    class _SchoolRolePermission(ActiveSchoolRequired):
        def has_permission(self, request, view) -> bool:
            if not super().has_permission(request, view):
                return False
            if not any(r in request.school_roles for r in roles):
                raise ApiError(
                    "PERMISSION_DENIED",
                    "ليست لديك صلاحية لتنفيذ هذا الإجراء.",
                    status_code=403,
                )
            return True

    return _SchoolRolePermission
