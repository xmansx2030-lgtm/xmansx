"""واجهات إعدادات المدرسة — /api/v1/school/settings/"""

import mimetypes
from zoneinfo import ZoneInfo

from django.http import FileResponse
from django.urls import reverse
from rest_framework import serializers
from rest_framework.exceptions import NotFound
from rest_framework.request import Request
from rest_framework.response import Response

from memberships.api_base import SchoolScopedAPIView
from memberships.models import MembershipStatus, SchoolMembership, SchoolRole
from schools.models import EducationStage, SchoolType
from schools.services import settings as settings_service


class SchoolInfoPatchSerializer(serializers.Serializer):
    """حقول التعديل المسموحة فقط — school/logo/status ليست هنا (منع mass assignment)."""

    name = serializers.CharField(max_length=200, required=False)
    school_type = serializers.ChoiceField(choices=SchoolType.choices, required=False)
    ministry_school_number = serializers.CharField(
        max_length=30, required=False, allow_blank=True
    )
    education_stage = serializers.ChoiceField(choices=EducationStage.choices, required=False)
    city = serializers.CharField(max_length=100, required=False, allow_blank=True)
    official_principal_name = serializers.CharField(
        max_length=150, required=False, allow_blank=True
    )
    timezone = serializers.CharField(max_length=50, required=False)
    attendance_edit_window_minutes = serializers.IntegerField(
        required=False, min_value=0, max_value=120
    )
    unprepared_period_alert_minutes = serializers.IntegerField(
        required=False, min_value=1, max_value=120
    )
    school_day_start_time = serializers.TimeField(required=False)
    morning_late_grace_minutes = serializers.IntegerField(
        required=False, min_value=0, max_value=120
    )

    def validate_timezone(self, value: str) -> str:
        try:
            ZoneInfo(value)
        except Exception as exc:
            raise serializers.ValidationError("المنطقة الزمنية غير صحيحة.") from exc
        return value


def _staff_by_role(school) -> dict:
    """المدير/الوكلاء/المرشدون من العضويات الفعالة — للعرض فقط، ليسوا مصدر صلاحية نصي."""
    memberships = (
        SchoolMembership.objects.filter(school=school, status=MembershipStatus.ACTIVE)
        .select_related("user")
        .prefetch_related("roles")
    )
    staff: dict[str, list[str]] = {"managers": [], "vice_principals": [], "counselors": []}
    role_map = {
        SchoolRole.SCHOOL_MANAGER: "managers",
        SchoolRole.VICE_PRINCIPAL: "vice_principals",
        SchoolRole.COUNSELOR: "counselors",
    }
    for membership in memberships:
        for role in membership.role_codes():
            key = role_map.get(role)
            if key:
                staff[key].append(membership.user.display_name)
    return staff


def serialize_settings(school, settings_obj, request) -> dict:
    logo_url = None
    if settings_obj.logo:
        # Same-origin, authorised delivery works behind the frontend reverse proxy
        # and does not expose the rest of MEDIA_ROOT.
        logo_url = f'{reverse("school-logo")}?v={int(settings_obj.updated_at.timestamp())}'
    return {
        "school": {
            "id": school.id,
            "name": school.name,
            "slug": school.slug,
            "school_type": school.school_type,
        },
        "ministry_school_number": settings_obj.ministry_school_number,
        "education_stage": settings_obj.education_stage,
        "city": settings_obj.city,
        "official_principal_name": settings_obj.official_principal_name,
        "timezone": settings_obj.timezone,
        "logo_url": logo_url,
        "attendance_edit_window_minutes": settings_obj.attendance_edit_window_minutes,
        "unprepared_period_alert_minutes": settings_obj.unprepared_period_alert_minutes,
        "school_day_start_time": settings_obj.school_day_start_time.strftime("%H:%M")
        if settings_obj.school_day_start_time
        else None,
        "morning_late_grace_minutes": settings_obj.morning_late_grace_minutes,
        "staff": _staff_by_role(school),
    }


class SchoolSettingsView(SchoolScopedAPIView):
    def get(self, request: Request) -> Response:
        settings_obj = settings_service.get_or_create_settings(school=request.school)
        return Response(serialize_settings(request.school, settings_obj, request))

    def patch(self, request: Request) -> Response:
        serializer = SchoolInfoPatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        settings_obj = settings_service.update_school_info(
            school=request.school,
            actor=request.user,
            data=serializer.validated_data,
            request=request,
        )
        request.school.refresh_from_db(fields=["name"])
        return Response(serialize_settings(request.school, settings_obj, request))


class SchoolLogoView(SchoolScopedAPIView):
    def get(self, request: Request) -> FileResponse:
        settings_obj = settings_service.get_or_create_settings(school=request.school)
        if not settings_obj.logo:
            raise NotFound("لا يوجد شعار مرفوع لهذه المدرسة.")

        content_type = mimetypes.guess_type(settings_obj.logo.name)[0] or "application/octet-stream"
        return FileResponse(settings_obj.logo.open("rb"), content_type=content_type)

    def post(self, request: Request) -> Response:
        uploaded = request.FILES.get("logo")
        if uploaded is None:
            from common.errors import ApiError

            raise ApiError("VALIDATION_ERROR", "أرفق ملف الشعار في الحقل logo.")
        settings_obj = settings_service.set_logo(
            school=request.school, actor=request.user, uploaded_file=uploaded, request=request
        )
        return Response(serialize_settings(request.school, settings_obj, request))

    def delete(self, request: Request) -> Response:
        settings_obj = settings_service.remove_logo(
            school=request.school, actor=request.user, request=request
        )
        return Response(serialize_settings(request.school, settings_obj, request))
