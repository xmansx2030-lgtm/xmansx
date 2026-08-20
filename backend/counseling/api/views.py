"""واجهات الحالات الإرشادية وطلبات المعلمين (م14).

طبقتا حماية لا واحدة: نطاق القراءة (`visible_cases`) يمنع رؤية حالة زميل، ودالة
`require_case_management` تمنع تعديلها. المعلم محجوب عن كل مسارات الحالات، وله
مسار واحد: طلباته هو.
"""

from django.db.models import Min, Q
from drf_spectacular.utils import extend_schema
from rest_framework.request import Request
from rest_framework.response import Response

from common.errors import ApiError
from common.pagination import DefaultPagination
from counseling.api.serializers import (
    ActivitySerializer,
    CaseRowSerializer,
    CaseStatusSerializer,
    CloseCaseSerializer,
    GoalSerializer,
    GoalStatusSerializer,
    OpenCaseSerializer,
    PlanSerializer,
    PlanStatusSerializer,
    ReassignCaseSerializer,
    ReopenCaseSerializer,
    SessionSerializer,
    TeacherRequestSerializer,
    TeacherResponseSerializer,
    VoidSessionSerializer,
)
from counseling.models import (
    ActivityStatus,
    ActivityType,
    CaseEventType,
    CasePriority,
    CaseStatus,
    CounselorCase,
    CounselorFollowUpPlan,
    CounselorSession,
    FollowUpActivity,
    FollowUpGoal,
    FollowUpRequestStatus,
    FollowUpRequestType,
    GoalStatus,
    GoalType,
    PlanStatus,
    SessionStatus,
    SessionType,
    TeacherImprovementStatus,
)
from counseling.selectors import (
    VIEW_ROLES,
    can_view_case,
    case_detail_queryset,
    case_plans,
    case_sessions,
    case_teacher_requests,
    case_timeline,
    counselor_dashboard_kpis,
    filter_cases,
    sort_cases,
    teacher_requests_for,
    visible_cases,
)
from counseling.services import cases as case_service
from counseling.services import plans as plan_service
from counseling.services import sessions as session_service
from counseling.services import teacher_requests as request_service
from counseling.services.snapshots import current_case_metrics
from memberships.api_base import SchoolScopedAPIView
from memberships.models import SchoolRole
from referrals.models import ReferralCategory, ReferralReason
from subscriptions.entitlements import require_feature
from subscriptions.models import EntitlementKey

CASE_READ_ROLES = VIEW_ROLES
CASE_WRITE_ROLES = (SchoolRole.SCHOOL_MANAGER, SchoolRole.COUNSELOR)
TEACHER_ROLES = (SchoolRole.TEACHER,)

CASE_NOT_FOUND = ApiError("CASE_NOT_FOUND", "ملف المتابعة غير موجود.", status_code=404)


class CounselingAPIView(SchoolScopedAPIView):
    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        require_feature(request.school, EntitlementKey.COUNSELING)


def _name(membership) -> str | None:
    if membership is None:
        return None
    profile = getattr(membership, "staff_profile", None)
    return profile.display_name if profile else membership.user.display_name


def _placement(student) -> tuple[str | None, str | None]:
    enrollments = list(student.enrollments.all())
    if not enrollments:
        return None, None
    latest = max(enrollments, key=lambda e: e.enrolled_at)
    return latest.grade.name, latest.section.name


def case_row(case, *, next_due=None) -> dict:
    grade, section = _placement(case.student)
    referral = case.primary_referral
    return {
        "id": case.id,
        "student_id": case.student_id,
        "student_name": case.student.full_name,
        "grade_name": grade,
        "section_name": section,
        "status": case.status,
        "status_label": CaseStatus(case.status).label,
        "priority": case.priority,
        "priority_label": CasePriority(case.priority).label,
        "referral_id": referral.id,
        "referral_category": referral.category,
        "referral_category_label": ReferralCategory(referral.category).label,
        "referral_reason_label": ReferralReason(referral.reason_code).label,
        "counselor_name": _name(case.assigned_counselor_membership),
        "counselor_membership_id": case.assigned_counselor_membership_id,
        "opened_at": case.opened_at.isoformat(),
        "last_activity_at": case.last_activity_at.isoformat(),
        "next_activity_due": next_due.isoformat() if next_due else None,
    }


