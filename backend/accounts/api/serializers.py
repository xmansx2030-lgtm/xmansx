from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from accounts.mobile import normalize_mobile
from accounts.models import User
from memberships.models import SchoolMembership
from schools.models import SchoolType


class LoginSerializer(serializers.Serializer):
    """إدخال تسجيل الدخول — كلمة المرور write-only ولا تظهر في أي إخراج/سجل."""

    mobile = serializers.CharField(max_length=20)
    password = serializers.CharField(max_length=128, write_only=True, trim_whitespace=False)

    def validate_mobile(self, value: str) -> str:
        try:
            return normalize_mobile(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages[0]) from exc


class ActiveSchoolSerializer(serializers.Serializer):
    school_id = serializers.IntegerField(min_value=1)


class SchoolRegistrationSerializer(serializers.Serializer):
    """مدخلات التسجيل العام؛ لا يقبل حالة اشتراك أو مدة تجربة من العميل."""

    school_name = serializers.CharField(max_length=200, trim_whitespace=True)
    school_type = serializers.ChoiceField(choices=SchoolType.choices)
    manager_name = serializers.CharField(max_length=150, trim_whitespace=True)
    manager_mobile = serializers.CharField(max_length=20)
    password = serializers.CharField(max_length=128, write_only=True, trim_whitespace=False)
    confirm_password = serializers.CharField(max_length=128, write_only=True, trim_whitespace=False)
    plan_id = serializers.IntegerField(min_value=1)
    terms_accepted = serializers.BooleanField()

    def validate_school_name(self, value: str) -> str:
        if len(value) < 3:
            raise serializers.ValidationError("اسم المدرسة يجب ألا يقل عن 3 أحرف.")
        return value

    def validate_manager_name(self, value: str) -> str:
        if len(value) < 3:
            raise serializers.ValidationError("اسم مدير المدرسة يجب ألا يقل عن 3 أحرف.")
        return value

    def validate_manager_mobile(self, value: str) -> str:
        try:
            return normalize_mobile(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages[0]) from exc

    def validate(self, attrs: dict) -> dict:
        if not attrs.get("terms_accepted"):
            raise serializers.ValidationError(
                {"terms_accepted": "يجب الموافقة على الشروط وسياسة الخصوصية."}
            )
        if attrs["password"] != attrs["confirm_password"]:
            raise serializers.ValidationError({"confirm_password": "تأكيد كلمة المرور غير مطابق."})
        candidate = User(mobile=attrs["manager_mobile"], first_name=attrs["manager_name"])
        try:
            validate_password(attrs["password"], user=candidate)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": list(exc.messages)}) from exc
        return attrs


def serialize_school(school) -> dict:
    return {
        "id": school.id,
        "name": school.name,
        "slug": school.slug,
        "school_type": school.school_type,
    }


def serialize_membership(membership: SchoolMembership) -> dict:
    return {
        "id": membership.id,
        "school": serialize_school(membership.school),
        "roles": membership.role_codes(),
        "capabilities": membership.capability_codes(),
        "status": membership.status,
    }


def serialize_invitation(membership: SchoolMembership) -> dict:
    return {
        "id": membership.id,
        "school": serialize_school(membership.school),
        "roles": membership.role_codes(),
        "capabilities": membership.capability_codes(),
    }


def build_me_payload(
    user,
    memberships,
    active_membership: SchoolMembership | None,
    invitations=(),
) -> dict:
    """الاستجابة الموحدة لـ /me وlogin وswitch — لا حقول حساسة (hash/permissions داخلية)."""
    from platform_team.access import get_platform_access

    platform_access = get_platform_access(user)
    return {
        "id": user.id,
        "mobile": user.mobile,
        "name": user.display_name,
        "is_platform_admin": platform_access["is_platform_user"],
        "is_platform_owner": platform_access["is_owner"],
        "platform_role": platform_access["role"],
        "platform_role_label": platform_access["role_label"],
        "platform_capabilities": platform_access["capabilities"],
        "must_change_password": user.must_change_password,
        "active_school": (
            serialize_school(active_membership.school) if active_membership else None
        ),
        "roles": active_membership.role_codes() if active_membership else [],
        "capabilities": active_membership.capability_codes() if active_membership else [],
        "memberships": [serialize_membership(m) for m in memberships],
        "invitations": [serialize_invitation(m) for m in invitations],
    }
