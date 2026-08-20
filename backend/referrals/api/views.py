"""‏API الإحالات — المدرسة من request.school حصرًا (بند 74).

الأدوار: المدير/الوكيل يديران؛ المرشد يستلم المعيّن له وغير المعيّن؛ المعلم ينشئ
ويرى ما أنشأه أو ساهم فيه فقط. كل عملية على إحالة تمر بفحص «هل يراها أصلًا؟»
قبل فحص «هل يملك الإجراء؟» — إحالة مدرسة أخرى تعيد 404 لا 403 (بند 82).
"""

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response

from common.errors import ApiError
from common.pagination import DefaultPagination
from memberships.api_base import SchoolScopedAPIView
from memberships.models import SchoolRole
from referrals import selectors
from referrals.api.serializers import (
    AssignSerializer,
    CloseSerializer,
    ContributionCreateSerializer,
    OpenCaseContributionSerializer,
    ReferralCreateSerializer,
    serialize_contribution,
    serialize_counselor,
    serialize_referral_detail,
    serialize_referral_row,
)
from referrals.models import (
    CATEGORIES_BY_SOURCE,
    REASONS_BY_CATEGORY,
    ReferralCategory,
    ReferralObservationType,
    ReferralReason,
    StudentReferral,
)
from referrals.services import referrals as referral_service
from referrals.services.snapshots import attendance_metrics
from students.models import Student

MANAGE_ROLES = (SchoolRole.SCHOOL_MANAGER, SchoolRole.VICE_PRINCIPAL)
# كل الأدوار المدرسية تصل للقائمة — النطاق نفسه هو ما يحمي الخصوصية
ALL_SCHOOL_ROLES = (
    SchoolRole.SCHOOL_MANAGER,
    SchoolRole.VICE_PRINCIPAL,
    SchoolRole.COUNSELOR,
    SchoolRole.TEACHER,
)

def _not_found() -> ApiError:
    """استثناء جديد لكل طلب — كائن واحد مشترك يراكم traceback عبر الطلبات."""
    return ApiError("REFERRAL_NOT_FOUND", "الإحالة غير موجودة.", status_code=404)

_DETAIL_RELATIONS = (
    "student",
    "source_warning",
    "created_by_membership__user",
    "created_by_membership__staff_profile",
    "assigned_counselor_membership__user",
    "assigned_counselor_membership__staff_profile",
    "closed_by_membership__user",
    "closed_by_membership__staff_profile",
)


def _get_visible_referral(request, referral_id: int, *, for_detail=False) -> StudentReferral:
    queryset = StudentReferral.objects.filter(school=request.school)
    if for_detail:
        queryset = queryset.select_related(*_DETAIL_RELATIONS).prefetch_related(
            "contributions__created_by_membership__user",
            "contributions__created_by_membership__staff_profile",
            "events__actor_membership__user",
            "events__actor_membership__staff_profile",
            "student__enrollments__grade",
            "student__enrollments__section",
        )
    referral = queryset.filter(id=referral_id).first()
    if referral is None:
        raise _not_found()
    if not selectors.can_view_referral(
        referral=referral, membership=request.membership, roles=request.school_roles
    ):
        raise _not_found()  # لا تسريب وجود حالة لا يملك رؤيتها
    return referral


def _detail_payload(referral: StudentReferral, request) -> dict:
    """التفاصيل الكاملة: اللقطة الثابتة + المؤشرات الحالية لفئة المواظبة (بند 59)."""
    current = (
        attendance_metrics(school=referral.school, student=referral.student)
        if referral.category == ReferralCategory.ATTENDANCE
        else None
    )
    return serialize_referral_detail(
        referral,
        current_metrics=current,
        membership=request.membership,
        roles=request.school_roles,
    )




def _require_manage(request) -> None:
    if not set(request.school_roles or []) & set(MANAGE_ROLES):
        raise ApiError(
            "REFERRAL_PERMISSION_DENIED",
            "هذا الإجراء من صلاحية المدير أو الوكيل.",
            status_code=403,
        )


