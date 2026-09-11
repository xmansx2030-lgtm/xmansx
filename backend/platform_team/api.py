from django.contrib.auth import update_session_auth_hash
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response

from accounts.api.views import _validate_new_password
from accounts.mobile import normalize_mobile
from accounts.models import User
from audit.models import AuditAction
from audit.services import record_event
from common.errors import ApiError
from platform_team import services
from platform_team.access import PlatformCapability, get_platform_access
from platform_team.models import PlatformStaffRole
from subscriptions.permissions import PlatformAPIView


def _account_payload(user) -> dict:
    access = get_platform_access(user)
    return {
        "id": user.id,
        "name": user.display_name,
        "mobile": user.mobile,
        "role": access["role"],
        "role_label": access["role_label"],
        "is_owner": access["is_owner"],
        "capabilities": access["capabilities"],
        "school_memberships_count": user.memberships.count(),
        "last_login": user.last_login.isoformat() if user.last_login else None,
    }


class PlatformAccountView(PlatformAPIView):
    def get(self, request: Request) -> Response:
        return Response(_account_payload(request.user))

    def patch(self, request: Request) -> Response:
        user = User.objects.get(id=request.user.id)
        name = str(request.data.get("name", user.display_name)).strip()
        if len(name) < 2:
            raise ApiError("VALIDATION_ERROR", "أدخل الاسم كاملًا.")
        try:
            mobile = normalize_mobile(str(request.data.get("mobile", user.mobile)))
        except Exception as exc:
            raise ApiError("VALIDATION_ERROR", "رقم الجوال غير صحيح.") from exc
        if mobile != user.mobile:
            if not user.check_password(str(request.data.get("current_password", ""))):
                raise ApiError(
                    "INVALID_CURRENT_PASSWORD",
                    "يلزم إدخال كلمة المرور الحالية لتغيير رقم الجوال.",
                )
            if User.objects.exclude(id=user.id).filter(mobile=mobile).exists():
                raise ApiError("MOBILE_ALREADY_EXISTS", "رقم الجوال مرتبط بحساب آخر.", 409)
        changed = []
        if user.display_name != name:
            user.first_name, user.last_name = name[:150], ""
            changed.append("name")
        if user.mobile != mobile:
            user.mobile = mobile
            changed.append("mobile")
        if changed:
            user.save(update_fields=["first_name", "last_name", "mobile", "updated_at"])
            record_event(
                AuditAction.PLATFORM_ACCOUNT_UPDATED,
                request=request,
                actor=user,
                target_type="User",
                target_id=user.id,
                metadata={"changed_fields": changed},
            )
        return Response(_account_payload(user))


class PlatformPasswordView(PlatformAPIView):
    def post(self, request: Request) -> Response:
        user = request.user
        current = str(request.data.get("current_password", ""))
        new_password = str(request.data.get("new_password", ""))
        confirmation = str(request.data.get("confirm_password", ""))
        if not user.check_password(current):
            raise ApiError("INVALID_CURRENT_PASSWORD", "كلمة المرور الحالية غير صحيحة.")
        if new_password != confirmation:
            raise ApiError("VALIDATION_ERROR", "تأكيد كلمة المرور غير مطابق.")
        if new_password == current:
            raise ApiError("VALIDATION_ERROR", "كلمة المرور الجديدة مطابقة للحالية.")
        _validate_new_password(user, new_password)
        user.set_password(new_password)
        user.must_change_password = False
        user.save(update_fields=["password", "must_change_password", "updated_at"])
        update_session_auth_hash(request, user)
        request.session.cycle_key()
        record_event(
            AuditAction.PLATFORM_ACCOUNT_PASSWORD_CHANGED,
            request=request,
            actor=user,
            target_type="User",
            target_id=user.id,
        )
        return Response({"detail": "تم تغيير كلمة المرور بنجاح."})


class PlatformTeamView(PlatformAPIView):
    platform_capabilities_by_method = {
        "GET": PlatformCapability.TEAM_VIEW,
        "POST": PlatformCapability.TEAM_MANAGE,
    }

    def get(self, request: Request) -> Response:
        return Response(
            {
                "members": services.list_team(),
                "roles": [
                    {"value": value, "label": label} for value, label in PlatformStaffRole.choices
                ],
            }
        )

    def post(self, request: Request) -> Response:
        result = services.create_member(
            name=str(request.data.get("name", "")),
            mobile=str(request.data.get("mobile", "")),
            role=str(request.data.get("role", "")),
            job_title=str(request.data.get("job_title", "")),
            actor=request.user,
            request=request,
        )
        return Response(result, status=status.HTTP_201_CREATED)


class PlatformTeamMemberView(PlatformAPIView):
    platform_capability = PlatformCapability.TEAM_MANAGE

    def patch(self, request: Request, user_id: int) -> Response:
        allowed = {
            key: request.data[key]
            for key in ("name", "mobile", "role", "job_title")
            if key in request.data
        }
        return Response(
            services.update_member(
                user_id=user_id, data=allowed, actor=request.user, request=request
            )
        )


class PlatformTeamMemberActionView(PlatformAPIView):
    platform_capability = PlatformCapability.TEAM_MANAGE

    def post(self, request: Request, user_id: int, action: str) -> Response:
        return Response(
            services.run_member_action(
                user_id=user_id, action=action, actor=request.user, request=request
            )
        )
