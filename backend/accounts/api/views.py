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
    serialize_invitation,
    serialize_membership,
)
from accounts.mobile import mask_mobile
from audit.models import AuditAction
from audit.services import client_ip, record_event
from common.errors import ApiError
from memberships.middleware import ACTIVE_SCHOOL_SESSION_KEY
from memberships.models import MembershipStatus, SchoolMembership
from memberships.selectors import (
    active_memberships_for_user,
    get_membership,
    invited_memberships_for_user,
)
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
        invitations = invited_memberships_for_user(user)
        return Response(build_me_payload(user, memberships, active, invitations))


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
        invitations = invited_memberships_for_user(request.user)
        return Response(build_me_payload(request.user, memberships, active, invitations))


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
        require_password_changed(request.user)
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
        invitations = invited_memberships_for_user(request.user)
        return Response(
            build_me_payload(request.user, memberships, membership, invitations),
            status=status.HTTP_200_OK,
        )


# ---------- كلمة المرور الأولية والدعوات (المرحلة 5) ----------


def require_password_changed(user) -> None:
    """بوابة: لا استخدام تشغيلي للمنصة قبل تغيير كلمة المرور المؤقتة."""
    if user.is_authenticated and user.must_change_password:
        raise ApiError(
            "INITIAL_PASSWORD_CHANGE_REQUIRED",
            "يجب تغيير كلمة المرور المؤقتة قبل متابعة استخدام المنصة.",
            status_code=403,
        )


def _validate_new_password(user, new_password: str) -> None:
    """سياسة كلمة المرور — رسائل عربية واضحة بلا تعقيد مبالغ."""
    if len(new_password) < 8:
        raise ApiError("VALIDATION_ERROR", "كلمة المرور يجب ألا تقل عن 8 أحرف.")
    if new_password.isdigit():
        raise ApiError("VALIDATION_ERROR", "كلمة المرور لا يمكن أن تكون أرقامًا فقط.")
    if new_password in (user.mobile, user.mobile.removeprefix("+966"), "0" + user.mobile[4:]):
        raise ApiError("VALIDATION_ERROR", "كلمة المرور لا يمكن أن تكون رقم جوالك.")


class ChangeInitialPasswordView(APIView):
    """تغيير كلمة المرور المؤقتة — عالمي (يخص User، ليس مدرسة).

    ملاحظة أمنية: مدير المدرسة لا يستطيع إعادة تعيين كلمة مرور مستخدم موجود —
    لأنها تؤثر على دخوله لكل مدارسه. لا يوجد Password Reset عام في هذه المرحلة.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        user = request.user
        if not user.must_change_password:
            raise ApiError(
                "VALIDATION_ERROR", "لا توجد كلمة مرور مؤقتة بحاجة إلى تغيير.", status_code=409
            )
        current = str(request.data.get("current_password", ""))
        new_password = str(request.data.get("new_password", ""))
        confirm = str(request.data.get("confirm_password", ""))

        if not user.check_password(current):
            raise ApiError(
                "INVALID_CURRENT_PASSWORD", "كلمة المرور الحالية غير صحيحة.", status_code=400
            )
        if new_password != confirm:
            raise ApiError("VALIDATION_ERROR", "تأكيد كلمة المرور غير مطابق.")
        if new_password == current:
            raise ApiError("VALIDATION_ERROR", "كلمة المرور الجديدة مطابقة للحالية.")
        _validate_new_password(user, new_password)

        user.set_password(new_password)
        user.must_change_password = False
        user.save(update_fields=["password", "must_change_password"])

        # يحافظ على الجلسة الحالية مع تدوير آمن بعد تغيير الـ hash
        from django.contrib.auth import update_session_auth_hash

        update_session_auth_hash(request, user)
        request.session.cycle_key()

        record_event(AuditAction.INITIAL_PASSWORD_CHANGED, request=request, actor=user)
        memberships = list(active_memberships_for_user(user))
        active = _resolve_active_membership(request, memberships)
        invitations = invited_memberships_for_user(user)
        return Response(build_me_payload(user, memberships, active, invitations))


def _get_own_invitation(user, invitation_id: int) -> SchoolMembership:
    """دعوة المستخدم نفسه فقط — دعوات الآخرين غير موجودة من منظوره (404)."""
    membership = (
        SchoolMembership.objects.filter(id=invitation_id, user=user)
        .select_related("school")
        .prefetch_related("roles")
        .first()
    )
    if membership is None:
        raise ApiError("INVITATION_NOT_FOUND", "هذه الدعوة غير موجودة.", status_code=404)
    if membership.status == MembershipStatus.ACTIVE:
        raise ApiError(
            "INVITATION_ALREADY_ACCEPTED", "هذه الدعوة مقبولة بالفعل.", status_code=409
        )
    if membership.status == MembershipStatus.DECLINED:
        raise ApiError(
            "INVITATION_ALREADY_DECLINED", "هذه الدعوة لم تعد متاحة.", status_code=409
        )
    if membership.status != MembershipStatus.INVITED:
        raise ApiError("INVITATION_NOT_FOUND", "هذه الدعوة غير موجودة.", status_code=404)
    return membership


class InvitationsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        invitations = invited_memberships_for_user(request.user)
        return Response({"invitations": [serialize_invitation(m) for m in invitations]})


class InvitationAcceptView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, invitation_id: int) -> Response:
        membership = _get_own_invitation(request.user, invitation_id)
        membership.status = MembershipStatus.ACTIVE
        membership.save(update_fields=["status", "updated_at"])
        record_event(
            AuditAction.SCHOOL_MEMBERSHIP_ACCEPTED,
            request=request, actor=request.user, school=membership.school,
            target_type="SchoolMembership", target_id=membership.id,
        )
        memberships = list(active_memberships_for_user(request.user))
        active = _resolve_active_membership(request, memberships)
        invitations = invited_memberships_for_user(request.user)
        return Response(build_me_payload(request.user, memberships, active, invitations))


class InvitationDeclineView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, invitation_id: int) -> Response:
        membership = _get_own_invitation(request.user, invitation_id)
        membership.status = MembershipStatus.DECLINED  # لا حذف — سجل يبقى (Reinvite صريح)
        membership.save(update_fields=["status", "updated_at"])
        record_event(
            AuditAction.SCHOOL_MEMBERSHIP_DECLINED,
            request=request, actor=request.user, school=membership.school,
            target_type="SchoolMembership", target_id=membership.id,
        )
        memberships = list(active_memberships_for_user(request.user))
        active = _resolve_active_membership(request, memberships)
        invitations = invited_memberships_for_user(request.user)
        return Response(build_me_payload(request.user, memberships, active, invitations))