def session_row(session) -> dict:
    return {
        "id": session.id,
        "session_type": session.session_type,
        "session_type_label": SessionType(session.session_type).label,
        "occurred_at": session.occurred_at.isoformat(),
        "summary": session.summary,
        "observations": session.observations,
        "outcome": session.outcome,
        "status": session.status,
        "status_label": SessionStatus(session.status).label,
        "created_by_name": _name(session.created_by_membership),
        "void_reason": session.void_reason,
    }


def goal_row(goal) -> dict:
    return {
        "id": goal.id,
        "goal_type": goal.goal_type,
        "goal_type_label": GoalType(goal.goal_type).label,
        "title": goal.title,
        "description": goal.description,
        "baseline_value": goal.baseline_value,
        "target_value": goal.target_value,
        "unit": goal.unit,
        "status": goal.status,
        "status_label": GoalStatus(goal.status).label,
        "completed_at": goal.completed_at.isoformat() if goal.completed_at else None,
    }


def activity_row(activity) -> dict:
    return {
        "id": activity.id,
        "activity_type": activity.activity_type,
        "activity_type_label": ActivityType(activity.activity_type).label,
        "title": activity.title,
        "description": activity.description,
        "due_date": activity.due_date.isoformat() if activity.due_date else None,
        "status": activity.status,
        "status_label": ActivityStatus(activity.status).label,
        "completed_at": activity.completed_at.isoformat() if activity.completed_at else None,
    }


def plan_row(plan) -> dict:
    return {
        "id": plan.id,
        "title": plan.title,
        "status": plan.status,
        "status_label": PlanStatus(plan.status).label,
        "start_date": plan.start_date.isoformat(),
        "target_end_date": plan.target_end_date.isoformat() if plan.target_end_date else None,
        "notes": plan.notes,
        "created_by_name": _name(plan.created_by_membership),
        "activated_at": plan.activated_at.isoformat() if plan.activated_at else None,
        "completed_at": plan.completed_at.isoformat() if plan.completed_at else None,
        "goals": [goal_row(goal) for goal in plan.goals.all()],
        "activities": [activity_row(a) for a in plan.activities.all()],
    }


def teacher_request_row(follow_up, *, include_response: bool = True) -> dict:
    response = getattr(follow_up, "response", None)
    row = {
        "id": follow_up.id,
        "request_type": follow_up.request_type,
        "request_type_label": FollowUpRequestType(follow_up.request_type).label,
        "question": follow_up.question,
        "due_date": follow_up.due_date.isoformat() if follow_up.due_date else None,
        "status": follow_up.status,
        "status_label": FollowUpRequestStatus(follow_up.status).label,
        "teacher_name": _name(follow_up.requested_from_membership),
        "requested_by_name": _name(follow_up.requested_by_membership),
        "created_at": follow_up.created_at.isoformat(),
        "responded_at": follow_up.responded_at.isoformat() if follow_up.responded_at else None,
    }
    if include_response and response is not None:
        row["response"] = {
            "observation": response.observation,
            "improvement_status": response.improvement_status,
            "improvement_status_label": TeacherImprovementStatus(
                response.improvement_status
            ).label,
            "notes": response.notes,
            "responded_by_name": _name(response.responded_by_membership),
            "created_at": response.created_at.isoformat(),
        }
    return row


def event_row(event) -> dict:
    return {
        "id": event.id,
        "event_type": event.event_type,
        "event_type_label": CaseEventType(event.event_type).label,
        "actor_name": _name(event.actor_membership),
        "created_at": event.created_at.isoformat(),
        "metadata": event.metadata,
    }


def _get_case(request, case_id: int) -> CounselorCase:
    case = case_detail_queryset(request.school).filter(id=case_id).first()
    if case is None or not can_view_case(
        case=case, membership=request.membership, roles=request.school_roles
    ):
        raise CASE_NOT_FOUND
    return case


class CounselorDashboardView(CounselingAPIView):
    read_roles = CASE_READ_ROLES
    write_roles = CASE_WRITE_ROLES

    @extend_schema(responses=None)
    def get(self, request: Request) -> Response:
        return Response(
            counselor_dashboard_kpis(
                school=request.school,
                membership=request.membership,
                roles=request.school_roles,
            )
        )


