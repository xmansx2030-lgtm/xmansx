"""خطط المتابعة وأهدافها وإجراءاتها (م14).

- **خطة نشطة واحدة لكل ملف** (البند 27): قيد فريد جزئي في قاعدة البيانات هو الحكم،
  لا فحص تطبيقي وحده.
- الأهداف رقمية أو وصفية معًا (البند 32): `baseline/target` اختيارية.
- الإجراءات لها موعد وحالة تنفيذ، وإتمامها يسجل فاعله ووقته.
"""

from django.db import IntegrityError, transaction
from django.utils import timezone as dj_timezone

from audit.models import AuditAction
from audit.services import record_event
from common.errors import ApiError
from counseling.models import (
    ActivityStatus,
    ActivityType,
    CaseEventType,
    CounselorFollowUpPlan,
    FollowUpActivity,
    FollowUpGoal,
    GoalStatus,
    GoalType,
    PlanStatus,
)
from counseling.services.cases import (
    log_case_event,
    require_case_management,
    require_open_case,
    touch_case,
)

TERMINAL_PLAN_STATUSES = (PlanStatus.COMPLETED, PlanStatus.CANCELLED)


def create_plan(
    *,
    case,
    membership,
    roles,
    title: str,
    start_date,
    target_end_date=None,
    notes: str = "",
    activate: bool = False,
    request=None,
) -> CounselorFollowUpPlan:
    require_case_management(case=case, membership=membership, roles=roles)
    require_open_case(case)
    if not (title or "").strip():
        raise ApiError("VALIDATION_ERROR", "عنوان الخطة مطلوب.", status_code=400)
    if target_end_date is not None and target_end_date < start_date:
        raise ApiError(
            "VALIDATION_ERROR", "تاريخ النهاية قبل تاريخ البداية.", status_code=400
        )

    now = dj_timezone.now()
    try:
        with transaction.atomic():
            plan = CounselorFollowUpPlan.objects.create(
                school=case.school,
                case=case,
                title=title.strip()[:200],
                status=PlanStatus.ACTIVE if activate else PlanStatus.DRAFT,
                start_date=start_date,
                target_end_date=target_end_date,
                created_by_membership=membership,
                activated_at=now if activate else None,
                notes=(notes or "").strip()[:2000],
            )
            log_case_event(
                case=case,
                event_type=CaseEventType.PLAN_CREATED,
                membership=membership,
                metadata={"plan_id": plan.id, "activated": activate},
            )
            if activate:
                # خطة تولد نشطة تسجل تفعيلها أيضًا: الخط الزمني يجب أن يبيّن متى
                # صارت نافذة بلا قراءة metadata حدث الإنشاء
                log_case_event(
                    case=case,
                    event_type=CaseEventType.PLAN_ACTIVATED,
                    membership=membership,
                    metadata={"plan_id": plan.id, "on_create": True},
                )
            touch_case(case, when=now)
    except IntegrityError:
        raise ApiError(
            "ACTIVE_PLAN_EXISTS",
            "توجد خطة متابعة نشطة لهذا الملف — أكملها أو ألغها أولاً.",
            status_code=409,
        ) from None

    record_event(
        AuditAction.FOLLOW_UP_PLAN_CREATED,
        request=request,
        actor=membership.user,
        school=case.school,
        target_type="CounselorFollowUpPlan",
        target_id=plan.id,
        metadata={"case_id": case.id},
    )
    return plan


def change_plan_status(
    *, plan, membership, roles, new_status: str, request=None
) -> CounselorFollowUpPlan:
    require_case_management(case=plan.case, membership=membership, roles=roles)
    if new_status not in PlanStatus.values:
        raise ApiError("VALIDATION_ERROR", "حالة خطة غير معروفة.", status_code=400)
    if plan.status in TERMINAL_PLAN_STATUSES:
        raise ApiError(
            "PLAN_ALREADY_FINISHED", "الخطة منتهية مسبقاً.", status_code=409
        )
    if new_status == PlanStatus.DRAFT:
        raise ApiError(
            "VALIDATION_ERROR", "لا يمكن إعادة الخطة إلى مسودة.", status_code=400
        )
    if new_status == PlanStatus.ACTIVE:
        require_open_case(plan.case)

    now = dj_timezone.now()
    event = {
        PlanStatus.ACTIVE: CaseEventType.PLAN_ACTIVATED,
        PlanStatus.COMPLETED: CaseEventType.PLAN_COMPLETED,
        PlanStatus.CANCELLED: CaseEventType.PLAN_CANCELLED,
    }[new_status]
    try:
        with transaction.atomic():
            plan.status = new_status
            if new_status == PlanStatus.ACTIVE:
                plan.activated_at = plan.activated_at or now
            if new_status in TERMINAL_PLAN_STATUSES:
                plan.completed_at = now
            plan.save(
                update_fields=["status", "activated_at", "completed_at", "updated_at"]
            )
            log_case_event(
                case=plan.case,
                event_type=event,
                membership=membership,
                metadata={"plan_id": plan.id},
            )
            touch_case(plan.case, when=now)
    except IntegrityError:
        raise ApiError(
            "ACTIVE_PLAN_EXISTS",
            "توجد خطة متابعة نشطة لهذا الملف — أكملها أو ألغها أولاً.",
            status_code=409,
        ) from None

    record_event(
        AuditAction.FOLLOW_UP_PLAN_STATUS_CHANGED,
        request=request,
        actor=membership.user,
        school=plan.school,
        target_type="CounselorFollowUpPlan",
        target_id=plan.id,
        metadata={"status": new_status},
    )
    return plan


