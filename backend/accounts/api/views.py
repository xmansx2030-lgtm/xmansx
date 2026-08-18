"""واجهات المصادقة والجلسة.

قواعد أمنية مطبقة هنا:
- CSRF مفروض حتى على login (SPA تجلب الـ cookie من /auth/csrf/ أولاً).
- رسالة INVALID_CREDENTIALS واحدة عامة — لا تمييز بين رقم غير موجود/كلمة مرور
  خاطئة/حساب معطل (منع user enumeration).
- login() في Django يدوّر مفتاح الجلسة (حماية Session Fixation)، وswitch يدوّرها أيضًا.
- school_id يقبل فقط في switch، ويتحقق من العضوية — لا يوثق به كسلطة في أي endpoint آخر.
"""

from django.contrib.auth import authenticate, login, logout
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts import rate_limit
from accounts.api.serializers import (
    ActiveSchoolSerializer,
    LoginSerializer,
    build_me_payload,
    serialize_membership,
)
from accounts.mobile import mask_mobile
from audit.models import AuditAction
from audit.services import client_ip, record_event
from common.errors import ApiError
from memberships.middleware import ACTIVE_SCHOOL_SESSION_KEY
from memberships.models import MembershipStatus
from memberships.selectors import active_memberships_for_user, get_membership
from schools.models import SchoolStatus

INVALID_CREDENTIALS_MESSAGE = "رقم الجوال أو كلمة المرور غير صحيحة."


def _resolve_active_membership(request: Request, memberships):
    """العضوية المطابقة للمدرسة النشطة في الجلسة — من القائمة المحملة (بلا استعلام إضافي)."""
    school_id = request.session.get(ACTIVE_SCHOOL_SESSION_KEY)
    if school_id is None:
        return None
    for membership in memberships:
        if membership.school_id == school_id and membership.school.status == SchoolStatus.ACTIVE:
            return membership
    return None


@method_decorator(ensure_csrf_cookie, name="dispatch")
class CsrfView(APIView):
    """CSRF Bootstrap للـ SPA — يضبط الـ cookie فقط، لا يعرض أي سر."""

    permission_classes = [AllowAny]

    def get(self, request: Request) -> Response:
        return Response({"detail": "ok"})


@method_decorator(csrf_protect, name="dispatch")
class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request: Request) -> Response:
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        mobile: str = serializer.validated_data["mobile"]
        password: str = serializer.validated_data["password"]
        ip = client_ip(request) or "unknown"

        rate_limit.precheck(ip, mobile)
        rate_limit.register_attempt(ip)

        user = authenticate(request, username=mobile, password=password)
        if user is None:
            rate_limit.register_failure(mobile)
            record_event(
                AuditAction.LOGIN_FAILED,
                request=request,
                metadata={"mobile_masked": mask_mobile(mobile)},
            )
            raise ApiError(
                "INVALID_CREDENTIALS", INVALID_CREDENTIALS_MESSAGE, status_code=401
            )

        login(request, user)  # يدوّر مفتاح الجلسة (session fixation protection)
        rate_limit.register_success(mobile)

        memberships = list(active_memberships_for_user(user))
        operational = [m for m in memberships if m.school.status == SchoolStatus.ACTIVE]
        if len(operational) == 1:
            # مدرسة واحدة فعالة → اختيار تلقائي
            request.session[ACTIVE_SCHOOL_SESSION_KEY] = operational[0].school_id

        record_event(AuditAction.LOGIN_SUCCESS, request=request, actor=user)

        active = _resolve_active_membership(request, memberships)
        return Response(build_me_payload(user, memberships, active))


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        record_event(AuditAction.LOGOUT, request=request, actor=request.user)
        logout(request)  # flush كامل للجلسة
        return Response({"detail": "ok"})


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        memberships = list(active_memberships_for_user(request.user))
        active = _resolve_active_membership(request, memberships)
        return Response(build_me_payload(request.user, memberships, active))


class MySchoolsView(APIView):
    """مدارس المستخدم الحالي حصرًا — لا يقبل أي معرف مستخدم من العميل."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        memberships = active_memberships_for_user(request.user)
        return Response({"memberships": [serialize_membership(m) for m in memberships]})


class ActiveSchoolView(APIView):
    """تبديل المدرسة النشطة — الاستثناء الوحيد الذي يقبل school_id من العميل،
    ويتحقق من العضوية الفعالة وحالة المدرسة قبل تحديث الجلسة."""

    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        serializer = ActiveSchoolSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        school_id = serializer.validated_data["school_id"]

        membership = get_membership(request.user, school_id)
        # رسالة واحدة لغير الموجود وغير العضو — لا نكشف وجود مدارس ليست له
        if membership is None or membership.status == MembershipStatus.LEFT:
            raise ApiError(
                "INVALID_SCHOOL_MEMBERSHIP",
                "لا تملك عضوية فعالة في هذه المدرسة.",
                status_code=403,
            )
        if membership.status != MembershipStatus.ACTIVE:
            raise ApiError(
                "MEMBERSHIP_SUSPENDED", "عضويتك في هذه المدرسة موقوفة.", status_code=403
            )
        if membership.school.status == SchoolStatus.SUSPENDED:
            raise ApiError("SCHOOL_SUSPENDED", "هذه المدرسة موقوفة حالياً.", status_code=403)
        if membership.school.status != SchoolStatus.ACTIVE:
            raise ApiError(
                "INVALID_SCHOOL_MEMBERSHIP",
                "لا تملك عضوية فعالة في هذه المدرسة.",
                status_code=403,
            )

        previous_school_id = request.session.get(ACTIVE_SCHOOL_SESSION_KEY)
        request.session[ACTIVE_SCHOOL_SESSION_KEY] = membership.school_id
        request.session.cycle_key()

        record_event(
            AuditAction.SWITCH_SCHOOL,
            request=request,
            actor=request.user,
            school=membership.school,
            metadata={"from_school_id": previous_school_id, "to_school_id": membership.school_id},
        )

        memberships = list(active_memberships_for_user(request.user))
        return Response(
            build_me_payload(request.user, memberships, membership),
            status=status.HTTP_200_OK,
        )