class CaseListView(CounselingAPIView):
    read_roles = CASE_READ_ROLES
    write_roles = CASE_WRITE_ROLES

    @extend_schema(responses=CaseRowSerializer(many=True))
    def get(self, request: Request) -> Response:
        queryset = visible_cases(
            school=request.school,
            membership=request.membership,
            roles=request.school_roles,
        )
        queryset = filter_cases(queryset, request.query_params)
        # أقرب إجراء مستحق ضمن نفس الاستعلام — لا استعلام لكل صف (البند 144)
        queryset = queryset.annotate(
            next_due=Min(
                "plans__activities__due_date",
                filter=Q(plans__activities__status=ActivityStatus.PENDING),
            )
        )
        queryset = sort_cases(queryset, request.query_params.get("sort", "recent"))

        paginator = DefaultPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(
            [case_row(case, next_due=case.next_due) for case in page]
        )


class ReferralOpenCaseView(CounselingAPIView):
    read_roles = CASE_WRITE_ROLES
    write_roles = CASE_WRITE_ROLES

    @extend_schema(request=OpenCaseSerializer, responses=CaseRowSerializer)
    def post(self, request: Request, referral_id: int) -> Response:
        serializer = OpenCaseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        case = case_service.open_counselor_case(
            school=request.school,
            membership=request.membership,
            roles=request.school_roles,
            referral_id=referral_id,
            priority=serializer.validated_data.get("priority", CasePriority.NORMAL),
            request=request,
        )
        return Response(case_row(_get_case(request, case.id)), status=201)


class CaseDetailView(CounselingAPIView):
    read_roles = CASE_READ_ROLES
    write_roles = CASE_WRITE_ROLES

    @extend_schema(responses=None)
    def get(self, request: Request, case_id: int) -> Response:
        case = _get_case(request, case_id)
        referral = case.primary_referral
        return Response(
            {
                **case_row(case),
                "summary": case.summary,
                "opened_by_name": _name(case.opened_by_membership),
                "closed_by_name": _name(case.closed_by_membership),
                "closed_at": case.closed_at.isoformat() if case.closed_at else None,
                "closure_reason": case.closure_reason,
                "outcome_summary": case.outcome_summary,
                "improvement_status": case.improvement_status,
                # وقت الفتح مقابل الحالي — مصدران منفصلان لا يخلطان (البند 18)
                "snapshot_at_opening": case.snapshot_data,
                "current_metrics": current_case_metrics(
                    school=request.school, student=case.student
                ),
                "referral": {
                    "id": referral.id,
                    "category_label": ReferralCategory(referral.category).label,
                    "reason_label": ReferralReason(referral.reason_code).label,
                    "description": referral.description,
                    "created_at": referral.created_at.isoformat(),
                    "snapshot_at_referral": referral.snapshot_data,
                },
                "can_manage": case_service.can_manage_case(
                    case=case, membership=request.membership, roles=request.school_roles
                ),
            }
        )


class CaseStatusView(CounselingAPIView):
    read_roles = CASE_WRITE_ROLES
    write_roles = CASE_WRITE_ROLES

    @extend_schema(request=CaseStatusSerializer, responses=CaseRowSerializer)
    def post(self, request: Request, case_id: int) -> Response:
        serializer = CaseStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        case = _get_case(request, case_id)
        case_service.change_case_status(
            case=case,
            membership=request.membership,
            roles=request.school_roles,
            new_status=serializer.validated_data["status"],
            request=request,
        )
        return Response(case_row(case))


class CaseCloseView(CounselingAPIView):
    read_roles = CASE_WRITE_ROLES
    write_roles = CASE_WRITE_ROLES

    @extend_schema(request=CloseCaseSerializer, responses=CaseRowSerializer)
    def post(self, request: Request, case_id: int) -> Response:
        serializer = CloseCaseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        case = _get_case(request, case_id)
        closed = case_service.close_case(
            case=case,
            membership=request.membership,
            roles=request.school_roles,
            closure_reason=data["closure_reason"],
            outcome_summary=data.get("outcome_summary", ""),
            improvement_status=data.get("improvement_status", "NOT_ASSESSED"),
            request=request,
        )
        return Response(case_row(_get_case(request, closed.id)))


