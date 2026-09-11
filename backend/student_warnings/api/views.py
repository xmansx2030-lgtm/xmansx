"""واجهات الإنذارات — القواعد للمدير، والإصدار للمدير/الوكيل، والقراءة تشمل المرشد.

لا `school_id` في أي طلب: ‏request.school من الجلسة حصرًا.
"""

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status as http_status
from rest_framework.request import Request
from rest_framework.response import Response

from common.errors import ApiError
from common.pagination import DefaultPagination
from memberships.api_base import SchoolScopedAPIView
from memberships.models import SchoolRole
from student_warnings.api.serializers import (
    EligibilityResponseSerializer,
    IssueWarningSerializer,
    RulesPatchSerializer,
    RulesResponseSerializer,
    VoidWarningSerializer,
    WarningDetailSerializer,
    WarningSerializer,
)
from student_warnings.models import StudentWarning, WarningLevel, WarningRuleType
from student_warnings.selectors.eligibility import (
    eligibility_dashboard,
    evaluate_student_warning_eligibility,
    get_warning_current_metric,
)
from student_warnings.services import issuance as issuance_service
from student_warnings.services.rules import get_rules_map, update_rules
from students.models import Student

MANAGER_ONLY = (SchoolRole.SCHOOL_MANAGER,)
# التشغيل: المدير والوكيل يصدران؛ المرشد يقرأ ضمن ملف الطالب فقط (مصفوفة م9)
WARNING_WRITE_ROLES = (SchoolRole.SCHOOL_MANAGER, SchoolRole.VICE_PRINCIPAL)
WARNING_READ_ROLES = (
    SchoolRole.SCHOOL_MANAGER,
    SchoolRole.VICE_PRINCIPAL,
    SchoolRole.COUNSELOR,
)

TYPE_LABELS = dict(WarningRuleType.choices)
LEVEL_LABELS = dict(WarningLevel.choices)


def _membership_name(membership) -> str | None:
    if membership is None:
        return None
    profile = getattr(membership, "staff_profile", None)
    return profile.display_name if profile else membership.user.display_name


def _warning_row(warning: StudentWarning) -> dict:
    return {
        "id": warning.id,
        "student_id": warning.student_id,
        # ‏Snapshot لا القيد الحالي — الاسم/الصف/الفصل كما كانت لحظة الإصدار
        "student_name": warning.student_name_snapshot,
        "grade_name": warning.grade_name_snapshot,
        "section_name": warning.section_name_snapshot,
        "warning_type": warning.warning_type,
        "warning_type_label": TYPE_LABELS[warning.warning_type],
        "level": warning.level,
        "level_label": LEVEL_LABELS[warning.level],
        "status": warning.status,
        "threshold_at_issue": warning.threshold_at_issue,
        "metric_value_at_issue": warning.metric_value_at_issue,
        "issued_at": warning.issued_at,
        "issued_by": _membership_name(warning.issued_by_membership),
        "notes": warning.notes,
        "voided_at": warning.voided_at,
        "voided_by": _membership_name(warning.voided_by_membership),
        "void_reason": warning.void_reason,
    }


class WarningRulesView(SchoolScopedAPIView):
    """عرض للمدير/الوكيل؛ التعديل للمدير حصرًا (قرار MVP — البند 77)."""

    read_roles = WARNING_WRITE_ROLES
    write_roles = MANAGER_ONLY

    @extend_schema(responses=RulesResponseSerializer)
    def get(self, request: Request) -> Response:
        return Response(get_rules_map(school=request.school))

    @extend_schema(request=RulesPatchSerializer, responses=RulesResponseSerializer)
    def patch(self, request: Request) -> Response:
        serializer = RulesPatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if not serializer.validated_data:
            raise ApiError("VALIDATION_ERROR", "لا توجد بيانات للتحديث.")
        return Response(
            update_rules(
                school=request.school,
                actor=request.user,
                payload=serializer.validated_data,
                request=request,
            )
        )


class WarningEligibilityView(SchoolScopedAPIView):
    read_roles = WARNING_WRITE_ROLES
    write_roles = WARNING_WRITE_ROLES

    @extend_schema(responses=EligibilityResponseSerializer)
    def get(self, request: Request) -> Response:
        def _int(name):
            value = request.query_params.get(name)
            try:
                return int(value) if value else None
            except ValueError:
                raise ApiError("VALIDATION_ERROR", "قيمة رقمية غير صحيحة.") from None

        rule_type = request.query_params.get("warning_type") or None
        if rule_type and rule_type not in WarningRuleType.values:
            raise ApiError("WARNING_RULE_NOT_FOUND", "نوع الإنذار غير معروف.", status_code=404)
        status_filter = request.query_params.get("status", "due")
        if status_filter not in ("due", "issued", "all"):
            raise ApiError("VALIDATION_ERROR", "قيمة الفلتر غير معروفة.")
        return Response(
            eligibility_dashboard(
                school=request.school,
                rule_type=rule_type,
                grade_id=_int("grade"),
                section_id=_int("section"),
                status_filter=status_filter,
                page=_int("page") or 1,
                page_size=_int("page_size") or 25,
            )
        )


