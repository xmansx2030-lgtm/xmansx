from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from accounts.mobile import normalize_mobile
from memberships.models import SchoolMembership


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


def serialize_school(school) -> dict:
    return {"id": school.id, "name": school.name, "slug": school.slug}


def serialize_membership(membership: SchoolMembership) -> dict:
    return {
        "id": membership.id,
        "school": serialize_school(membership.school),
        "roles": membership.role_codes(),
        "status": membership.status,
    }


def build_me_payload(user, memberships, active_membership: SchoolMembership | None) -> dict:
    """الاستجابة الموحدة لـ /me وlogin وswitch — لا حقول حساسة (hash/permissions داخلية)."""
    return {
        "id": user.id,
        "mobile": user.mobile,
        "name": user.display_name,
        "is_platform_admin": user.is_platform_admin,
        "active_school": (
            serialize_school(active_membership.school) if active_membership else None
        ),
        "roles": active_membership.role_codes() if active_membership else [],
        "memberships": [serialize_membership(m) for m in memberships],
    }