class CaseReopenView(CounselingAPIView):
    read_roles = CASE_WRITE_ROLES
    write_roles = CASE_WRITE_ROLES

    @extend_schema(request=ReopenCaseSerializer, responses=CaseRowSerializer)
    def post(self, request: Request, case_id: int) -> Response:
        serializer = ReopenCaseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        case = _get_case(request, case_id)
        reopened = case_service.reopen_case(
            case=case,
            membership=request.membership,
            roles=request.school_roles,
            reason=serializer.validated_data["reason"],
            request=request,
        )
        return Response(case_row(_get_case(request, reopened.id)))


class CaseReassignView(CounselingAPIView):
    read_roles = (SchoolRole.SCHOOL_MANAGER,)
    write_roles = (SchoolRole.SCHOOL_MANAGER,)

    @extend_schema(request=ReassignCaseSerializer, responses=CaseRowSerializer)
    def post(self, request: Request, case_id: int) -> Response:
        serializer = ReassignCaseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        case = _get_case(request, case_id)
        case_service.reassign_case(
            case=case,
            membership=request.membership,
            roles=request.school_roles,
            counselor_id=serializer.validated_data["counselor_membership_id"],
            request=request,
        )
        return Response(case_row(_get_case(request, case.id)))


class CaseSessionsView(CounselingAPIView):
    read_roles = CASE_READ_ROLES
    write_roles = CASE_WRITE_ROLES

    @extend_schema(responses=None)
    def get(self, request: Request, case_id: int) -> Response:
        case = _get_case(request, case_id)
        return Response([session_row(s) for s in case_sessions(case)])

    @extend_schema(request=SessionSerializer, responses=None)
    def post(self, request: Request, case_id: int) -> Response:
        serializer = SessionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        case = _get_case(request, case_id)
        session = session_service.add_session(
            case=case,
            membership=request.membership,
            roles=request.school_roles,
            session_type=data["session_type"],
            occurred_at=data.get("occurred_at"),
            summary=data["summary"],
            observations=data.get("observations", ""),
            outcome=data.get("outcome", ""),
            request=request,
        )
        return Response(session_row(session), status=201)


class SessionVoidView(CounselingAPIView):
    read_roles = CASE_WRITE_ROLES
    write_roles = CASE_WRITE_ROLES

    @extend_schema(request=VoidSessionSerializer, responses=None)
    def post(self, request: Request, session_id: int) -> Response:
        serializer = VoidSessionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        session = (
            CounselorSession.objects.filter(id=session_id, school=request.school)
            .select_related("case")
            .first()
        )
        if session is None or not can_view_case(
            case=session.case, membership=request.membership, roles=request.school_roles
        ):
            raise ApiError("SESSION_NOT_FOUND", "الجلسة غير موجودة.", status_code=404)
        voided = session_service.void_session(
            session=session,
            membership=request.membership,
            roles=request.school_roles,
            reason=serializer.validated_data["reason"],
            request=request,
        )
        return Response(session_row(voided))


class CasePlansView(CounselingAPIView):
    read_roles = CASE_READ_ROLES
    write_roles = CASE_WRITE_ROLES

    @extend_schema(responses=None)
    def get(self, request: Request, case_id: int) -> Response:
        case = _get_case(request, case_id)
        return Response([plan_row(plan) for plan in case_plans(case)])

    @extend_schema(request=PlanSerializer, responses=None)
    def post(self, request: Request, case_id: int) -> Response:
        serializer = PlanSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        case = _get_case(request, case_id)
        plan = plan_service.create_plan(
            case=case,
            membership=request.membership,
            roles=request.school_roles,
            title=data["title"],
            start_date=data["start_date"],
            target_end_date=data.get("target_end_date"),
            notes=data.get("notes", ""),
            activate=data.get("activate", False),
            request=request,
        )
        return Response(plan_row(plan), status=201)


def _get_plan(request, plan_id: int) -> CounselorFollowUpPlan:
    plan = (
        CounselorFollowUpPlan.objects.filter(id=plan_id, school=request.school)
        .select_related("case", "case__student")
        .prefetch_related("goals", "activities")
        .first()
    )
    if plan is None or not can_view_case(
        case=plan.case, membership=request.membership, roles=request.school_roles
    ):
        raise ApiError("PLAN_NOT_FOUND", "خطة المتابعة غير موجودة.", status_code=404)
    return plan


