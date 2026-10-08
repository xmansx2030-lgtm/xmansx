"""School-reviewed contact changes and unresolved global identity requests."""

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response

from accounts.mobile import mask_mobile, normalize_mobile
from audit.services import record_event
from common.errors import ApiError
from common.pagination import DefaultPagination
from memberships.api_base import SchoolScopedAPIView
from memberships.models import SchoolRole
from parents.access import lock_parent_school
from parents.contact_security import contact_write_context
from parents.models import (
    GlobalMobileChangeRequest,
    GuardianContactReview,
    GuardianStudentRelation,
    RecipientContactBlock,
)
from parents.security import contact_hash, decrypt_value, encrypt_value, mobile_hash
from students.models import Student


class VerifiedContactInput(serializers.Serializer):
    reason = serializers.CharField(max_length=300, min_length=5)
    verification_note = serializers.CharField(max_length=600, min_length=5)
    identity_verified = serializers.BooleanField()

    def validate_identity_verified(self, value):
        if not value:
            raise serializers.ValidationError("يجب توثيق التحقق من صفة صاحب الطلب.")
        return value


def _mobile(value, *, allow_blank=False):
    from django.core.exceptions import ValidationError

    if allow_blank and not value.strip():
        return ""
    try:
        return normalize_mobile(value)
    except ValidationError as error:
        raise serializers.ValidationError(error.messages[0]) from error


class ContactInput(VerifiedContactInput):
    guardian_mobile = serializers.CharField(max_length=30, allow_blank=True)
    guardian_name = serializers.CharField(max_length=150, required=False, allow_blank=True)

    def validate_guardian_mobile(self, value):
        return _mobile(value, allow_blank=True)


class RecipientBlockInput(VerifiedContactInput):
    mobile = serializers.CharField(max_length=30, write_only=True)

    def validate_mobile(self, value):
        return _mobile(value)


class GlobalMobileInput(VerifiedContactInput):
    relation_id = serializers.IntegerField(min_value=1)
    new_mobile = serializers.CharField(max_length=30, write_only=True)

    def validate_new_mobile(self, value):
        return _mobile(value)


class ContactOutput(serializers.Serializer):
    student_id = serializers.IntegerField()
    contact_revision = serializers.IntegerField()
    guardian_mobile_masked = serializers.CharField()
    review_id = serializers.IntegerField(allow_null=True)


class ReviewOutput(serializers.Serializer):
    id = serializers.IntegerField()
    student_id = serializers.IntegerField()
    student_name = serializers.CharField()
    previous_revision = serializers.IntegerField()
    current_revision = serializers.IntegerField()
    source = serializers.CharField()
    reason = serializers.CharField()
    actor_name = serializers.CharField()
    created_at = serializers.DateTimeField()
    resolved_at = serializers.DateTimeField(allow_null=True)


class ResolutionOutput(serializers.Serializer):
    id = serializers.IntegerField()
    resolved_at = serializers.DateTimeField(allow_null=True)


class RecipientBlockOutput(serializers.Serializer):
    id = serializers.IntegerField()
    student_id = serializers.IntegerField()
    student_name = serializers.CharField(required=False)
    mobile_masked = serializers.CharField()
    reason = serializers.CharField(required=False)
    created_at = serializers.DateTimeField(required=False)
    resolved_at = serializers.DateTimeField(allow_null=True)


class GlobalMobileOutput(serializers.Serializer):
    id = serializers.IntegerField()
    student_id = serializers.IntegerField(required=False)
    student_name = serializers.CharField(required=False)
    status = serializers.ChoiceField(choices=["PENDING"])
    reason = serializers.CharField(required=False)
    new_mobile_masked = serializers.CharField()
    created_at = serializers.DateTimeField()


class ReviewQuery(serializers.Serializer):
    status = serializers.ChoiceField(choices=["open", "resolved", "all"], required=False)
    student_id = serializers.IntegerField(min_value=1, required=False)
    page = serializers.IntegerField(min_value=1, required=False)


class PageQuery(serializers.Serializer):
    page = serializers.IntegerField(min_value=1, required=False)


class ReviewPageOutput(serializers.Serializer):
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = ReviewOutput(many=True)


class BlockPageOutput(serializers.Serializer):
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = RecipientBlockOutput(many=True)


class MobileChangePageOutput(serializers.Serializer):
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = GlobalMobileOutput(many=True)


class StaffContactView(SchoolScopedAPIView):
    read_roles = (SchoolRole.SCHOOL_MANAGER, SchoolRole.VICE_PRINCIPAL)
    write_roles = read_roles

    def page(self, request, queryset, serialize):
        paginator = DefaultPagination()
        rows = paginator.paginate_queryset(queryset, request)
        return paginator.get_paginated_response([serialize(row) for row in rows])


