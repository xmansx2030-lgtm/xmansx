"""واجهات لوحة المنصة (م16) — بيانات تشغيلية للمستأجرين، بلا أي بيان طالب.

كل ما هنا محمي بـ PlatformAdminRequired: مدير المدرسة والوكيل والمرشد والمعلم
يُرفضون جميعًا (بند 124).
"""

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import (
    BigIntegerField,
    Count,
    IntegerField,
    OuterRef,
    Prefetch,
    Q,
    Subquery,
    Sum,
    Value,
)
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from django.utils import timezone as dj_timezone
from rest_framework import serializers, status
from rest_framework.request import Request
from rest_framework.response import Response

from accounts.mobile import normalize_mobile
from audit.models import AuditAction
from audit.services import record_event
from common.pagination import DefaultPagination
from devices.models import AttendanceDevice
from documents.models import GeneratedDocument
from excuses.models import AbsenceExcuseAttachment
from memberships.models import MembershipStatus, SchoolMembership, SchoolRole
from schools.models import School, SchoolStatus, SchoolType
from students.models import Student, StudentStatus
from subscriptions.access import effective_status, live_subscription, subscription_state
from subscriptions.entitlements import get_school_entitlements
from subscriptions.models import (
    NUMERIC_ENTITLEMENTS,
    SaaSPlan,
    SchoolSubscription,
    SubscriptionStatus,
)
from subscriptions.permissions import PlatformAPIView
from subscriptions.services import plans as plan_service
from subscriptions.services import provisioning as provisioning_service
from subscriptions.services import school_accounts as school_account_service
from subscriptions.services import subscriptions as subscription_service
from subscriptions.usage import get_school_usage

EXPIRING_SOON_DAYS = 30


def _count_for_school(model, **filters):
    query = (
        model.objects.filter(school_id=OuterRef("pk"), **filters)
        .order_by()
        .values("school_id")
        .annotate(total=Count("id"))
        .values("total")[:1]
    )
    return Coalesce(
        Subquery(query, output_field=IntegerField()),
        Value(0),
        output_field=IntegerField(),
    )


def _sum_for_school(model, field: str):
    query = (
        model.objects.filter(school_id=OuterRef("pk"))
        .order_by()
        .values("school_id")
        .annotate(total=Sum(field))
        .values("total")[:1]
    )
    return Coalesce(
        Subquery(query, output_field=BigIntegerField()),
        Value(0),
        output_field=BigIntegerField(),
    )


def _platform_school_queryset():
    subscriptions = (
        SchoolSubscription.objects.select_related("plan")
        .prefetch_related("entitlements")
        .order_by("-starts_at", "-id")
    )
    managers = (
        SchoolMembership.objects.filter(
            status=MembershipStatus.ACTIVE,
            roles__role=SchoolRole.SCHOOL_MANAGER,
        )
        .select_related("user")
        .distinct()
    )
    return (
        School.objects.annotate(
            platform_active_students=_count_for_school(
                Student, status=StudentStatus.ACTIVE
            ),
            platform_active_staff=_count_for_school(
                SchoolMembership, status=MembershipStatus.ACTIVE
            ),
            platform_active_devices=_count_for_school(
                AttendanceDevice, is_active=True
            ),
            platform_attachment_bytes=_sum_for_school(
                AbsenceExcuseAttachment, "size_bytes"
            ),
            platform_document_bytes=_sum_for_school(GeneratedDocument, "size_bytes"),
        )
        .prefetch_related(
            Prefetch("subscriptions", queryset=subscriptions, to_attr="prefetched_subscriptions"),
            Prefetch("memberships", queryset=managers, to_attr="platform_managers"),
        )
        .order_by("name")
    )


def _usage_entry(used: int, limit: int | None) -> dict:
    over_limit = limit is not None and used > limit
    return {
        "used": used,
        "limit": limit,
        "over_limit": over_limit,
        "near_limit": (
            limit is not None and limit > 0 and not over_limit and used / limit >= 0.8
        ),
        "remaining": None if limit is None else max(limit - used, 0),
    }