class ReferralListCreateView(SchoolScopedAPIView):
    read_roles = ALL_SCHOOL_ROLES
    write_roles = ALL_SCHOOL_ROLES  # المعلم ينشئ أيضًا؛ الفئات تُقيَّد في الخدمة

    @extend_schema(responses=None)
    def get(self, request):
        queryset = selectors.apply_filters(
            selectors.visible_referrals(
                school=request.school,
                membership=request.membership,
                roles=request.school_roles,
            ),
            request.query_params,
        ).order_by("-created_at", "-id")
        paginator = DefaultPagination()
        page = paginator.paginate_queryset(queryset, request)
        return paginator.get_paginated_response(
            [serialize_referral_row(referral) for referral in page]
        )

    @extend_schema(request=ReferralCreateSerializer, responses=None)
    def post(self, request):
        serializer = ReferralCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        student = Student.objects.filter(
            school=request.school, id=data["student_id"]
        ).first()
        if student is None:
            raise ApiError("NOT_FOUND", "الطالب غير موجود.", status_code=404)

        warning = None
        if data.get("source_warning_id"):
            from student_warnings.models import StudentWarning

            warning = StudentWarning.objects.filter(
                school=request.school, id=data["source_warning_id"]
            ).first()
            if warning is None:
                raise ApiError("NOT_FOUND", "الإنذار غير موجود.", status_code=404)

        referral = referral_service.create_referral(
            school=request.school,
            membership=request.membership,
            roles=request.school_roles,
            student=student,
            category=data["category"],
            reason_code=data["reason_code"],
            description=data["description"],
            priority=data["priority"],
            source_warning=warning,
            assigned_counselor_id=data.get("assigned_counselor_id"),
            allow_duplicate=data["allow_duplicate"],
            request=request,
        )
        return Response(
            _detail_payload(_get_visible_referral(request, referral.id, for_detail=True), request),
            status=201,
        )


class MyReferralsView(SchoolScopedAPIView):
    """«إحالاتي» — ما أنشأه المستخدم أو ساهم فيه، لأي دور."""

    read_roles = ALL_SCHOOL_ROLES
    write_roles = ALL_SCHOOL_ROLES

    @extend_schema(responses=None)
    def get(self, request):
        queryset = selectors.apply_filters(
            selectors.teacher_referrals(
                school=request.school, membership=request.membership
            ),
            request.query_params,
        ).order_by("-created_at", "-id")
        paginator = DefaultPagination()
        page = paginator.paginate_queryset(queryset, request)
        return paginator.get_paginated_response(
            [serialize_referral_row(referral) for referral in page]
        )


class ReferralKpisView(SchoolScopedAPIView):
    read_roles = ALL_SCHOOL_ROLES
    write_roles = MANAGE_ROLES

    @extend_schema(responses=None)
    def get(self, request):
        return Response(
            selectors.referral_kpis(
                school=request.school,
                membership=request.membership,
                roles=request.school_roles,
            )
        )


class ReferralOptionsView(SchoolScopedAPIView):
    """الفئات والأسباب المسموحة لدور المستخدم — الواجهة تبني القوائم منها."""

    read_roles = ALL_SCHOOL_ROLES
    write_roles = ALL_SCHOOL_ROLES

    @extend_schema(responses=None)
    def get(self, request):
        source_type = referral_service.resolve_source_type(request.school_roles)
        allowed = CATEGORIES_BY_SOURCE[source_type]
        return Response(
            {
                "source_type": source_type,
                "can_assign": bool(set(request.school_roles or []) & set(MANAGE_ROLES)),
                "categories": [
                    {
                        "value": category,
                        "label": ReferralCategory(category).label,
                        "reasons": [
                            {"value": reason, "label": ReferralReason(reason).label}
                            for reason in REASONS_BY_CATEGORY[category]
                        ],
                    }
                    for category in allowed
                ],
                "observation_types": [
                    {"value": value, "label": label}
                    for value, label in ReferralObservationType.choices
                ],
            }
        )


class CounselorListView(SchoolScopedAPIView):
    """المرشدون النشطون المتاحون للتعيين — للمدير/الوكيل."""

    read_roles = MANAGE_ROLES
    write_roles = MANAGE_ROLES

    @extend_schema(responses=None)
    def get(self, request):
        counselors = list(referral_service.active_counselors(request.school))
        return Response(
            {
                "counselors": [serialize_counselor(m) for m in counselors],
                "has_counselors": bool(counselors),
            }
        )