def add_goal(
    *,
    plan,
    membership,
    roles,
    goal_type: str,
    title: str,
    description: str = "",
    baseline_value=None,
    target_value=None,
    unit: str = "",
) -> FollowUpGoal:
    require_case_management(case=plan.case, membership=membership, roles=roles)
    require_open_case(plan.case)
    if plan.status in TERMINAL_PLAN_STATUSES:
        raise ApiError("PLAN_ALREADY_FINISHED", "الخطة منتهية.", status_code=409)
    if goal_type not in GoalType.values:
        raise ApiError("VALIDATION_ERROR", "نوع الهدف غير معروف.", status_code=400)
    if not (title or "").strip():
        raise ApiError("VALIDATION_ERROR", "عنوان الهدف مطلوب.", status_code=400)

    goal = FollowUpGoal.objects.create(
        school=plan.school,
        plan=plan,
        goal_type=goal_type,
        title=title.strip()[:200],
        description=(description or "").strip()[:1000],
        baseline_value=baseline_value,
        target_value=target_value,
        unit=(unit or "").strip()[:20],
    )
    log_case_event(
        case=plan.case,
        event_type=CaseEventType.GOAL_ADDED,
        membership=membership,
        metadata={"goal_id": goal.id, "goal_type": goal_type},
    )
    touch_case(plan.case)
    return goal


def update_goal_status(*, goal, membership, roles, new_status: str) -> FollowUpGoal:
    require_case_management(case=goal.plan.case, membership=membership, roles=roles)
    if new_status not in GoalStatus.values:
        raise ApiError("VALIDATION_ERROR", "حالة هدف غير معروفة.", status_code=400)
    if goal.status != GoalStatus.OPEN:
        raise ApiError("GOAL_ALREADY_FINISHED", "الهدف منتهٍ مسبقاً.", status_code=409)

    goal.status = new_status
    goal.completed_at = dj_timezone.now() if new_status == GoalStatus.COMPLETED else None
    goal.save(update_fields=["status", "completed_at", "updated_at"])
    if new_status == GoalStatus.COMPLETED:
        log_case_event(
            case=goal.plan.case,
            event_type=CaseEventType.GOAL_COMPLETED,
            membership=membership,
            metadata={"goal_id": goal.id},
        )
    touch_case(goal.plan.case)
    return goal


def add_activity(
    *,
    plan,
    membership,
    roles,
    activity_type: str,
    title: str,
    description: str = "",
    due_date=None,
) -> FollowUpActivity:
    require_case_management(case=plan.case, membership=membership, roles=roles)
    require_open_case(plan.case)
    if plan.status in TERMINAL_PLAN_STATUSES:
        raise ApiError("PLAN_ALREADY_FINISHED", "الخطة منتهية.", status_code=409)
    if activity_type not in ActivityType.values:
        raise ApiError("VALIDATION_ERROR", "نوع الإجراء غير معروف.", status_code=400)
    if not (title or "").strip():
        raise ApiError("VALIDATION_ERROR", "عنوان الإجراء مطلوب.", status_code=400)

    activity = FollowUpActivity.objects.create(
        school=plan.school,
        plan=plan,
        activity_type=activity_type,
        title=title.strip()[:200],
        description=(description or "").strip()[:1000],
        due_date=due_date,
    )
    log_case_event(
        case=plan.case,
        event_type=CaseEventType.ACTIVITY_ADDED,
        membership=membership,
        metadata={"activity_id": activity.id, "activity_type": activity_type},
    )
    touch_case(plan.case)
    return activity


def complete_activity(*, activity, membership, roles) -> FollowUpActivity:
    require_case_management(case=activity.plan.case, membership=membership, roles=roles)
    if activity.status != ActivityStatus.PENDING:
        raise ApiError(
            "ACTIVITY_ALREADY_FINISHED", "الإجراء منتهٍ مسبقاً.", status_code=409
        )
    activity.status = ActivityStatus.COMPLETED
    activity.completed_at = dj_timezone.now()
    activity.completed_by_membership = membership
    activity.save(
        update_fields=[
            "status", "completed_at", "completed_by_membership", "updated_at",
        ]
    )
    log_case_event(
        case=activity.plan.case,
        event_type=CaseEventType.ACTIVITY_COMPLETED,
        membership=membership,
        metadata={"activity_id": activity.id},
    )
    touch_case(activity.plan.case)
    return activity