def _plan_payload(plan: SaaSPlan) -> dict:
    return {
        "id": plan.id,
        "code": plan.code,
        "name_ar": plan.name_ar,
        "name_en": plan.name_en,
        "description": plan.description,
        "is_active": plan.is_active,
        "is_public": plan.is_public,
        "billing_period": plan.billing_period,
        "price_amount": str(plan.price_amount),
        "currency": plan.currency,
        "trial_days_default": plan.trial_days_default,
        "entitlements": plan_service.plan_entitlements(plan),
    }


class PlanListView(PlatformAPIView):
    class InputSerializer(serializers.Serializer):
        code = serializers.SlugField(max_length=40)
        name_ar = serializers.CharField(max_length=100)
        name_en = serializers.CharField(max_length=100, required=False, allow_blank=True)
        description = serializers.CharField(
            max_length=1000, required=False, allow_blank=True
        )
        billing_period = serializers.CharField(max_length=12, required=False)
        price_amount = serializers.DecimalField(
            max_digits=10, decimal_places=2, required=False
        )
        currency = serializers.CharField(max_length=3, required=False)
        trial_days_default = serializers.IntegerField(min_value=0, required=False)
        is_public = serializers.BooleanField(required=False)
        entitlements = serializers.DictField(required=False)

    def get(self, request: Request) -> Response:
        plans = SaaSPlan.objects.all()
        return Response([_plan_payload(plan) for plan in plans])

    def post(self, request: Request) -> Response:
        serializer = self.InputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        plan = plan_service.create_plan(
            actor=request.user,
            request=request,
            entitlements=data.pop("entitlements", None),
            **data,
        )
        return Response(_plan_payload(plan), status=status.HTTP_201_CREATED)


class PlanDetailView(PlatformAPIView):
    class PatchSerializer(serializers.Serializer):
        name_ar = serializers.CharField(max_length=100, required=False)
        name_en = serializers.CharField(max_length=100, required=False, allow_blank=True)
        description = serializers.CharField(
            max_length=1000, required=False, allow_blank=True
        )
        billing_period = serializers.CharField(max_length=12, required=False)
        price_amount = serializers.DecimalField(
            max_digits=10, decimal_places=2, required=False
        )
        currency = serializers.CharField(max_length=3, required=False)
        trial_days_default = serializers.IntegerField(min_value=0, required=False)
        is_public = serializers.BooleanField(required=False)
        is_active = serializers.BooleanField(required=False)
        entitlements = serializers.DictField(required=False)

    def get(self, request: Request, plan_id: int) -> Response:
        return Response(_plan_payload(get_object_or_404(SaaSPlan, id=plan_id)))

    def patch(self, request: Request, plan_id: int) -> Response:
        plan = get_object_or_404(SaaSPlan, id=plan_id)
        serializer = self.PatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        plan = plan_service.update_plan(
            plan=plan,
            actor=request.user,
            request=request,
            entitlements=data.pop("entitlements", None),
            **data,
        )
        return Response(_plan_payload(plan))

    def delete(self, request: Request, plan_id: int) -> Response:
        """لا حذف نهائي — التعطيل يحفظ العقود التاريخية (بند 103)."""
        plan = get_object_or_404(SaaSPlan, id=plan_id)
        plan_service.disable_plan(plan=plan, actor=request.user, request=request)
        return Response(_plan_payload(plan))