class ReferralDetailView(SchoolScopedAPIView):
    read_roles = ALL_SCHOOL_ROLES
    write_roles = MANAGE_ROLES

    @extend_schema(responses=None)
    def get(self, request, referral_id: int):
        # المؤشرات الحالية تُقرأ لا تُحسب — والمقارنة مع اللقطة تظهر التغير
        return Response(
            _detail_payload(_get_visible_referral(request, referral_id, for_detail=True), request)
        )


class ReferralAssignView(SchoolScopedAPIView):
    read_roles = MANAGE_ROLES
    write_roles = MANAGE_ROLES

    @extend_schema(request=AssignSerializer, responses=None)
    def post(self, request, referral_id: int):
        _get_visible_referral(request, referral_id)
        _require_manage(request)
        serializer = AssignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if not referral_service.active_counselors(request.school).exists():
            raise ApiError(
                "NO_ACTIVE_COUNSELOR_AVAILABLE",
                "لا يوجد مرشد نشط في المدرسة الحالية.",
                status_code=409,
            )
        referral_service.assign_counselor(
            referral_id=referral_id,
            school=request.school,
            membership=request.membership,
            counselor_id=serializer.validated_data["counselor_membership_id"],
            request=request,
        )
        return Response(
            _detail_payload(_get_visible_referral(request, referral_id, for_detail=True), request)
        )


class ReferralAcknowledgeView(SchoolScopedAPIView):
    read_roles = (SchoolRole.COUNSELOR,)
    write_roles = (SchoolRole.COUNSELOR,)

    @extend_schema(request=None, responses=None)
    def post(self, request, referral_id: int):
        _get_visible_referral(request, referral_id)
        referral_service.acknowledge_referral(
            referral_id=referral_id,
            school=request.school,
            membership=request.membership,
            roles=request.school_roles,
            request=request,
        )
        return Response(
            _detail_payload(_get_visible_referral(request, referral_id, for_detail=True), request)
        )


class ReferralCloseView(SchoolScopedAPIView):
    read_roles = (*MANAGE_ROLES, SchoolRole.COUNSELOR)
    write_roles = (*MANAGE_ROLES, SchoolRole.COUNSELOR)

    @extend_schema(request=CloseSerializer, responses=None)
    def post(self, request, referral_id: int):
        referral = _get_visible_referral(request, referral_id)
        serializer = CloseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cancel = serializer.validated_data["cancel"]
        roles = set(request.school_roles or [])
        if cancel and not (
            roles & set(MANAGE_ROLES)
            or referral.created_by_membership_id == request.membership.id
        ):
            raise ApiError(
                "REFERRAL_PERMISSION_DENIED",
                "إلغاء الإحالة لمنشئها أو للإدارة.",
                status_code=403,
            )
        if not cancel and not (roles & {*MANAGE_ROLES, SchoolRole.COUNSELOR}):
            raise ApiError(
                "REFERRAL_PERMISSION_DENIED",
                "إغلاق الإحالة من صلاحية الإدارة أو المرشد.",
                status_code=403,
            )
        referral_service.close_referral(
            referral_id=referral_id,
            school=request.school,
            membership=request.membership,
            reason=serializer.validated_data["reason"],
            cancel=cancel,
            request=request,
        )
        return Response(
            _detail_payload(_get_visible_referral(request, referral_id, for_detail=True), request)
        )


class ReferralCancelView(SchoolScopedAPIView):
    """إلغاء المنشئ لإحالته قبل استلامها — المعلم يصحح خطأه بنفسه."""

    read_roles = ALL_SCHOOL_ROLES
    write_roles = ALL_SCHOOL_ROLES

    @extend_schema(request=CloseSerializer, responses=None)
    def post(self, request, referral_id: int):
        referral = _get_visible_referral(request, referral_id)
        serializer = CloseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        roles = set(request.school_roles or [])
        is_manager = bool(roles & set(MANAGE_ROLES))
        is_creator = referral.created_by_membership_id == request.membership.id
        if not (is_manager or is_creator):
            raise ApiError(
                "REFERRAL_PERMISSION_DENIED",
                "إلغاء الإحالة لمنشئها أو للإدارة.",
                status_code=403,
            )
        referral_service.close_referral(
            referral_id=referral_id,
            school=request.school,
            membership=request.membership,
            reason=serializer.validated_data["reason"],
            cancel=True,
            # المنشئ غير الإداري يلغي قبل الاستلام فقط
            creator_only=not is_manager,
            request=request,
        )
        return Response(
            _detail_payload(_get_visible_referral(request, referral_id, for_detail=True), request)
        )


