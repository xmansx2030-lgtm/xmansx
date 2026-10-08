"""CSRF-protected owner enrollment and narrowly scoped public bearer reset."""

import secrets
from collections.abc import Mapping
from time import monotonic, sleep

from django.core.exceptions import ValidationError
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.mobile import normalize_mobile
from audit.services import client_ip
from parents import email_recovery_services as services
from parents.email_recovery_models import RecoveryEmailPurpose
from parents.rate_limit import consume


class StrictInput(serializers.Serializer):
    def to_internal_value(self, data):
        if isinstance(data, Mapping) and set(data) - set(self.fields):
            raise serializers.ValidationError("حقول غير مسموحة في طلب استرداد الحساب.")
        return super().to_internal_value(data)


class EnrollInput(StrictInput):
    email = serializers.CharField(max_length=254, write_only=True)
    current_password = serializers.CharField(max_length=128, trim_whitespace=False, write_only=True)

    def validate_email(self, value):
        try:
            return services.normalize_recovery_email(value)
        except ValidationError as exc:
            raise serializers.ValidationError(exc.messages[0]) from exc


class EmptyInput(StrictInput):
    pass


class BearerInput(StrictInput):
    token = serializers.CharField(min_length=40, max_length=128, write_only=True)


class PasswordRequestInput(StrictInput):
    mobile = serializers.CharField(max_length=30, write_only=True)

    def validate_mobile(self, value):
        try:
            return normalize_mobile(value)
        except ValidationError as exc:
            raise serializers.ValidationError(exc.messages[0]) from exc


class PasswordCompleteInput(BearerInput):
    new_password = serializers.CharField(max_length=128, trim_whitespace=False, write_only=True)
    confirm_password = serializers.CharField(max_length=128, trim_whitespace=False, write_only=True)


class EmailStatusOutput(serializers.Serializer):
    verified = serializers.BooleanField()
    verification_required = serializers.BooleanField()
    email_masked = serializers.CharField()
    pending_email_masked = serializers.CharField()
    delivery_status = serializers.CharField(allow_null=True)
    enabled = serializers.BooleanField()


class TokenStatusOutput(serializers.Serializer):
    status = serializers.CharField()


class MessageOutput(serializers.Serializer):
    message = serializers.CharField()


@method_decorator(csrf_protect, name="dispatch")
class RecoveryEmailBase(APIView):
    permission_classes = [IsAuthenticated]

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "no-store, private"
        response["Referrer-Policy"] = "no-referrer"
        return response

    def data(self, request, serializer_class):
        consume(kind="email-recovery-ip", value=client_ip(request) or "unknown", limit=120)
        if request.user.is_authenticated:
            consume(kind="email-recovery-user", value=str(request.user.id), limit=30)
        serializer = serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data


class RecoveryEmailView(RecoveryEmailBase):
    @extend_schema(responses=EmailStatusOutput)
    def get(self, request):
        return Response(services.email_status(request.user))

    @extend_schema(request=EnrollInput, responses=EmailStatusOutput)
    def post(self, request):
        data = self.data(request, EnrollInput)
        return Response(services.enroll_recovery_email(request.user, **data))


class RecoveryEmailResendView(RecoveryEmailBase):
    @extend_schema(request=EmptyInput, responses=EmailStatusOutput)
    def post(self, request):
        self.data(request, EmptyInput)
        return Response(services.resend_verification(request.user))


class RecoveryEmailVerifyCheckView(RecoveryEmailBase):
    @extend_schema(request=BearerInput, responses=TokenStatusOutput)
    def post(self, request):
        data = self.data(request, BearerInput)
        return Response(
            services.check_token(
                data["token"], RecoveryEmailPurpose.RECOVERY_EMAIL_VERIFICATION, actor=request.user
            )
        )


class RecoveryEmailVerifyView(RecoveryEmailBase):
    @extend_schema(request=BearerInput, responses=EmailStatusOutput)
    def post(self, request):
        data = self.data(request, BearerInput)
        return Response(services.verify_recovery_email(request.user, data["token"]))


class ParentPasswordRecoveryView(RecoveryEmailBase):
    permission_classes = [AllowAny]

    @extend_schema(request=PasswordRequestInput, responses={202: MessageOutput})
    def post(self, request):
        started = monotonic()
        data = self.data(request, PasswordRequestInput)
        # Same mobile counter applies even when the account does not exist.
        consume(kind="email-reset-mobile", value=data["mobile"], limit=5)
        services.request_password_recovery(data["mobile"])
        # Fast missing/blocked accounts must not advertise themselves through timing.
        # This bounded local padding does not claim constant time under DB overload.
        remaining = 0.2 + secrets.randbelow(20) / 1000 - (monotonic() - started)
        if remaining > 0:
            sleep(remaining)
        return Response({"message": services.GENERIC_RESET_MESSAGE}, status=202)


class ParentPasswordRecoveryCheckView(RecoveryEmailBase):
    permission_classes = [AllowAny]

    @extend_schema(request=BearerInput, responses=TokenStatusOutput)
    def post(self, request):
        data = self.data(request, BearerInput)
        consume(kind="email-reset-token", value=data["token"], limit=10)
        return Response(services.check_token(data["token"], RecoveryEmailPurpose.PASSWORD_RESET))


class ParentPasswordRecoveryCompleteView(RecoveryEmailBase):
    permission_classes = [AllowAny]

    @extend_schema(request=PasswordCompleteInput, responses=MessageOutput)
    def post(self, request):
        data = self.data(request, PasswordCompleteInput)
        consume(kind="email-reset-token", value=data["token"], limit=10)
        return Response(services.complete_password_recovery(**data))