def _school_row(school: School) -> dict:
    prefetched = getattr(school, "prefetched_subscriptions", None)
    subscription = prefetched[0] if prefetched is not None and prefetched else None
    if prefetched is None:
        subscription = live_subscription(school)
    status_value = effective_status(subscription)
    managers = getattr(school, "platform_managers", None)
    if managers is None:
        managers = list(
            SchoolMembership.objects.filter(
                school=school,
                status=MembershipStatus.ACTIVE,
                roles__role=SchoolRole.SCHOOL_MANAGER,
            )
            .select_related("user")
            .distinct()[:1]
        )
    manager = managers[0] if managers else None

    if hasattr(school, "platform_active_students"):
        entitlements = {
            row.key: row.numeric_value
            for row in (subscription.entitlements.all() if subscription else [])
        }
        storage_bytes = int(school.platform_attachment_bytes) + int(
            school.platform_document_bytes
        )
        storage_limit_gb = entitlements.get("MAX_STORAGE_GB")
        storage_limit = (
            None if storage_limit_gb is None else storage_limit_gb * 1024**3
        )
        usage = {
            "students": _usage_entry(
                school.platform_active_students, entitlements.get("MAX_STUDENTS")
            ),
            "staff": _usage_entry(
                school.platform_active_staff, entitlements.get("MAX_STAFF")
            ),
            "devices": _usage_entry(
                school.platform_active_devices, entitlements.get("MAX_DEVICES")
            ),
            "storage": {
                **_usage_entry(storage_bytes, storage_limit),
                "used_gb": round(storage_bytes / 1024**3, 3),
                "limit_gb": storage_limit_gb,
            },
        }
    else:
        usage = get_school_usage(school)

    access_ends_at = None
    if subscription is not None:
        access_ends_at = (
            subscription.grace_ends_at
            if status_value == SubscriptionStatus.GRACE_PERIOD
            and subscription.grace_ends_at is not None
            else subscription.ends_at
        )
    return {
        "id": school.id,
        "name": school.name,
        "slug": school.slug,
        "school_type": school.school_type,
        "school_status": school.status,
        "subscription_status": status_value,
        "plan": subscription.plan.code if subscription else None,
        "plan_name": subscription.plan.name_ar if subscription else None,
        "starts_at": subscription.starts_at.isoformat() if subscription else None,
        "ends_at": subscription.ends_at.isoformat() if subscription else None,
        "manager": (
            {"id": manager.id, "name": manager.user.display_name} if manager else None
        ),
        "usage": usage,
        "_access_ends_at": access_ends_at,
    }


class SchoolListView(PlatformAPIView):
    class InputSerializer(serializers.Serializer):
        school_name = serializers.CharField(max_length=200)
        school_type = serializers.ChoiceField(choices=SchoolType.choices)
        manager_name = serializers.CharField(max_length=150)
        manager_mobile = serializers.CharField(max_length=20)
        plan_id = serializers.IntegerField(required=False, allow_null=True)
        subscription_mode = serializers.ChoiceField(
            choices=["TRIAL", "ACTIVE"], required=False, default="TRIAL"
        )
        trial_days = serializers.IntegerField(required=False, allow_null=True)
        months = serializers.IntegerField(required=False, default=12)

    def get(self, request: Request) -> Response:
        schools = _platform_school_queryset()
        search = request.query_params.get("search", "").strip()
        if search:
            schools = schools.filter(Q(name__icontains=search) | Q(slug__icontains=search))

        status_filter = request.query_params.get("status", "").strip()
        plan_filter = request.query_params.get("plan", "").strip()
        trial_filter = request.query_params.get("trial", "").lower() in {"1", "true", "yes"}
        expires_filter = request.query_params.get("expires_soon", "").lower() in {
            "1", "true", "yes",
        }
        over_limit_filter = request.query_params.get("over_limit", "").lower() in {
            "1", "true", "yes",
        }
        rows = [_school_row(school) for school in schools]
        if status_filter:
            rows = [row for row in rows if row["subscription_status"] == status_filter]
        if plan_filter:
            rows = [row for row in rows if row["plan"] == plan_filter]
        if trial_filter:
            rows = [row for row in rows if row["subscription_status"] == SubscriptionStatus.TRIAL]
        if expires_filter:
            soon = dj_timezone.now() + dj_timezone.timedelta(days=EXPIRING_SOON_DAYS)
            rows = [
                row
                for row in rows
                if row["_access_ends_at"] is not None
                and dj_timezone.now() <= row["_access_ends_at"] <= soon
            ]
        if over_limit_filter:
            rows = [
                row
                for row in rows
                if any(entry["over_limit"] for entry in row["usage"].values())
            ]

        for row in rows:
            row.pop("_access_ends_at", None)

        paginator = DefaultPagination()
        page = paginator.paginate_queryset(rows, request)
        return paginator.get_paginated_response(page)

    def post(self, request: Request) -> Response:
        serializer = self.InputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = provisioning_service.create_school(
            actor=request.user, request=request, **serializer.validated_data
        )
        school = result["school"]
        row = _school_row(school)
        row.pop("_access_ends_at", None)
        return Response(
            {
                **row,
                "manager_membership_id": result["manager_membership"].id,
                # يُعرض مرة واحدة فقط ولا يُخزن نصًا في أي مكان
                "temporary_password": result["temporary_password"],
            },
            status=status.HTTP_201_CREATED,
        )