class PlanStatusView(CounselingAPIView):
    read_roles = CASE_WRITE_ROLES
    write_roles = CASE_WRITE_ROLES

    @extend_schema(request=PlanStatusSerializer, responses=None)
    def post(self, request: Request, plan_id: int) -> Response:
        serializer = PlanStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        plan = _get_plan(request, plan_id)
        plan_service.change_plan_status(
            plan=plan,
            membership=request.membership,
            roles=request.school_roles,
            new_status=serializer.validated_data["status"],
            request=request,
        )
        return Response(plan_row(_get_plan(request, plan.id)))


class PlanGoalsView(CounselingAPIView):
    read_roles = CASE_WRITE_ROLES
    write_roles = CASE_WRITE_ROLES

    @extend_schema(request=GoalSerializer, responses=None)
    def post(self, request: Request, plan_id: int) -> Response:
        serializer = GoalSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        plan = _get_plan(request, plan_id)
        goal = plan_service.add_goal(
            plan=plan,
            membership=request.membership,
            roles=request.school_roles,
            goal_type=data["goal_type"],
            title=data["title"],
            description=data.get("description", ""),
            baseline_value=data.get("baseline_value"),
            target_value=data.get("target_value"),
            unit=data.get("unit", ""),
        )
        return Response(goal_row(goal), status=201)


class GoalStatusView(CounselingAPIView):
    read_roles = CASE_WRITE_ROLES
    write_roles = CASE_WRITE_ROLES

    @extend_schema(request=GoalStatusSerializer, responses=None)
    def patch(self, request: Request, goal_id: int) -> Response:
        serializer = GoalStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        goal = (
            FollowUpGoal.objects.filter(id=goal_id, school=request.school)
            .select_related("plan", "plan__case")
            .first()
        )
        if goal is None or not can_view_case(
            case=goal.plan.case, membership=request.membership, roles=request.school_roles
        ):
            raise ApiError("GOAL_NOT_FOUND", "الهدف غير موجود.", status_code=404)
        updated = plan_service.update_goal_status(
            goal=goal,
            membership=request.membership,
            roles=request.school_roles,
            new_status=serializer.validated_data["status"],
        )
        return Response(goal_row(updated))


class PlanActivitiesView(CounselingAPIView):
    read_roles = CASE_WRITE_ROLES
    write_roles = CASE_WRITE_ROLES

    @extend_schema(request=ActivitySerializer, responses=None)
    def post(self, request: Request, plan_id: int) -> Response:
        serializer = ActivitySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        plan = _get_plan(request, plan_id)
        activity = plan_service.add_activity(
            plan=plan,
            membership=request.membership,
            roles=request.school_roles,
            activity_type=data["activity_type"],
            title=data["title"],
            description=data.get("description", ""),
            due_date=data.get("due_date"),
        )
        return Response(activity_row(activity), status=201)


class ActivityCompleteView(CounselingAPIView):
    read_roles = CASE_WRITE_ROLES
    write_roles = CASE_WRITE_ROLES

    @extend_schema(request=None, responses=None)
    def post(self, request: Request, activity_id: int) -> Response:
        activity = (
            FollowUpActivity.objects.filter(id=activity_id, school=request.school)
            .select_related("plan", "plan__case")
            .first()
        )
        if activity is None or not can_view_case(
            case=activity.plan.case,
            membership=request.membership,
            roles=request.school_roles,
        ):
            raise ApiError("ACTIVITY_NOT_FOUND", "الإجراء غير موجود.", status_code=404)
        completed = plan_service.complete_activity(
            activity=activity, membership=request.membership, roles=request.school_roles
        )
        return Response(activity_row(completed))


class CaseTeacherRequestsView(CounselingAPIView):
    read_roles = CASE_READ_ROLES
    write_roles = CASE_WRITE_ROLES

    @extend_schema(responses=None)
    def get(self, request: Request, case_id: int) -> Response:
        case = _get_case(request, case_id)
        return Response([teacher_request_row(r) for r in case_teacher_requests(case)])

    @extend_schema(request=TeacherRequestSerializer, responses=None)
    def post(self, request: Request, case_id: int) -> Response:
        serializer = TeacherRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        case = _get_case(request, case_id)
        follow_up = request_service.request_teacher_follow_up(
            case=case,
            membership=request.membership,
            roles=request.school_roles,
            teacher_membership_id=data["teacher_membership_id"],
            request_type=data["request_type"],
            question=data["question"],
            due_date=data.get("due_date"),
            request=request,
        )
        return Response(teacher_request_row(follow_up), status=201)