class StudentEligibilityView(SchoolScopedAPIView):
    read_roles = WARNING_WRITE_ROLES
    write_roles = WARNING_WRITE_ROLES

    @extend_schema(responses=EligibilityResponseSerializer)
    def get(self, request: Request, student_id: int) -> Response:
        student = get_object_or_404(Student, id=student_id, school=request.school)
        return Response(
            evaluate_student_warning_eligibility(school=request.school, student=student)
        )


class WarningsView(SchoolScopedAPIView):
    read_roles = WARNING_READ_ROLES
    write_roles = WARNING_WRITE_ROLES

    @extend_schema(responses=WarningSerializer(many=True))
    def get(self, request: Request) -> Response:
        queryset = StudentWarning.objects.filter(school=request.school).select_related(
            "issued_by_membership__user", "issued_by_membership__staff_profile",
            "voided_by_membership__user", "voided_by_membership__staff_profile",
        ).order_by("-issued_at")
        student_id = request.query_params.get("student")
        if student_id:
            queryset = queryset.filter(student_id=student_id)
        warning_type = request.query_params.get("warning_type")
        if warning_type in WarningRuleType.values:
            queryset = queryset.filter(warning_type=warning_type)
        status_value = request.query_params.get("status")
        if status_value in ("ISSUED", "VOIDED"):
            queryset = queryset.filter(status=status_value)
        paginator = DefaultPagination()
        page = paginator.paginate_queryset(queryset, request)
        return paginator.get_paginated_response([_warning_row(w) for w in page])


class WarningIssueView(SchoolScopedAPIView):
    read_roles = WARNING_WRITE_ROLES
    write_roles = WARNING_WRITE_ROLES

    @extend_schema(request=IssueWarningSerializer, responses=WarningSerializer)
    def post(self, request: Request) -> Response:
        serializer = IssueWarningSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        student = get_object_or_404(
            Student, id=data["student_id"], school=request.school
        )
        warning = issuance_service.issue_student_warning(
            school=request.school,
            membership=request.membership,
            student=student,
            warning_type=data["warning_type"],
            level=data["level"],
            notes=data.get("notes", ""),
            request=request,
        )
        return Response(_warning_row(warning), status=http_status.HTTP_201_CREATED)


class WarningDetailView(SchoolScopedAPIView):
    read_roles = WARNING_READ_ROLES
    write_roles = WARNING_WRITE_ROLES

    @extend_schema(responses=WarningDetailSerializer)
    def get(self, request: Request, warning_id: int) -> Response:
        warning = get_object_or_404(
            StudentWarning.objects.select_related(
                "academic_year",
                "issued_by_membership__user", "issued_by_membership__staff_profile",
                "voided_by_membership__user", "voided_by_membership__staff_profile",
            ),
            id=warning_id,
            school=request.school,
        )
        current = get_warning_current_metric(warning=warning)
        return Response({
            **_warning_row(warning),
            "academic_year": warning.academic_year.name,
            # القيمة الحالية منفصلة عن Snapshot — عذر لاحق يغيرها ولا يمس الإنذار
            "current_metric_value": current,
            "metric_drifted": current != warning.metric_value_at_issue,
            "snapshot": {
                "full_absence_days": warning.full_absence_days_at_issue,
                "unexcused_full_absence_days": warning.unexcused_full_absence_days_at_issue,
                "excused_full_absence_days": warning.excused_full_absence_days_at_issue,
                "absent_periods": warning.absent_periods_at_issue,
                "unexcused_absent_periods": warning.unexcused_absent_periods_at_issue,
                "morning_late_occurrences": warning.morning_late_occurrences_at_issue,
                "morning_late_minutes": warning.morning_late_minutes_at_issue,
                "national_id_masked": warning.national_id_masked_snapshot,
            },
        })


class WarningVoidView(SchoolScopedAPIView):
    """الإلغاء للمدير حصرًا — لا حذف نهائي لسجل إداري صادر."""

    read_roles = MANAGER_ONLY
    write_roles = MANAGER_ONLY

    @extend_schema(request=VoidWarningSerializer, responses=WarningSerializer)
    def post(self, request: Request, warning_id: int) -> Response:
        warning = get_object_or_404(
            StudentWarning, id=warning_id, school=request.school
        )
        serializer = VoidWarningSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        warning = issuance_service.void_student_warning(
            school=request.school,
            membership=request.membership,
            warning=warning,
            reason=serializer.validated_data["reason"],
            request=request,
        )
        return Response(_warning_row(warning))
