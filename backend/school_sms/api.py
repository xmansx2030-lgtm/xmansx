from datetime import date

from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.response import Response

from attendance.services.periods import school_now
from common.errors import ApiError
from common.pagination import DefaultPagination
from memberships.api_base import SchoolScopedAPIView
from memberships.models import SchoolRole
from school_sms.models import AbsenceSmsNotice, SchoolSmsIntegration, SmsProvider
from school_sms.services import (
    absence_preview,
    integration_payload,
    queue_absence_sms,
    save_integration,
)
from students.models import Student


class IntegrationInputSerializer(serializers.Serializer):
    provider = serializers.ChoiceField(choices=SmsProvider.choices)
    username = serializers.CharField(max_length=150, trim_whitespace=True)
    api_key = serializers.CharField(
        max_length=500, required=False, allow_blank=True, write_only=True
    )
    sender_name = serializers.CharField(max_length=30, trim_whitespace=True)
    is_active = serializers.BooleanField()

    def validate_sender_name(self, value: str) -> str:
        if any(ord(char) < 32 for char in value):
            raise serializers.ValidationError("اسم المرسل يحتوي محارف غير مسموحة.")
        return value

    def validate(self, attrs):
        if attrs["provider"] == SmsProvider.MSEGAT and len(attrs["sender_name"]) > 11:
            raise serializers.ValidationError({"sender_name": "اسم مرسل مسجات لا يتجاوز 11 حرفًا."})
        return attrs


class SendAbsenceInputSerializer(serializers.Serializer):
    date = serializers.DateField()
    student_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1), min_length=1, max_length=50
    )


def _date_or_today(request: Request) -> date:
    raw = request.query_params.get("date")
    if not raw:
        return school_now(request.school).date()
    try:
        value = date.fromisoformat(raw)
    except ValueError as exc:
        raise ApiError("VALIDATION_ERROR", "صيغة التاريخ غير صحيحة (YYYY-MM-DD).") from exc
    if value > school_now(request.school).date():
        raise ApiError("VALIDATION_ERROR", "لا يمكن إرسال غياب بتاريخ مستقبلي.")
    return value


class SchoolSmsIntegrationView(SchoolScopedAPIView):
    read_roles = (SchoolRole.SCHOOL_MANAGER,)
    write_roles = (SchoolRole.SCHOOL_MANAGER,)

    def get(self, request: Request) -> Response:
        integration = SchoolSmsIntegration.objects.filter(school=request.school).first()
        return Response(integration_payload(integration))

    def put(self, request: Request) -> Response:
        serializer = IntegrationInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(save_integration(
            school=request.school, actor=request.user,
            data=serializer.validated_data, request=request,
        ))


class AbsenceSmsPreviewView(SchoolScopedAPIView):
    read_roles = (SchoolRole.SCHOOL_MANAGER, SchoolRole.VICE_PRINCIPAL)

    def get(self, request: Request) -> Response:
        target_date = _date_or_today(request)
        try:
            page = max(int(request.query_params.get("page", "1")), 1)
        except ValueError as exc:
            raise ApiError("VALIDATION_ERROR", "رقم الصفحة غير صحيح.") from exc
        return Response(absence_preview(school=request.school, attendance_date=target_date,
                                        page=page))


class AbsenceSmsSendView(SchoolScopedAPIView):
    read_roles = (SchoolRole.SCHOOL_MANAGER, SchoolRole.VICE_PRINCIPAL)
    write_roles = (SchoolRole.SCHOOL_MANAGER, SchoolRole.VICE_PRINCIPAL)

    def post(self, request: Request) -> Response:
        serializer = SendAbsenceInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        target_date = serializer.validated_data["date"]
        if target_date > school_now(request.school).date():
            raise ApiError("VALIDATION_ERROR", "لا يمكن إرسال غياب بتاريخ مستقبلي.")
        return Response(queue_absence_sms(
            school=request.school, actor=request.user,
            attendance_date=target_date,
            student_ids=serializer.validated_data["student_ids"], request=request,
        ), status=202)


class StudentSmsHistoryView(SchoolScopedAPIView):
    read_roles = (SchoolRole.SCHOOL_MANAGER, SchoolRole.VICE_PRINCIPAL)

    def get(self, request: Request, student_id: int) -> Response:
        get_object_or_404(Student.objects.filter(school=request.school), pk=student_id)
        notices = AbsenceSmsNotice.objects.filter(
            school=request.school, student_id=student_id
        ).order_by("-updated_at", "-id")
        paginator = DefaultPagination()
        page = paginator.paginate_queryset(notices, request)
        return paginator.get_paginated_response([
            {
                "id": notice.id,
                "attendance_date": notice.attendance_date,
                "provider": notice.provider,
                "recipient_masked": notice.recipient_masked,
                "status": notice.status,
                "message_text": notice.message_text,
                "requested_at": notice.created_at,
                "attempted_at": notice.attempted_at,
                "accepted_at": notice.accepted_at,
                "attempts": notice.attempts,
            }
            for notice in page
        ])
