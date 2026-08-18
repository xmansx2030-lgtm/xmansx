"""Tenant Context Middleware — يثبت سياق المدرسة النشطة لكل طلب.

القاعدة الأمنية (SECURITY.md §2): قيمة الجلسة ليست مصدر ثقة — يعاد التحقق من
العضوية والمدرسة في كل طلب. السياق الفاسد (عضوية موقوفة/مدرسة موقوفة) يزال من
الجلسة فورًا ويحفظ سبب الرفض ليعيده permission بالرمز الدقيق.
"""

from django.http import HttpRequest, HttpResponse

from memberships.selectors import get_membership
from schools.models import SchoolStatus

ACTIVE_SCHOOL_SESSION_KEY = "active_school_id"


class TenantContextMiddleware:
    """بعد AuthenticationMiddleware: يحدد request.school/membership/school_roles."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        request.school = None
        request.membership = None
        request.school_roles: list[str] = []
        request.school_context_error: str | None = None

        user = getattr(request, "user", None)
        school_id = request.session.get(ACTIVE_SCHOOL_SESSION_KEY)

        if user is not None and user.is_authenticated and school_id is not None:
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

        return self.get_response(request)
