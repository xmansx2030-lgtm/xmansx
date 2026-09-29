"""Explicit, school-scoped student merge for the school manager."""

from django.db import IntegrityError
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.response import Response

from common.errors import ApiError
from memberships.api_base import SchoolScopedAPIView
from memberships.models import SchoolRole
from students.services.manual_merge import apply_manual_merge, preview_manual_merge


class MergeSelectionSerializer(serializers.Serializer):
    target_id = serializers.IntegerField(min_value=1)
    source_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1), min_length=1, max_length=9
    )

    def validate(self, attrs):
        ids = [attrs["target_id"], *attrs["source_ids"]]
        if len(ids) != len(set(ids)):
            raise serializers.ValidationError("يجب اختيار سجلات مختلفة للدمج.")
        return attrs


class MergeConfirmationSerializer(serializers.Serializer):
    confirmation_token = serializers.CharField(max_length=1000)
    confirmed_same_person = serializers.BooleanField()

    def validate_confirmed_same_person(self, value):
        if not value:
            raise serializers.ValidationError("يلزم تأكيد أن السجلات تخص الطالب نفسه.")
        return value


class ManagerMergeView(SchoolScopedAPIView):
    read_roles = (SchoolRole.SCHOOL_MANAGER,)
    write_roles = (SchoolRole.SCHOOL_MANAGER,)


class MergePreviewView(ManagerMergeView):
    def post(self, request: Request) -> Response:
        serializer = MergeSelectionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        return Response(
            preview_manual_merge(
                school=request.school,
                actor=request.user,
                ids=[data["target_id"], *data["source_ids"]],
            )
        )


class MergeApplyView(ManagerMergeView):
    def post(self, request: Request) -> Response:
        serializer = MergeConfirmationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            result = apply_manual_merge(
                school=request.school,
                actor=request.user,
                request=request,
                token=serializer.validated_data["confirmation_token"],
            )
        except IntegrityError as exc:
            raise ApiError(
                "MERGE_DATA_CONFLICT",
                "تغيرت البيانات المرتبطة بهذه السجلات؛ أعد المعاينة قبل الدمج.",
                status_code=409,
            ) from exc
        return Response(result)
