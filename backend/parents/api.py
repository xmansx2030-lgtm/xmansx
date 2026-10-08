"""Whitelisted public/family/staff APIs; school staff and parent authority stay separate."""

from django.conf import settings
from django.contrib.auth import login
from django.db.models import Avg, Count, F, Q
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.api.serializers import build_me_payload
from audit.services import client_ip, record_event
from common.errors import ApiError
from common.pagination import DefaultPagination
from common.tenant_rls import tenant_context
from memberships.api_base import SchoolScopedAPIView
from memberships.models import SchoolRole
from memberships.selectors import active_memberships_for_user, invited_memberships_for_user
from parents import selectors, services
from parents import serializers as output
from parents.access import (
    ParentAPIView,
    owned_relation_index,
    parent_school_read,
    parent_scope,
    relation_school_groups,
)
from parents.models import (
    GuardianRegistrationRequest,
    GuardianStudentRelation,
    ParentRegistrationConfig,
)
from parents.rate_limit import consume
from parents.serializers import (
    ActivationSerializer,
    HistorySerializer,
    PasswordChangeSerializer,
    ReceiptSerializer,
    RegistrationDecisionSerializer,
    RegistrationSerializer,
    RelationDecisionSerializer,
    ResponseSerializer,
    SettingsSerializer,
    TokenSerializer,
)


@method_decorator(csrf_protect, name="dispatch")
class RegistrationView(APIView):
    permission_classes = [AllowAny]
    serializer_class = RegistrationSerializer

    @extend_schema(responses=output.RegistrationMetadataSerializer)
    def get(self, request, token):
        school = services.registration_config(token)
        return Response({"school_name": school.name, "school_id": school.id, "enabled": True})

    @extend_schema(
        request=RegistrationSerializer, responses={202: output.RegistrationReceiptSerializer}
    )
    def post(self, request, token):
        consume(
            kind="registration-ip",
            value=client_ip(request) or "unknown",
            limit=settings.PARENT_REGISTRATION_IP_LIMIT,
        )
        serializer = RegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        consume(
            kind="registration-mobile",
            value=data["mobile"],
            limit=settings.PARENT_REGISTRATION_MOBILE_LIMIT,
        )
        school = services.registration_config(token)
        return Response(
            services.submit_registration(
                school=school, data=data, user=request.user, request=request
            ),
            status=202,
        )


@method_decorator(csrf_protect, name="dispatch")
class ReceiptView(APIView):
    permission_classes = [AllowAny]
    serializer_class = ReceiptSerializer

    @extend_schema(request=ReceiptSerializer, responses=output.ReceiptStatusSerializer)
    def post(self, request):
        consume(kind="receipt-ip", value=client_ip(request) or "unknown", limit=120)
        serializer = ReceiptSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(
            services.receipt_status(
                serializer.validated_data["receipt_token"],
                applicant_note=serializer.validated_data.get("applicant_note"),
            )
        )


@method_decorator(csrf_protect, name="dispatch")
class ActivationCheckView(APIView):
    permission_classes = [AllowAny]
    serializer_class = TokenSerializer

    @extend_schema(request=TokenSerializer, responses=output.ActivationMetadataSerializer)
    def post(self, request):
        consume(kind="activation-ip", value=client_ip(request) or "unknown", limit=120)
        serializer = TokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(
            services.inspect_activation(serializer.validated_data["token"], user=request.user)
        )


@method_decorator(csrf_protect, name="dispatch")
class ActivationView(APIView):
    permission_classes = [AllowAny]
    serializer_class = ActivationSerializer

    @extend_schema(request=ActivationSerializer, responses=output.ParentAccountSerializer)
    def post(self, request):
        consume(kind="activation-ip", value=client_ip(request) or "unknown", limit=120)
        serializer = ActivationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        account = services.complete_activation(
            user=request.user, request=request, **serializer.validated_data
        )
        login(request, account, backend="django.contrib.auth.backends.ModelBackend")
        with tenant_context(user_id=account.id):
            memberships = list(active_memberships_for_user(account))
            active_id = request.session.get("active_school_id")
            active = next((m for m in memberships if m.school_id == active_id), None)
            return Response(
                build_me_payload(
                    account, memberships, active, invited_memberships_for_user(account)
                )
            )


