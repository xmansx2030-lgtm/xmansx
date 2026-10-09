from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.response import Response

from audit.models import AuditAction
from audit.services import record_event
from memberships.api_base import SchoolScopedAPIView
from memberships.models import SchoolRole
from platform_team.access import PlatformCapability
from schools.models import School
from subscriptions.entitlements import MANAGED_FEATURES, school_feature_access
from subscriptions.permissions import PlatformAPIView


class SchoolFeatureAccessView(PlatformAPIView):
    platform_capabilities_by_method = {
        "GET": PlatformCapability.SCHOOLS_VIEW,
        "PATCH": PlatformCapability.SUBSCRIPTIONS_MANAGE,
    }

    class InputSerializer(serializers.Serializer):
        feature = serializers.ChoiceField(choices=MANAGED_FEATURES)
        enabled = serializers.BooleanField()

        def validate(self, attrs):
            if set(self.initial_data) - {"feature", "enabled"}:
                raise serializers.ValidationError("حقول غير معتمدة لتفعيل الميزة.")
            if not isinstance(self.initial_data.get("enabled"), bool):
                raise serializers.ValidationError("حالة التفعيل يجب أن تكون قيمة منطقية.")
            return attrs

    def get(self, request, school_id):
        school = get_object_or_404(School, pk=school_id)
        return Response({"school_id": school.id, "features": school_feature_access(school)})

    @transaction.atomic
    def patch(self, request, school_id):
        serializer = self.InputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        school = get_object_or_404(School.objects.select_for_update(), pk=school_id)
        key = serializer.validated_data["feature"]
        enabled = serializer.validated_data["enabled"]
        before = school_feature_access(school)[key]
        if school.feature_access.get(key) is not enabled:
            school.feature_access = {**school.feature_access, key: enabled}
            school.save(update_fields=["feature_access", "updated_at"])
            record_event(
                AuditAction.SCHOOL_FEATURE_ACCESS_CHANGED,
                actor=request.user,
                request=request,
                school=school,
                target_type="School",
                target_id=school.id,
                metadata={"feature": key, "before": before, "enabled": enabled},
            )
        return Response({"school_id": school.id, "features": school_feature_access(school)})


class SchoolFeatureStateView(SchoolScopedAPIView):
    read_roles = tuple(SchoolRole.values)
    write_roles = ()

    def get(self, request):
        return Response(
            {"school_id": request.school.id, "features": school_feature_access(request.school)}
        )
