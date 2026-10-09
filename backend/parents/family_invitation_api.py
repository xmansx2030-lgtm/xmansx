"""Reviewed school families and a bounded private bearer activation flow."""

from django.contrib.auth import login
from django.db import transaction
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.api.serializers import build_me_payload
from audit.services import client_ip
from common.pagination import DefaultPagination
from common.tenant_rls import tenant_context
from memberships.api_base import SchoolScopedAPIView
from memberships.models import SchoolRole
from memberships.selectors import active_memberships_for_user, invited_memberships_for_user
from parents import family_invitation_services as services
from parents.models import GuardianFamilyInvitation
from parents.rate_limit import consume
from parents.serializers import (
    ActivationSerializer,
    ParentAccountSerializer,
    RegistrationSerializer,
    TokenSerializer,
)

REVIEW_ROLES = (SchoolRole.SCHOOL_MANAGER, SchoolRole.VICE_PRINCIPAL)


class PrivateResponseMixin:
    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "no-store, private"
        response["Referrer-Policy"] = "no-referrer"
        return response


class InvitationChildInput(serializers.Serializer):
    id = serializers.IntegerField(min_value=1)
    revision = serializers.IntegerField(min_value=1)


class InvitationInput(serializers.Serializer):
    mobile = RegistrationSerializer().fields["mobile"]
    name = serializers.CharField(min_length=3, max_length=150)
    relationship_type = serializers.CharField(min_length=2, max_length=60)
    verification_note = serializers.CharField(min_length=10, max_length=600)
    children = InvitationChildInput(many=True, min_length=1, max_length=services.MAX_CHILDREN)
    reissue = serializers.BooleanField(default=False)

    def validate_mobile(self, value):
        return RegistrationSerializer().validate_mobile(value)

    def validate_children(self, value):
        if len({child["id"] for child in value}) != len(value):
            raise serializers.ValidationError("لا تكرر الطالب في الدعوة.")
        return value


class InvitationBatchInput(serializers.Serializer):
    invitations = InvitationInput(many=True, min_length=1, max_length=20)


class InvitationOutput(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    mobile_masked = serializers.CharField()
    delivery_status = serializers.CharField()
    lifecycle = serializers.CharField()
    created_at = serializers.DateTimeField()
    expires_at = serializers.DateTimeField()
    consumed_at = serializers.DateTimeField(allow_null=True)
    failure_code = serializers.CharField(allow_blank=True)
    student_ids = serializers.ListField(child=serializers.IntegerField())
    partial = serializers.BooleanField()


class FamilyChildOutput(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    revision = serializers.IntegerField()


class FamilyOutput(serializers.Serializer):
    key = serializers.CharField()
    name = serializers.CharField()
    names = serializers.ListField(child=serializers.CharField())
    mobile = serializers.CharField(allow_blank=True)
    mobile_masked = serializers.CharField()
    needs_review = serializers.BooleanField()
    child_count = serializers.IntegerField()
    children = FamilyChildOutput(many=True)
    invitation = InvitationOutput(allow_null=True)


class FamiliesOutput(serializers.Serializer):
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = FamilyOutput(many=True)
    sms_enabled = serializers.BooleanField()
    sms_configured = serializers.BooleanField()


class InvitationBatchOutput(serializers.Serializer):
    invitations = InvitationOutput(many=True)


class StaffFamiliesView(PrivateResponseMixin, SchoolScopedAPIView):
    feature_key = "PARENT_PORTAL"
    read_roles = write_roles = REVIEW_ROLES

    @extend_schema(responses=FamiliesOutput)
    def get(self, request):
        return Response(services.families_page(request.school, DefaultPagination(), request))

    @extend_schema(request=InvitationBatchInput, responses={201: InvitationBatchOutput})
    def post(self, request):
        serializer = InvitationBatchInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data["invitations"]
        consume(kind="family-invite-staff", value=str(request.user.id), limit=200)
        for item in data:
            consume(
                kind="family-invite-mobile", value=f"{request.school.id}:{item['mobile']}", limit=3
            )
        with transaction.atomic():
            # Acquire all selected student locks in one shared order for batches.
            services.lock_parent_school(request.school.id)
            for digest in sorted({services.mobile_hash(item["mobile"]) for item in data}):
                services.lock_family(request.school.id, digest)
            ids = sorted({child["id"] for item in data for child in item["children"]})
            list(
                services._students(request.school)
                .filter(id__in=ids)
                .order_by("id")
                .select_for_update()
            )
            created = [
                services.create_invitation(
                    school=request.school, membership=request.membership, data=item, request=request
                )
                for item in data
            ]
        rows = GuardianFamilyInvitation.objects.filter(
            id__in=[item.id for item in created], school=request.school
        ).prefetch_related("children__student", "children__activation")
        return Response({"invitations": [services.invitation_row(row) for row in rows]}, status=201)


class InvitationMetadata(serializers.Serializer):
    school_name = serializers.CharField()
    children_count = serializers.IntegerField()
    account_exists = serializers.BooleanField()
    requires_login = serializers.BooleanField()
    email_verified = serializers.BooleanField()


class FamilyActivationInput(ActivationSerializer):
    email = serializers.EmailField(max_length=254, required=False)


@method_decorator(csrf_protect, name="dispatch")
class FamilyInvitationCheckView(PrivateResponseMixin, APIView):
    permission_classes = [AllowAny]

    @extend_schema(request=TokenSerializer, responses=InvitationMetadata)
    def post(self, request):
        consume(kind="family-invite-check", value=client_ip(request) or "unknown", limit=120)
        serializer = TokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        response = Response(
            services.inspect_invitation(serializer.validated_data["token"], request.user)
        )
        response["Cache-Control"] = "no-store"
        response["Referrer-Policy"] = "no-referrer"
        return response


@method_decorator(csrf_protect, name="dispatch")
class FamilyInvitationActivationView(PrivateResponseMixin, APIView):
    permission_classes = [AllowAny]

    @extend_schema(request=FamilyActivationInput, responses=ParentAccountSerializer)
    def post(self, request):
        consume(kind="family-invite-complete", value=client_ip(request) or "unknown", limit=60)
        serializer = FamilyActivationInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        account = services.complete_invitation(
            user=request.user, request=request, **serializer.validated_data
        )
        login(request, account, backend="django.contrib.auth.backends.ModelBackend")
        with tenant_context(user_id=account.id):
            memberships = list(active_memberships_for_user(account))
            active = next(
                (
                    item
                    for item in memberships
                    if item.school_id == request.session.get("active_school_id")
                ),
                None,
            )
            response = Response(
                build_me_payload(
                    account, memberships, active, invited_memberships_for_user(account)
                )
            )
        response["Cache-Control"] = "no-store"
        response["Referrer-Policy"] = "no-referrer"
        return response