class ChildrenView(ParentAPIView):
    serializer_class = ResponseSerializer

    @extend_schema(operation_id="parent_children_list", responses=output.ChildrenSerializer)
    def get(self, request):
        from parents.request_models import ParentNotification
        from parents.request_services import sync_activity_notifications

        rows = {}
        page = DefaultPagination()
        index_page = page.paginate_queryset(owned_relation_index(request.user), request, view=self)
        for school_id, group in relation_school_groups(index_page):
            school_name = "المدرسة"
            details = {}
            inboxes = {}
            try:
                with parent_school_read(
                    request.user, school_id, [item["id"] for item in group],
                ) as scope:
                    relations = scope.current_relations()
                    for item in group:
                        relation = relations.get(item["id"]) if item["status"] == "ACTIVE" else None
                        if relation is None:
                            continue
                        details[relation.pk] = selectors.child_day(relation)
                        sync_activity_notifications(relation)
                    # A sibling may be withdrawn while another child's facts are read.
                    current = scope.current_relations()
                    details = {
                        relation_id: detail for relation_id, detail in details.items()
                        if relation_id in current
                    }
                    school_name = scope.school_name
                    inboxes = {
                        row["relation_id"]: row for row in ParentNotification.objects.filter(
                            relation_id__in=details, user=request.user,
                        ).values("relation_id").annotate(
                            new_notifications=Count("id", filter=Q(read_at__isnull=True)),
                            required_actions=Count(
                                "id",
                                filter=Q(
                                    requires_action=True,
                                    action_completed_at__isnull=True,
                                ),
                            ),
                        )
                    }
            except ApiError as exc:
                if exc.status_code not in {403, 404}:
                    raise
                details = {}
            for item in group:
                detail = details.get(item["id"])
                if detail is not None:
                    inbox = inboxes.get(item["id"], {})
                    rows[item["id"]] = {
                        **detail["child"], "today": detail["today"], "morning": detail["morning"],
                        "new_notifications": inbox.get("new_notifications", 0),
                        "required_actions": inbox.get("required_actions", 0),
                    }
                else:
                    rows[item["id"]] = {
                        "relation_id": item["id"],
                        "school": {"id": item["school_id"], "name": school_name or "المدرسة"},
                        "student": None,
                        "status": item["status"] if item["status"] != "ACTIVE" else "UNAVAILABLE",
                        "today": None, "new_notifications": 0, "required_actions": 0,
                    }
        return page.get_paginated_response([rows[item["id"]] for item in index_page])


class ChildView(ParentAPIView):
    serializer_class = ResponseSerializer

    @extend_schema(responses=output.ChildDetailSerializer)
    def get(self, request, relation_id):
        day = (
            serializers.DateField().run_validation(request.query_params["date"])
            if "date" in request.query_params
            else None
        )
        with parent_scope(request.user, relation_id) as relation:
            return Response(selectors.child_day(relation, day))


class HistoryView(ParentAPIView):
    serializer_class = HistorySerializer

    @extend_schema(parameters=[HistorySerializer], responses=output.ParentHistorySerializer)
    def get(self, request, relation_id):
        serializer = HistorySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        with parent_scope(request.user, relation_id) as relation:
            return Response(selectors.child_history(relation, **serializer.validated_data))


class ParentStaffView(SchoolScopedAPIView):
    read_roles = (SchoolRole.SCHOOL_MANAGER, SchoolRole.VICE_PRINCIPAL)
    write_roles = read_roles
    serializer_class = ResponseSerializer


class ParentPasswordView(ParentAPIView):
    requires_verified_email = False
    serializer_class = PasswordChangeSerializer

    @extend_schema(request=PasswordChangeSerializer, responses=ResponseSerializer)
    def post(self, request):
        from django.contrib.auth import update_session_auth_hash
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError
        from django.db import transaction

        from accounts.models import User

        consume(kind="password-user", value=str(request.user.id), limit=10)
        serializer = PasswordChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if data["new_password"] != data["confirm_password"]:
            raise ApiError("VALIDATION_ERROR", "تأكيد كلمة المرور غير مطابق.")
        if data["new_password"] == data["current_password"]:
            raise ApiError("VALIDATION_ERROR", "اختر كلمة مرور جديدة.")
        with transaction.atomic():
            account = User.objects.select_for_update().get(pk=request.user.pk)
            if not account.check_password(data["current_password"]):
                raise ApiError("INVALID_CURRENT_PASSWORD", "كلمة المرور الحالية غير صحيحة.")
            try:
                validate_password(data["new_password"], user=account)
            except ValidationError as exc:
                raise ApiError(
                    "VALIDATION_ERROR",
                    "كلمة المرور لا تستوفي شروط الأمان.",
                    details={"new_password": exc.messages},
                ) from exc
            account.set_password(data["new_password"])
            account.save(update_fields=["password", "updated_at"])
            record_event("PARENT_PASSWORD_CHANGED", actor=account, request=request)
        update_session_auth_hash(request, account)
        return Response({"message": "تم تغيير كلمة المرور وإنهاء الجلسات الأخرى."})


def staff_stats(school):
    from parents.models import ParentExcuseRequest
    from students.models import Student

    relations = GuardianStudentRelation.objects.filter(school=school)
    active = relations.filter(status="ACTIVE")
    registered_students = active.values("student_id").distinct().count()
    all_students = Student.objects.filter(school=school, status="ACTIVE").count()
    registrations = GuardianRegistrationRequest.objects.filter(school=school)
    avg = registrations.exclude(reviewed_at=None).aggregate(
        average=Avg(F("reviewed_at") - F("created_at")),
    )["average"]
    return {
        "registered_parents": active.values("user_id").distinct().count(),
        "linked_students": registered_students,
        "student_count": all_students,
        "coverage_percent": round(100 * registered_students / all_students, 1)
        if all_students
        else 0,
        "pending_registrations": registrations.filter(status__in=["PENDING", "NEEDS_INFO"]).count(),
        "relations_needing_review": relations.filter(status="SUSPENDED_CONTACT_REVIEW").count(),
        "unactivated_accounts": registrations.filter(status="APPROVED").count(),
        "average_processing_seconds": round(avg.total_seconds()) if avg else 0,
        "pending_excuses": ParentExcuseRequest.objects.filter(
            school=school, status__in=["PENDING", "NEEDS_INFO"]
        ).count(),
    }