class ReferralContributionsView(SchoolScopedAPIView):
    read_roles = ALL_SCHOOL_ROLES
    write_roles = ALL_SCHOOL_ROLES

    @extend_schema(responses=None)
    def get(self, request, referral_id: int):
        referral = _get_visible_referral(request, referral_id)
        contributions = referral.contributions.select_related(
            "created_by_membership__user", "created_by_membership__staff_profile"
        ).order_by("created_at")
        return Response(
            {"results": [serialize_contribution(c) for c in contributions]}
        )

    @extend_schema(request=ContributionCreateSerializer, responses=None)
    def post(self, request, referral_id: int):
        _get_visible_referral(request, referral_id)
        serializer = ContributionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        contribution = referral_service.add_contribution(
            referral_id=referral_id,
            school=request.school,
            membership=request.membership,
            observation_type=serializer.validated_data["observation_type"],
            notes=serializer.validated_data["notes"],
            request=request,
        )
        return Response(serialize_contribution(contribution), status=201)


class ContributeToOpenCaseView(SchoolScopedAPIView):
    """إضافة ملاحظة إلى الحالة المفتوحة لـ(طالب، فئة) — بديل التكرار (بند 33).

    الخادم هو من يحل الحالة من الطالب والفئة، فلا يمرر العميل معرف إحالة لا يراها.
    (تمرير معرف حر كان يجعل الإرسال بوابة قراءة لكل حالة مفتوحة في المدرسة.)
    """

    read_roles = ALL_SCHOOL_ROLES
    write_roles = ALL_SCHOOL_ROLES

    @extend_schema(request=OpenCaseContributionSerializer, responses=None)
    def post(self, request):
        serializer = OpenCaseContributionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        student = Student.objects.filter(
            school=request.school, id=data["student_id"]
        ).first()
        if student is None:
            raise ApiError("NOT_FOUND", "الطالب غير موجود.", status_code=404)

        # نفس قيود الإحالة: لا يضيف ملاحظة في فئة لا يملك الإحالة فيها أصلًا
        source_type = referral_service.resolve_source_type(request.school_roles)
        if data["category"] not in CATEGORIES_BY_SOURCE[source_type]:
            raise ApiError(
                "INVALID_REFERRAL_CATEGORY",
                "لا يمكنك إضافة ملاحظة ضمن هذه الفئة.",
                status_code=403,
            )

        referral = referral_service.find_open_duplicate(
            school=request.school, student=student, category=data["category"]
        )
        if referral is None:
            raise ApiError(
                "REFERRAL_NOT_FOUND",
                "لا توجد حالة متابعة مفتوحة لهذا الطالب في هذه الفئة.",
                status_code=404,
            )
        contribution = referral_service.add_contribution(
            referral_id=referral.id,
            school=request.school,
            membership=request.membership,
            observation_type=data["observation_type"],
            notes=data["notes"],
            request=request,
        )
        return Response(
            {"referral_id": referral.id, "contribution": serialize_contribution(contribution)},
            status=201,
        )


class StudentReferralsView(SchoolScopedAPIView):
    """إحالات طالب داخل ملفه — للإدارة والمرشد ضمن نطاقهما."""

    read_roles = (*MANAGE_ROLES, SchoolRole.COUNSELOR)
    write_roles = MANAGE_ROLES

    @extend_schema(responses=None)
    def get(self, request, student_id: int):
        get_object_or_404(Student, id=student_id, school=request.school)
        queryset = selectors.visible_referrals(
            school=request.school,
            membership=request.membership,
            roles=request.school_roles,
        ).filter(student_id=student_id).order_by("-created_at", "-id")
        return Response(
            {"results": [serialize_referral_row(r) for r in queryset]}
        )
