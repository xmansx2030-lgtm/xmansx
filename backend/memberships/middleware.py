"""Tenant Context Middleware — يثبت سياق المدرسة النشطة لكل طلب.

القاعدة الأمنية (SECURITY.md §2): قيمة الجلسة ليست مصدر ثقة — يعاد التحقق من
العضوية والمدرسة في كل طلب. السياق الفاسد (عضوية موقوفة/مدرسة موقوفة) يزال من
الجلسة فورًا ويحفظ سبب الرفض ليعيده permission بالرمز الدقيق.
"""

from django.conf import settings
from django.db import connection
from django.http import HttpRequest, HttpResponse

from common.tenant_rls import clear_tenant_context, set_tenant_context
from memberships.selectors import get_membership
from schools.models import SchoolStatus

ACTIVE_SCHOOL_SESSION_KEY = "active_school_id"


class TenantContextMiddleware:
    """يثبت المدرسة والعضوية والأدوار والتكليفات التشغيلية للطلب الحالي."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        # Persistent DB connections must never inherit the previous request's tenant.
        rls_enforced = settings.DATABASE_RLS_ENFORCED
        if rls_enforced:
            clear_tenant_context()
        try:
            return self._dispatch_with_context(request, rls_enforced=rls_enforced)
        finally:
            # Do not hide the original database error by issuing SQL while an
            # outer transaction is broken. The next request always clears first.
            if rls_enforced and not connection.needs_rollback:
                clear_tenant_context()

    def _dispatch_with_context(
        self, request: HttpRequest, *, rls_enforced: bool
    ) -> HttpResponse:
        request.school = None
        request.membership = None
        request.school_roles: list[str] = []
        request.school_capabilities: list[str] = []
        request.school_context_error: str | None = None

        user = getattr(request, "user", None)
        school_id = request.session.get(ACTIVE_SCHOOL_SESSION_KEY)

        if user is not None and user.is_authenticated and school_id is not None:
            if rls_enforced:
                set_tenant_context(user_id=user.id)
            membership = get_membership(user, school_id)
            if membership is None:
                request.school_context_error = "INVALID_SCHOOL_MEMBERSHIP"
                request.session.pop(ACTIVE_SCHOOL_SESSION_KEY, None)
            elif not membership.is_active_membership:
                request.school_context_error = "MEMBERSHIP_SUSPENDED"
                request.session.pop(ACTIVE_SCHOOL_SESSION_KEY, None)
            elif membership.school.status == SchoolStatus.SUSPENDED:
                request.school_context_error = "SCHOOL_SUSPENDED"
                # لا نزيل المفتاح: عودة المدرسة للعمل تعيد السياق تلقائيًا
            elif membership.school.status != SchoolStatus.ACTIVE:
                request.school_context_error = "INVALID_SCHOOL_MEMBERSHIP"
                request.session.pop(ACTIVE_SCHOOL_SESSION_KEY, None)
            else:
                request.school = membership.school
                request.membership = membership
                request.school_roles = membership.role_codes()
                request.school_capabilities = membership.capability_codes()

        platform_request = request.path.startswith("/api/v1/platform/")
        if (
            rls_enforced
            and platform_request
            and user is not None
            and user.is_authenticated
            and user.is_platform_admin
        ):
            set_tenant_context(bypass=True)
        elif rls_enforced and request.school is not None:
            set_tenant_context(school_id=request.school.id, user_id=user.id)
        elif rls_enforced and user is not None and user.is_authenticated:
            set_tenant_context(user_id=user.id)

        return self.get_response(request)