class StudentContactView(StaffContactView):
    @extend_schema(request=ContactInput, responses=ContactOutput)
    @transaction.atomic
    def post(self, request, student_id):
        serializer = ContactInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        lock_parent_school(request.school.id)
        student = get_object_or_404(
            Student.objects.select_for_update(),
            school=request.school,
            id=student_id,
        )
        previous_mobile = student.guardian_mobile
        previous_revision = student.guardian_contact_revision
        fields = ["guardian_mobile", "updated_at"]
        student.guardian_mobile = data["guardian_mobile"]
        if "guardian_name" in data:
            student.guardian_name = data["guardian_name"]
            fields.append("guardian_name")
        with contact_write_context(
            source="STAFF_CONTACT",
            actor=request.user,
            reason=data["reason"],
            previous_mobile=previous_mobile,
            current_mobile=student.guardian_mobile,
        ):
            student.save(update_fields=fields)
        student.refresh_from_db()
        review = None
        if student.guardian_contact_revision != previous_revision:
            review = (
                GuardianContactReview.objects.filter(
                    school=request.school,
                    student=student,
                    current_revision=student.guardian_contact_revision,
                )
                .order_by("-id")
                .first()
            )
        if review:
            review.verification_note = data["verification_note"]
            review.current_mobile_hash = contact_hash(student.guardian_mobile)
            review.save(update_fields=["verification_note", "current_mobile_hash", "updated_at"])
        return Response(
            {
                "student_id": student.id,
                "contact_revision": student.guardian_contact_revision,
                "guardian_mobile_masked": mask_mobile(student.guardian_mobile),
                "review_id": review.id if review else None,
            }
        )


class ContactReviewListView(StaffContactView):
    @extend_schema(parameters=[ReviewQuery], responses=ReviewPageOutput)
    def get(self, request):
        queryset = (
            GuardianContactReview.objects.filter(school=request.school)
            .select_related(
                "student",
                "actor",
            )
            .order_by("-id")
        )
        status = request.query_params.get("status", "open")
        if status not in ("open", "resolved", "all"):
            raise ApiError("VALIDATION_ERROR", "حالة المراجعة غير صحيحة.")
        if status != "all":
            queryset = queryset.filter(resolved_at__isnull=status == "open")
        student_id = request.query_params.get("student_id")
        if student_id:
            if not student_id.isdigit():
                raise ApiError("VALIDATION_ERROR", "معرف الطالب غير صحيح.")
            queryset = queryset.filter(student_id=int(student_id))
        return self.page(
            request,
            queryset,
            lambda row: {
                "id": row.id,
                "student_id": row.student_id,
                "student_name": row.student.full_name,
                "previous_revision": row.previous_revision,
                "current_revision": row.current_revision,
                "source": row.source,
                "reason": row.reason,
                "actor_name": row.actor.display_name if row.actor else "",
                "created_at": row.created_at,
                "resolved_at": row.resolved_at,
            },
        )


class ContactReviewResolveView(StaffContactView):
    @extend_schema(request=VerifiedContactInput, responses=ResolutionOutput)
    @transaction.atomic
    def post(self, request, review_id):
        serializer = VerifiedContactInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        lock_parent_school(request.school.id)
        review = get_object_or_404(
            GuardianContactReview.objects.select_for_update(),
            school=request.school,
            id=review_id,
        )
        if review.resolved_at is None:
            review.resolved_at = timezone.now()
            review.resolved_by = request.user
            review.resolution_reason = serializer.validated_data["reason"]
            review.resolution_verification_note = serializer.validated_data["verification_note"]
            review.save(
                update_fields=[
                    "resolved_at",
                    "resolved_by",
                    "resolution_reason",
                    "resolution_verification_note",
                    "updated_at",
                ]
            )
            record_event(
                "PARENT_CONTACT_REVIEW_RESOLVED",
                school=request.school,
                actor=request.user,
                request=request,
                target_type="GuardianContactReview",
                target_id=review.id,
                metadata={"student_id": review.student_id, "source": "STAFF_CONTACT_REVIEW",
                          "resolution_documented": True},
            )
        return Response({"id": review.id, "resolved_at": review.resolved_at})


