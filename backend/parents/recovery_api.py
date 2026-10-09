"""Whitelisted school intake and explicitly authorized central review APIs."""

from collections.abc import Mapping

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.mobile import normalize_mobile
from audit.services import record_event
from common.errors import ApiError
from common.pagination import DefaultPagination
from common.tenant_rls import tenant_context
from parents.access import lock_parent_school
from parents.contact_api import StaffContactView, VerifiedContactInput
from parents.models import GlobalMobileChangeRequest, GuardianStudentRelation
from parents.rate_limit import consume
from parents.recovery_models import (
    GlobalAccountRecoveryCase,
    RecoveryEvidenceKind,
    RecoveryEvidenceReference,
    RecoveryOperation,
    RecoveryRecommendation,
    RecoveryReviewStage,
    RecoveryStatus,
)
from parents.recovery_services import (
    case_payload,
    execute_recovery,
    open_case_from_source,
    record_reference,
    recovery_scope,
    require_reviewer,
    review_case,
    revoke_reference,
)
from parents.security import encrypt_value, mobile_hash
from students.models import Student


class StrictInput(serializers.Serializer):
    def to_internal_value(self, data):
        if not isinstance(data, Mapping):
            return super().to_internal_value(data)
        unknown = set(data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError("حقول غير مسموحة في طلب الاستعادة.")
        return super().to_internal_value(data)


class RecoveryIntakeInput(StrictInput, VerifiedContactInput):
    relation_id = serializers.IntegerField(min_value=1)
    operation = serializers.ChoiceField(choices=RecoveryOperation.choices)
    new_mobile = serializers.CharField(max_length=30, required=False, write_only=True)

    def validate(self, attrs):
        if attrs["operation"] == RecoveryOperation.PASSWORD_RECOVERY and "new_mobile" in attrs:
            raise serializers.ValidationError(
                {"new_mobile": "استعادة كلمة المرور لا تتضمن تغيير رقم الدخول."}
            )
        if attrs["operation"] != RecoveryOperation.PASSWORD_RECOVERY and not attrs.get(
            "new_mobile"
        ):
            raise serializers.ValidationError({"new_mobile": "أدخل الرقم المقترح."})
        if attrs.get("new_mobile"):
            from django.core.exceptions import ValidationError

            try:
                attrs["new_mobile"] = normalize_mobile(attrs["new_mobile"])
            except ValidationError as error:
                raise serializers.ValidationError({"new_mobile": error.messages[0]}) from error
        return attrs


class CaseOutput(serializers.Serializer):
    id = serializers.UUIDField()
    source_request_id = serializers.IntegerField()
    school_id = serializers.IntegerField()
    student_id = serializers.IntegerField()
    operation = serializers.CharField()
    status = serializers.CharField()
    version = serializers.IntegerField()
    expires_at = serializers.DateTimeField()
    created_at = serializers.DateTimeField()
    execution_enabled = serializers.BooleanField()
    policy_code = serializers.CharField()
    new_mobile_masked = serializers.CharField()
    account_id = serializers.IntegerField(required=False)
    requester_id = serializers.IntegerField(required=False)


class CasePageOutput(serializers.Serializer):
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = CaseOutput(many=True)


class CaseVersionInput(StrictInput):
    expected_version = serializers.IntegerField(min_value=1)


class EvidenceInput(CaseVersionInput):
    kind = serializers.ChoiceField(choices=RecoveryEvidenceKind.choices)
    reference_id = serializers.UUIDField()
    expires_at = serializers.DateTimeField()


class EvidenceOutput(serializers.Serializer):
    id = serializers.IntegerField()
    kind = serializers.CharField()
    reference_id = serializers.UUIDField()
    expires_at = serializers.DateTimeField()
    revoked_at = serializers.DateTimeField(allow_null=True)
    verified = serializers.BooleanField()


class EvidenceCreatedOutput(serializers.Serializer):
    evidence = EvidenceOutput()
    case = CaseOutput()


class ReviewInput(CaseVersionInput):
    stage = serializers.ChoiceField(choices=RecoveryReviewStage.choices)
    recommendation = serializers.ChoiceField(choices=RecoveryRecommendation.choices)
    note = serializers.CharField(max_length=600, required=False, allow_blank=True, write_only=True)


class ErrorOutput(serializers.Serializer):
    code = serializers.CharField()
    message = serializers.CharField()


class NoStoreMixin:
    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "no-store, private"
        return response


class SchoolRecoveryIntakeView(NoStoreMixin, StaffContactView):
    @extend_schema(request=RecoveryIntakeInput, responses={201: CaseOutput})
    @transaction.atomic
    def post(self, request, student_id):
        data = RecoveryIntakeInput(data=request.data)
        data.is_valid(raise_exception=True)
        data = data.validated_data
        consume(kind="recovery-intake", value=str(request.user.id), limit=30)
        lock_parent_school(request.school.id)
        get_object_or_404(Student.objects.select_for_update(), id=student_id, school=request.school)
        relation = get_object_or_404(
            GuardianStudentRelation.objects.select_for_update(),
            id=data["relation_id"],
            school=request.school,
            student_id=student_id,
        )
        if relation.user_id == request.user.id:
            raise ApiError(
                "RECOVERY_INTAKE_CONFLICT", "يلزم موظف مستقل لاستقبال الطلب.", status_code=409
            )
        proposed = data.get("new_mobile") or relation.user.mobile
        source = GlobalMobileChangeRequest.objects.create(
            user_id=relation.user_id,
            school=request.school,
            student_id=student_id,
            requested_by=request.user,
            new_mobile_encrypted=encrypt_value(proposed),
            new_mobile_hash=mobile_hash(proposed),
            reason=data["reason"],
            verification_note=data["verification_note"],
        )
        case = open_case_from_source(source, operation=data["operation"])
        return Response(case_payload(case), status=201)


class SchoolRecoveryListView(NoStoreMixin, StaffContactView):
    @extend_schema(responses=CasePageOutput)
    def get(self, request):
        query = (
            GlobalAccountRecoveryCase.objects.filter(school=request.school)
            .select_related("source_request")
            .order_by("-created_at", "id")
        )
        return self.page(request, query, case_payload)


class SchoolRecoveryCancelView(NoStoreMixin, StaffContactView):
    @extend_schema(request=CaseVersionInput, responses=CaseOutput)
    @transaction.atomic
    def post(self, request, case_id):
        data = CaseVersionInput(data=request.data)
        data.is_valid(raise_exception=True)
        lock_parent_school(request.school.id)
        case = get_object_or_404(
            GlobalAccountRecoveryCase.objects.select_for_update(), id=case_id, school=request.school
        )
        if case.version != data.validated_data["expected_version"]:
            raise ApiError("RECOVERY_CASE_CHANGED", "تغيرت القضية؛ أعد تحميلها.", status_code=409)
        if case.status in {
            RecoveryStatus.REJECTED,
            RecoveryStatus.CANCELLED,
            RecoveryStatus.EXPIRED,
        }:
            raise ApiError("RECOVERY_CASE_CLOSED", "القضية مغلقة.", status_code=409)
        case.status = (
            RecoveryStatus.EXPIRED
            if case.expires_at <= timezone.now()
            else RecoveryStatus.CANCELLED
        )
        case.save(update_fields=["status", "updated_at"])
        record_event(
            "PARENT_RECOVERY_CASE_CANCELLED",
            school=request.school,
            actor=request.user,
            target_type="GlobalAccountRecoveryCase",
            target_id=case.id,
            metadata={"case_version": case.version},
        )
        return Response(case_payload(case))


class CentralRecoveryView(NoStoreMixin, APIView):
    permission_classes = [IsAuthenticated]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        require_reviewer(request.user)
        if request.method != "GET":
            consume(kind="recovery-review", value=str(request.user.id), limit=120)


class CentralRecoveryListView(CentralRecoveryView):
    @extend_schema(operation_id="parent_recovery_central_list", responses=CasePageOutput)
    def get(self, request):
        with tenant_context(user_id=request.user.id):
            query = GlobalAccountRecoveryCase.objects.select_related("source_request").order_by(
                "-created_at", "id"
            )
            paginator = DefaultPagination()
            rows = paginator.paginate_queryset(query, request)
            payload = [case_payload(row, central=True) for row in rows]
        return paginator.get_paginated_response(payload)


class CentralRecoveryDetailView(CentralRecoveryView):
    @extend_schema(operation_id="parent_recovery_central_detail", responses=CaseOutput)
    def get(self, request, case_id):
        with recovery_scope(request.user, case_id) as case:
            record_event(
                "PARENT_RECOVERY_CASE_VIEWED",
                actor=request.user,
                school=case.school,
                target_type="GlobalAccountRecoveryCase",
                target_id=case.id,
            )
            return Response(case_payload(case, central=True))


def reference_payload(row):
    return {
        "id": row.id,
        "kind": row.kind,
        "reference_id": row.reference_id,
        "expires_at": row.expires_at,
        "revoked_at": row.revoked_at,
        "verified": False,
    }


class CentralRecoveryEvidenceView(CentralRecoveryView):
    @extend_schema(responses=EvidenceOutput(many=True))
    def get(self, request, case_id):
        with recovery_scope(request.user, case_id) as case:
            rows = list(RecoveryEvidenceReference.objects.filter(case=case).order_by("id")[:100])
            record_event(
                "PARENT_RECOVERY_REFERENCES_VIEWED",
                actor=request.user,
                school=case.school,
                target_type="GlobalAccountRecoveryCase",
                target_id=case.id,
                metadata={"count": len(rows)},
            )
            return Response([reference_payload(row) for row in rows])

    @extend_schema(request=EvidenceInput, responses={201: EvidenceCreatedOutput})
    def post(self, request, case_id):
        data = EvidenceInput(data=request.data)
        data.is_valid(raise_exception=True)
        row, case = record_reference(request.user, case_id, **data.validated_data)
        return Response(
            {"evidence": reference_payload(row), "case": case_payload(case, central=True)},
            status=201,
        )


class CentralRecoveryEvidenceRevokeView(CentralRecoveryView):
    @extend_schema(request=CaseVersionInput, responses=CaseOutput)
    def post(self, request, case_id, evidence_id):
        data = CaseVersionInput(data=request.data)
        data.is_valid(raise_exception=True)
        case = revoke_reference(request.user, case_id, evidence_id, **data.validated_data)
        return Response(case_payload(case, central=True))


class CentralRecoveryReviewView(CentralRecoveryView):
    @extend_schema(request=ReviewInput, responses=CaseOutput)
    def post(self, request, case_id):
        data = ReviewInput(data=request.data)
        data.is_valid(raise_exception=True)
        case = review_case(request.user, case_id, **data.validated_data)
        return Response(case_payload(case, central=True))


class CentralRecoveryExecuteView(CentralRecoveryView):
    @extend_schema(
        request={"application/json": {"type": "object", "additionalProperties": False}},
        responses={423: ErrorOutput},
    )
    def post(self, request, case_id):
        data = StrictInput(data=request.data)
        data.is_valid(raise_exception=True)
        execute_recovery(actor=request.user, case_id=case_id)