class ParentSettingsView(ParentStaffView):
    write_roles = (SchoolRole.SCHOOL_MANAGER,)
    serializer_class = SettingsSerializer

    def _payload(self, school):
        config = ParentRegistrationConfig.objects.filter(school=school).first()
        return {
            "enabled": config.enabled if config else False,
            "registration_url": services.portal_url(f"/parent/register/{config.token}")
            if config
            else None,
            "stats": staff_stats(school),
        }

    @extend_schema(responses=output.ParentSettingsResultSerializer)
    def get(self, request):
        return Response(self._payload(request.school))

    @extend_schema(request=SettingsSerializer, responses=output.ParentSettingsResultSerializer)
    def patch(self, request):
        serializer = SettingsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.portal_url("/parent")
        config, _ = ParentRegistrationConfig.objects.get_or_create(school=request.school)
        config.enabled = serializer.validated_data["enabled"]
        config.save(update_fields=["enabled", "updated_at"])
        record_event(
            "PARENT_REGISTRATION_SETTINGS",
            school=request.school,
            request=request,
            metadata={"enabled": config.enabled},
        )
        return Response(self._payload(request.school))


class StaffRegistrationListView(ParentStaffView):
    @extend_schema(
        operation_id="staff_parent_registrations_list", responses=output.RegistrationPageSerializer
    )
    def get(self, request):
        queryset = GuardianRegistrationRequest.objects.filter(school=request.school).order_by(
            "-created_at"
        )
        if request.query_params.get("status"):
            queryset = queryset.filter(status=request.query_params["status"])
        page = DefaultPagination()
        result = page.paginate_queryset(queryset, request, view=self)
        return page.get_paginated_response([services.registration_payload(item) for item in result])


class StaffRegistrationView(ParentStaffView):
    @extend_schema(responses=output.RegistrationReviewSerializer)
    def get(self, request, request_id):
        return Response(services.registration_review(school=request.school, request_id=request_id))


class StaffRegistrationDecisionView(ParentStaffView):
    serializer_class = RegistrationDecisionSerializer

    @extend_schema(
        request=RegistrationDecisionSerializer, responses=output.ActivationDeliverySerializer
    )
    def post(self, request, request_id):
        serializer = RegistrationDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if serializer.validated_data["decision"] == "APPROVE":
            services.portal_url("/parent/activate")
        return Response(
            services.decide_registration(
                school=request.school,
                membership=request.membership,
                request_id=request_id,
                data=serializer.validated_data,
                request=request,
            )
        )


class ActivationReissueSerializer(serializers.Serializer):
    delivery = serializers.ChoiceField(choices=["EMAIL", "SMS", "MANUAL"], default="EMAIL")
    verification_note = serializers.CharField(min_length=10, max_length=600)


class StaffActivationReissueView(ParentStaffView):
    serializer_class = ActivationReissueSerializer

    @extend_schema(
        request=ActivationReissueSerializer, responses=output.ActivationDeliverySerializer
    )
    def post(self, request, request_id):
        serializer = ActivationReissueSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(
            services.reissue_activation(
                school=request.school,
                membership=request.membership,
                request_id=request_id,
                data=serializer.validated_data,
                request=request,
            )
        )


class StaffRelationsView(ParentStaffView):
    @extend_schema(responses=output.StaffRelationsSerializer)
    def get(self, request):
        queryset = (
            GuardianStudentRelation.objects.filter(school=request.school)
            .select_related("student", "user")
            .order_by("-created_at")
        )
        if request.query_params.get("status"):
            queryset = queryset.filter(status=request.query_params["status"])
        page = DefaultPagination()
        result = page.paginate_queryset(queryset, request, view=self)
        from accounts.mobile import mask_mobile

        return page.get_paginated_response(
            [
                {
                    "id": r.id,
                    "student_id": r.student_id,
                    "student_name": r.student.full_name,
                    "parent_name": r.user.display_name,
                    "mobile_masked": mask_mobile(r.user.mobile),
                    "status": r.status,
                    "relationship_type": r.relationship_type,
                    "contact_bound": r.contact_bound,
                    "contact_revision": r.contact_revision,
                    "approval_revision": r.approval_revision,
                    "suspension_reason": r.suspension_reason,
                }
                for r in result
            ]
        )


class StaffRelationDecisionView(ParentStaffView):
    serializer_class = RelationDecisionSerializer

    @extend_schema(
        request=RelationDecisionSerializer, responses=output.RelationDecisionResultSerializer
    )
    def post(self, request, relation_id):
        serializer = RelationDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(
            services.decide_relation(
                school=request.school,
                membership=request.membership,
                relation_id=relation_id,
                data=serializer.validated_data,
                request=request,
            )
        )