class CaseTimelineView(CounselingAPIView):
    read_roles = CASE_READ_ROLES
    write_roles = CASE_WRITE_ROLES

    @extend_schema(responses=None)
    def get(self, request: Request, case_id: int) -> Response:
        case = _get_case(request, case_id)
        return Response([event_row(event) for event in case_timeline(case)])


class CaseTeachersView(CounselingAPIView):
    """معلمو المدرسة النشطون — لاختيار المرسل إليه (بلا بيانات اتصال)."""

    read_roles = CASE_WRITE_ROLES
    write_roles = CASE_WRITE_ROLES

    @extend_schema(responses=None)
    def get(self, request: Request) -> Response:
        from memberships.models import MembershipStatus, SchoolMembership

        teachers = (
            SchoolMembership.objects.filter(
                school=request.school,
                status=MembershipStatus.ACTIVE,
                roles__role=SchoolRole.TEACHER,
            )
            .select_related("user", "staff_profile")
            .distinct()
        )
        return Response(
            [{"membership_id": t.id, "name": _name(t)} for t in teachers]
        )


class TeacherFollowUpListView(CounselingAPIView):
    """صندوق المعلم — طلباته هو فقط، بلا أي محتوى إرشادي (البندان 69-71)."""

    read_roles = TEACHER_ROLES
    write_roles = TEACHER_ROLES

    @extend_schema(responses=None)
    def get(self, request: Request) -> Response:
        rows = []
        for follow_up in teacher_requests_for(
            school=request.school, membership=request.membership
        ):
            row = teacher_request_row(follow_up)
            row["student_name"] = follow_up.case.student.full_name
            row["student_id"] = follow_up.case.student_id
            row.pop("teacher_name", None)  # هو نفسه — لا فائدة
            rows.append(row)
        return Response(rows)


class TeacherFollowUpRespondView(CounselingAPIView):
    read_roles = TEACHER_ROLES
    write_roles = TEACHER_ROLES

    @extend_schema(request=TeacherResponseSerializer, responses=None)
    def post(self, request: Request, request_id: int) -> Response:
        serializer = TeacherResponseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        request_service.respond_to_request(
            school=request.school,
            membership=request.membership,
            request_id=request_id,
            observation=data["observation"],
            improvement_status=data["improvement_status"],
            notes=data.get("notes", ""),
            request=request,
        )
        follow_up = request_service.teacher_request_for(
            school=request.school, membership=request.membership, request_id=request_id
        )
        row = teacher_request_row(follow_up)
        row["student_name"] = follow_up.case.student.full_name
        return Response(row, status=201)


class StudentCounselingView(CounselingAPIView):
    """ملخص «الإرشاد والمتابعة» في ملف الطالب — المعلم محجوب (البند 85)."""

    read_roles = CASE_READ_ROLES
    write_roles = CASE_WRITE_ROLES

    @extend_schema(responses=None)
    def get(self, request: Request, student_id: int) -> Response:
        from students.models import Student

        student = Student.objects.filter(school=request.school, id=student_id).first()
        if student is None:
            raise ApiError("NOT_FOUND", "المورد المطلوب غير موجود.", status_code=404)
        from counseling.selectors import student_counseling_summary

        summary = student_counseling_summary(
            school=request.school, student=student, roles=request.school_roles
        )
        # المرشد يرى حالاته فقط ضمن الملخص كذلك
        if SchoolRole.COUNSELOR in set(request.school_roles) and not (
            set(request.school_roles) & {SchoolRole.SCHOOL_MANAGER, SchoolRole.VICE_PRINCIPAL}
        ):
            allowed = set(
                visible_cases(
                    school=request.school,
                    membership=request.membership,
                    roles=request.school_roles,
                ).values_list("id", flat=True)
            )
            summary["cases"] = [c for c in summary["cases"] if c["id"] in allowed]
            summary["total_cases"] = len(summary["cases"])
            summary["open_cases"] = sum(
                1 for c in summary["cases"] if c["status"] != CaseStatus.CLOSED
            )
        return Response(summary)