class SchoolDetailView(PlatformAPIView):
    class PatchSerializer(serializers.Serializer):
        name = serializers.CharField(max_length=200, required=False)
        school_status = serializers.ChoiceField(
            choices=SchoolStatus.choices, required=False
        )
        school_type = serializers.ChoiceField(choices=SchoolType.choices, required=False)

        def validate_name(self, value):
            value = value.strip()
            if len(value) < 2:
                raise serializers.ValidationError("أدخل اسم المدرسة كاملًا.")
            return value

    def get(self, request: Request, school_id: int) -> Response:
        """بيانات تشغيلية وحسابات المديرين فقط — لا بيانات طلاب (بند 98)."""
        school = get_object_or_404(_platform_school_queryset(), id=school_id)
        row = _school_row(school)
        row.pop("_access_ends_at", None)
        return Response(
            {
                **row,
                "created_at": school.created_at.isoformat(),
                "updated_at": school.updated_at.isoformat(),
                "managers": [
                    school_account_service.manager_payload(membership)
                    for membership in school_account_service.manager_memberships(school)
                ],
                "subscription": subscription_state(school),
                "usage": row["usage"],
                "entitlements": get_school_entitlements(school),
            }
        )

    def patch(self, request: Request, school_id: int) -> Response:
        school = get_object_or_404(School, id=school_id)
        serializer = self.PatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        changed = []
        for field, value in serializer.validated_data.items():
            model_field = "status" if field == "school_status" else field
            if getattr(school, model_field) != value:
                setattr(school, model_field, value)
                changed.append(field)
        if changed:
            school.save()
            record_event(
                AuditAction.PLATFORM_SCHOOL_UPDATED,
                request=request,
                actor=request.user,
                school=school,
                target_type="School",
                target_id=school.id,
                metadata={"changed_fields": changed},
            )
        return self.get(request, school_id)


class SchoolManagersView(PlatformAPIView):
    class InputSerializer(serializers.Serializer):
        name = serializers.CharField(max_length=150)
        mobile = serializers.CharField(max_length=20)

        def validate_mobile(self, value):
            try:
                return normalize_mobile(value)
            except DjangoValidationError as exc:
                raise serializers.ValidationError(exc.messages[0]) from exc

    def get(self, request: Request, school_id: int) -> Response:
        school = get_object_or_404(School, id=school_id)
        return Response(
            [
                school_account_service.manager_payload(membership)
                for membership in school_account_service.manager_memberships(school)
            ]
        )

    def post(self, request: Request, school_id: int) -> Response:
        school = get_object_or_404(School, id=school_id)
        serializer = self.InputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = school_account_service.add_manager(
            school=school,
            actor=request.user,
            request=request,
            **serializer.validated_data,
        )
        return Response(result, status=status.HTTP_201_CREATED)


class SchoolManagerDetailView(PlatformAPIView):
    class PatchSerializer(serializers.Serializer):
        name = serializers.CharField(max_length=150, required=False)
        mobile = serializers.CharField(max_length=20, required=False)

        def validate_mobile(self, value):
            try:
                return normalize_mobile(value)
            except DjangoValidationError as exc:
                raise serializers.ValidationError(exc.messages[0]) from exc

        def validate(self, attrs):
            if not attrs:
                raise serializers.ValidationError("أرسل حقلًا واحدًا على الأقل.")
            return attrs

    def patch(self, request: Request, school_id: int, membership_id: int) -> Response:
        school = get_object_or_404(School, id=school_id)
        membership = school_account_service.get_manager(school, membership_id)
        serializer = self.PatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        membership = school_account_service.update_manager(
            membership=membership,
            actor=request.user,
            request=request,
            name=serializer.validated_data.get("name"),
            mobile=serializer.validated_data.get("mobile"),
        )
        return Response(school_account_service.manager_payload(membership))


