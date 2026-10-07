from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response

from academics.ministry_models import CalendarProfile
from academics.services.ministry_calendar import (
    apply_ministry_calendars,
    calendar_status,
    configure_calendar_scope,
    sync_ministry_calendar,
)
from common.tenant_rls import tenant_context
from memberships.api_base import SchoolScopedAPIView
from platform_team.access import PlatformCapability
from schools.models import School
from subscriptions.permissions import PlatformAPIView


class CalendarScopeInput(serializers.Serializer):
    profile = serializers.ChoiceField(choices=CalendarProfile.choices)
    scope_note = serializers.CharField(max_length=500, allow_blank=True)


class MinistryStatusOutput(serializers.Serializer):
    source_url = serializers.URLField()
    automatic_enabled = serializers.BooleanField()
    checked_at = serializers.DateTimeField(allow_null=True)
    succeeded_at = serializers.DateTimeField(allow_null=True)
    application_checked_at = serializers.DateTimeField(allow_null=True)
    error_code = serializers.CharField(allow_blank=True)
    fingerprint = serializers.CharField(allow_null=True)
    profile = serializers.ChoiceField(choices=CalendarProfile.choices)
    scope_note = serializers.CharField(allow_blank=True)
    outcome = serializers.CharField(allow_blank=True)
    current_calendar = serializers.JSONField(allow_null=True)
    calendars = serializers.ListField(child=serializers.JSONField())


class MinistrySyncOutput(serializers.Serializer):
    sync = serializers.JSONField()
    source = MinistryStatusOutput()


class SchoolMinistryCalendarView(SchoolScopedAPIView):
    @extend_schema(responses=MinistryStatusOutput)
    def get(self, request):
        return Response(calendar_status(school=request.school))


class PlatformMinistryCalendarView(PlatformAPIView):
    platform_capabilities_by_method = {
        "GET": PlatformCapability.SCHOOLS_VIEW,
        "POST": PlatformCapability.SCHOOLS_MANAGE,
    }

    @extend_schema(responses=MinistryStatusOutput)
    def get(self, request):
        return Response(calendar_status())

    @extend_schema(request=None, responses=MinistrySyncOutput)
    def post(self, request):
        result = sync_ministry_calendar()
        if result["status"] == "FETCHED":
            result["application"] = apply_ministry_calendars()
        return Response({"sync": result, "source": calendar_status()})


class PlatformSchoolCalendarScopeView(PlatformAPIView):
    platform_capabilities_by_method = {
        "GET": PlatformCapability.SCHOOLS_VIEW,
        "PATCH": PlatformCapability.SCHOOLS_MANAGE,
    }

    @extend_schema(responses=MinistryStatusOutput)
    def get(self, request, school_id):
        with tenant_context(bypass=True):
            school = get_object_or_404(School, pk=school_id)
            return Response(calendar_status(school=school))

    @extend_schema(request=CalendarScopeInput, responses=MinistryStatusOutput)
    def patch(self, request, school_id):
        serializer = CalendarScopeInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        with tenant_context(bypass=True):
            school = get_object_or_404(School, pk=school_id)
            configure_calendar_scope(
                school=school, actor=request.user, request=request, **serializer.validated_data
            )
        # Activation always runs under individual tenant scope, not platform bypass.
        apply_ministry_calendars()
        with tenant_context(school_id=school_id):
            return Response(calendar_status(school=school))