class RecipientBlockCreateView(StaffContactView):
    @extend_schema(
        request=RecipientBlockInput,
        responses={200: RecipientBlockOutput, 201: RecipientBlockOutput},
    )
    @transaction.atomic
    def post(self, request, student_id):
        serializer = RecipientBlockInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        lock_parent_school(request.school.id)
        student = get_object_or_404(
            Student.objects.select_for_update(),
            id=student_id,
            school=request.school,
        )
        block, created = RecipientContactBlock.objects.get_or_create(
            school=request.school,
            student=student,
            mobile_hash=contact_hash(data["mobile"]),
            resolved_at__isnull=True,
            defaults={
                "reason": data["reason"],
                "verification_note": data["verification_note"],
                "created_by": request.user,
            },
        )
        if created:
            record_event(
                "PARENT_RECIPIENT_BLOCKED",
                school=request.school,
                actor=request.user,
                request=request,
                target_type="RecipientContactBlock",
                target_id=block.id,
                metadata={"student_id": student.id},
            )
        return Response(
            {
                "id": block.id,
                "student_id": student.id,
                "mobile_masked": mask_mobile(data["mobile"]),
                "resolved_at": block.resolved_at,
            },
            status=201 if created else 200,
        )


class RecipientBlockListView(StaffContactView):
    @extend_schema(parameters=[PageQuery], responses=BlockPageOutput)
    def get(self, request):
        queryset = (
            RecipientContactBlock.objects.filter(
                school=request.school,
                resolved_at__isnull=True,
            )
            .select_related("student")
            .order_by("-id")
        )
        return self.page(
            request,
            queryset,
            lambda row: {
                "id": row.id,
                "student_id": row.student_id,
                "student_name": row.student.full_name,
                "reason": row.reason,
                "created_at": row.created_at,
                "resolved_at": row.resolved_at,
                "mobile_masked": mask_mobile(row.student.guardian_mobile)
                if contact_hash(row.student.guardian_mobile) == row.mobile_hash
                else "رقم سابق",
            },
        )


class RecipientBlockResolveView(StaffContactView):
    @extend_schema(request=VerifiedContactInput, responses=ResolutionOutput)
    @transaction.atomic
    def post(self, request, block_id):
        serializer = VerifiedContactInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        lock_parent_school(request.school.id)
        block = get_object_or_404(
            RecipientContactBlock.objects.select_for_update(),
            id=block_id,
            school=request.school,
        )
        if block.resolved_at is None:
            block.resolved_at = timezone.now()
            block.resolved_by = request.user
            block.resolution_reason = serializer.validated_data["reason"]
            block.resolution_verification_note = serializer.validated_data["verification_note"]
            block.save(update_fields=["resolved_at", "resolved_by", "resolution_reason",
                                      "resolution_verification_note", "updated_at"])
            record_event(
                "PARENT_RECIPIENT_BLOCK_RESOLVED",
                school=request.school,
                actor=request.user,
                request=request,
                target_type="RecipientContactBlock",
                target_id=block.id,
                metadata={"student_id": block.student_id, "source": "STAFF_RECIPIENT_REVIEW",
                          "resolution_documented": True},
            )
        return Response({"id": block.id, "resolved_at": block.resolved_at})


class GlobalMobileChangeView(StaffContactView):
    @extend_schema(request=GlobalMobileInput, responses={201: GlobalMobileOutput})
    @transaction.atomic
    def post(self, request, student_id):
        serializer = GlobalMobileInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        lock_parent_school(request.school.id)
        get_object_or_404(Student.objects.select_for_update(), id=student_id, school=request.school)
        relation = get_object_or_404(
            GuardianStudentRelation.objects.select_for_update(),
            id=data["relation_id"],
            student_id=student_id,
            school=request.school,
        )
        change = GlobalMobileChangeRequest.objects.create(
            user=relation.user,
            school=request.school,
            student_id=student_id,
            requested_by=request.user,
            new_mobile_encrypted=encrypt_value(data["new_mobile"]),
            new_mobile_hash=mobile_hash(data["new_mobile"]),
            reason=data["reason"],
            verification_note=data["verification_note"],
        )
        record_event(
            "PARENT_GLOBAL_MOBILE_CHANGE_REQUESTED",
            school=request.school,
            actor=request.user,
            request=request,
            target_type="GlobalMobileChangeRequest",
            target_id=change.id,
            metadata={"student_id": student_id},
        )
        return Response(
            {
                "id": change.id,
                "status": change.status,
                "new_mobile_masked": mask_mobile(data["new_mobile"]),
                "created_at": change.created_at,
            },
            status=201,
        )


class GlobalMobileChangeListView(StaffContactView):
    @extend_schema(parameters=[PageQuery], responses=MobileChangePageOutput)
    def get(self, request):
        queryset = (
            GlobalMobileChangeRequest.objects.filter(
                school=request.school,
            )
            .select_related("student")
            .order_by("-id")
        )
        return self.page(
            request,
            queryset,
            lambda row: {
                "id": row.id,
                "student_id": row.student_id,
                "student_name": row.student.full_name,
                "status": row.status,
                "reason": row.reason,
                "new_mobile_masked": mask_mobile(decrypt_value(row.new_mobile_encrypted)),
                "created_at": row.created_at,
            },
        )