class SchoolManagerActionView(PlatformAPIView):
    def post(
        self, request: Request, school_id: int, membership_id: int, action: str
    ) -> Response:
        school = get_object_or_404(School, id=school_id)
        membership = school_account_service.get_manager(school, membership_id)
        if action == "reset-password":
            return Response(
                school_account_service.reset_manager_password(
                    membership=membership, actor=request.user, request=request
                )
            )

        from staff.services import management as staff_management

        if action == "suspend":
            staff_management.suspend(
                membership=membership, actor=request.user, request=request
            )
        elif action == "reactivate":
            staff_management.reactivate(
                membership=membership, actor=request.user, request=request
            )
        else:
            return Response(
                {"code": "NOT_FOUND", "message": "إجراء غير معروف."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(
            school_account_service.manager_payload(
                school_account_service.get_manager(school, membership.id)
            )
        )


class SchoolUsageView(PlatformAPIView):
    def get(self, request: Request, school_id: int) -> Response:
        school = get_object_or_404(School, id=school_id)
        return Response(get_school_usage(school))


def _subscription_payload(subscription: SchoolSubscription) -> dict:
    return {
        "id": subscription.id,
        "plan": subscription.plan.code,
        "plan_name": subscription.plan.name_ar,
        "status": subscription.status,
        "effective_status": effective_status(subscription),
        "starts_at": subscription.starts_at.isoformat(),
        "ends_at": subscription.ends_at.isoformat(),
        "trial_ends_at": (
            subscription.trial_ends_at.isoformat() if subscription.trial_ends_at else None
        ),
        "grace_ends_at": (
            subscription.grace_ends_at.isoformat() if subscription.grace_ends_at else None
        ),
        "suspension_reason": subscription.suspension_reason,
        "cancel_reason": subscription.cancel_reason,
    }


class SubscriptionView(PlatformAPIView):
    def get(self, request: Request, school_id: int) -> Response:
        school = get_object_or_404(School, id=school_id)
        subscriptions = SchoolSubscription.objects.filter(school=school).select_related("plan")
        current = live_subscription(school)
        return Response(
            {
                "current": _subscription_payload(current) if current else None,
                "history": [_subscription_payload(row) for row in subscriptions],
            }
        )


class SubscriptionActionView(PlatformAPIView):
    """كل انتقال إجراء صريح — لا PATCH يغيّر الحالة مباشرة (بند 147)."""

    class ActionSerializer(serializers.Serializer):
        plan_id = serializers.IntegerField(required=False)
        trial_days = serializers.IntegerField(required=False, allow_null=True)
        days = serializers.IntegerField(required=False)
        months = serializers.IntegerField(required=False, default=12)
        reason = serializers.CharField(max_length=300, required=False, allow_blank=True)

    def post(self, request: Request, school_id: int, action: str) -> Response:
        school = get_object_or_404(School, id=school_id)
        serializer = self.ActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        actor = request.user
        common = {"school": school, "actor": actor, "request": request}

        if action == "start-trial":
            subscription = subscription_service.start_trial(
                plan_id=data["plan_id"], trial_days=data.get("trial_days"), **common
            )
        elif action == "extend-trial":
            subscription = subscription_service.extend_trial(
                extra_days=data["days"], reason=data.get("reason", ""), **common
            )
        elif action == "activate":
            subscription = subscription_service.activate(
                plan_id=data["plan_id"], months=data.get("months", 12), **common
            )
        elif action == "change-plan":
            subscription = subscription_service.change_plan(
                plan_id=data["plan_id"], reason=data.get("reason", ""), **common
            )
        elif action == "extend":
            subscription = subscription_service.extend(
                extra_days=data["days"], reason=data.get("reason", ""), **common
            )
        elif action == "suspend":
            subscription = subscription_service.suspend(
                reason=data.get("reason", ""), **common
            )
        elif action == "reactivate":
            subscription = subscription_service.reactivate(
                reason=data.get("reason", ""), **common
            )
        elif action == "cancel":
            subscription = subscription_service.cancel(reason=data.get("reason", ""), **common)
        else:
            return Response(
                {"code": "NOT_FOUND", "message": "إجراء غير معروف."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(_subscription_payload(subscription))


class SubscriptionEventsView(PlatformAPIView):
    def get(self, request: Request, school_id: int) -> Response:
        school = get_object_or_404(School, id=school_id)
        events = school.subscription_events.select_related("actor")[:100]
        return Response(
            [
                {
                    "id": event.id,
                    "event_type": event.event_type,
                    "reason": event.reason,
                    "metadata": event.metadata,
                    "created_at": event.created_at.isoformat(),
                }
                for event in events
            ]
        )


class PlanChangePreviewView(PlatformAPIView):
    """معاينة أثر تغيير الباقة قبل التنفيذ — لا تغيير صامت (بنود 85-87)."""

    def get(self, request: Request, school_id: int) -> Response:
        school = get_object_or_404(School, id=school_id)
        plan = get_object_or_404(SaaSPlan, id=request.query_params.get("plan_id"))
        usage = get_school_usage(school)
        target = plan_service.plan_entitlements(plan)
        rows = {}
        for key, usage_key in (
            ("MAX_STUDENTS", "students"),
            ("MAX_STAFF", "staff"),
            ("MAX_DEVICES", "devices"),
        ):
            limit = target.get(key)
            used = usage[usage_key]["used"]
            rows[usage_key] = {
                "used": used,
                "new_limit": limit,
                "over_limit": limit is not None and used > limit,
            }
        storage_limit = target.get("MAX_STORAGE_GB")
        rows["storage"] = {
            "used_gb": usage["storage"]["used_gb"],
            "new_limit_gb": storage_limit,
            "over_limit": (
                storage_limit is not None and usage["storage"]["used_gb"] > storage_limit
            ),
        }
        return Response(
            {
                "plan": {"id": plan.id, "code": plan.code, "name": plan.name_ar},
                "impact": rows,
                # التخفيض لا يحذف شيئًا — يمنع الإضافة فقط
                "deletes_data": False,
            }
        )


class PlatformOverviewView(PlatformAPIView):
    def get(self, request: Request) -> Response:
        now = dj_timezone.now()
        soon = now + dj_timezone.timedelta(days=EXPIRING_SOON_DAYS)
        current = list(
            SchoolSubscription.objects.select_related("school", "plan")
            .order_by("school_id", "-starts_at", "-id")
            .distinct("school_id")
        )
        totals = {
            "trial": 0,
            "active": 0,
            "grace": 0,
            "expired": 0,
            "suspended": 0,
            "cancelled": 0,
        }
        expiring = []
        status_keys = {
            SubscriptionStatus.TRIAL: "trial",
            SubscriptionStatus.ACTIVE: "active",
            SubscriptionStatus.GRACE_PERIOD: "grace",
            SubscriptionStatus.EXPIRED: "expired",
            SubscriptionStatus.SUSPENDED: "suspended",
            SubscriptionStatus.CANCELLED: "cancelled",
        }
        for row in current:
            status_value = effective_status(row, now=now)
            totals[status_keys[status_value]] += 1
            access_end = (
                row.grace_ends_at
                if status_value == SubscriptionStatus.GRACE_PERIOD and row.grace_ends_at
                else row.ends_at
            )
            if status_value in {
                SubscriptionStatus.TRIAL,
                SubscriptionStatus.ACTIVE,
                SubscriptionStatus.GRACE_PERIOD,
            } and now <= access_end <= soon:
                expiring.append((access_end, row))
        expiring.sort(key=lambda value: value[0])
        return Response(
            {
                "schools_total": School.objects.count(),
                "subscriptions": totals,
                "usage_totals": {
                    "active_students": Student.objects.filter(
                        status=StudentStatus.ACTIVE
                    ).count(),
                    "active_staff": SchoolMembership.objects.filter(
                        status=MembershipStatus.ACTIVE
                    ).count(),
                    "active_devices": AttendanceDevice.objects.filter(is_active=True).count(),
                },
                "expiring_soon": [
                    {
                        "school_id": row.school_id,
                        "school_name": row.school.name,
                        "plan": row.plan.code,
                        "ends_at": access_end.isoformat(),
                        "days_remaining": max((access_end - now).days, 0),
                    }
                    for access_end, row in expiring[:20]
                ],
            }
        )


class EntitlementOverrideView(PlatformAPIView):
    class InputSerializer(serializers.Serializer):
        key = serializers.CharField(max_length=32)
        numeric_value = serializers.IntegerField(required=False, allow_null=True)
        is_enabled = serializers.BooleanField(required=False, default=True)

    def post(self, request: Request, school_id: int) -> Response:
        school = get_object_or_404(School, id=school_id)
        serializer = self.InputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        key = data["key"]
        subscription_service.set_entitlement_override(
            school=school,
            key=key,
            numeric_value=data.get("numeric_value") if key in NUMERIC_ENTITLEMENTS else None,
            is_enabled=data.get("is_enabled", True),
            actor=request.user,
            request=request,
        )
        return Response(get_school_entitlements(school))
