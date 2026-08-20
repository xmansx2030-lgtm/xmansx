"""فتح الحالات الإرشادية وإدارتها (م14).

ضمانات:
- **فتح واحد**: قيد فريد على الإحالة يجعل النقر المزدوج وطلبين متزامنين ملفًا واحدًا
  (البندان 14-15) — لا فحص تطبيقي وحده.
- **لا ملف ثانٍ حي لنفس الطالب**: الإحالة الثانية تُوصَل بالملف القائم بقرار
  المستخدم لا تلقائيًا (البند 81).
- **اللقطة تُجمّد عند الفتح**؛ المؤشر الحالي يقرأ منفصلًا (البند 18).
- الإغلاق يلزمه سبب (البند 49)، وإعادة الفتح تسجل سببها وفاعلها (البند 53).
"""

from django.db import IntegrityError, transaction
from django.utils import timezone as dj_timezone

from audit.models import AuditAction
from audit.services import record_event
from common.errors import ApiError
from counseling.models import (
    ALLOWED_STATUS_FLOW,
    LIVE_CASE_STATUSES,
    ActivityStatus,
    CaseClosureReason,
    CaseEventType,
    CaseStatus,
    CounselorCase,
    CounselorCaseEvent,
    FollowUpActivity,
    FollowUpRequestStatus,
    ImprovementStatus,
    PlanStatus,
    TeacherFollowUpRequest,
)
from counseling.services.snapshots import build_case_snapshot
from memberships.models import MembershipStatus, SchoolMembership, SchoolRole
from referrals.models import ReferralStatus, StudentReferral

MANAGE_ROLES = (SchoolRole.SCHOOL_MANAGER, SchoolRole.VICE_PRINCIPAL)
#: من يفتح/يدير الملف: المرشد صاحب الحالة، والمدير إداريًا (البندان 75-76)
CASE_ADMIN_ROLES = (SchoolRole.SCHOOL_MANAGER,)

CASE_NOT_FOUND = ApiError("CASE_NOT_FOUND", "ملف المتابعة غير موجود.", status_code=404)


def log_case_event(*, case, event_type: str, membership, metadata=None) -> None:
    CounselorCaseEvent.objects.create(
        school_id=case.school_id,
        case=case,
        event_type=event_type,
        actor_membership=membership,
        metadata=metadata or {},
    )


def touch_case(case, *, when=None) -> None:
    """آخر نشاط — يُحدَّث مع كل إضافة ليعمل فرز «الأقدم بلا متابعة» بلا N+1."""
    case.last_activity_at = when or dj_timezone.now()
    case.save(update_fields=["last_activity_at", "updated_at"])


def _is_counselor(roles) -> bool:
    return SchoolRole.COUNSELOR in set(roles or [])


def _is_manager(roles) -> bool:
    return bool(set(roles or []) & set(CASE_ADMIN_ROLES))


def can_manage_case(*, case, membership, roles) -> bool:
    """من يعدّل محتوى الملف: المرشد المسؤول عنه، أو مدير المدرسة إداريًا."""
    if _is_manager(roles):
        return True
    return (
        _is_counselor(roles)
        and case.assigned_counselor_membership_id == membership.id
    )


def require_case_management(*, case, membership, roles) -> None:
    if not can_manage_case(case=case, membership=membership, roles=roles):
        raise ApiError(
            "CASE_PERMISSION_DENIED",
            "هذا الملف من مسؤولية مرشد آخر.",
            status_code=403,
        )


def require_open_case(case) -> None:
    """الحالة تُقرأ من قاعدة البيانات لا من النسخة المحمولة.

    ملف أغلقه المدير للتو (أو نسخة قديمة في الذاكرة) كان يقبل جلسة/خطة جديدة —
    استعلام واحد يغلق الثغرة ويغطي التزامن معًا.
    """
    current = (
        CounselorCase.objects.filter(id=case.id)
        .values_list("status", flat=True)
        .first()
    )
    if current == CaseStatus.CLOSED:
        raise ApiError(
            "CASE_CLOSED", "الملف مغلق — أعد فتحه أولاً.", status_code=409
        )


def open_counselor_case(
    *, school, membership, roles, referral_id: int, priority: str = "NORMAL", request=None
) -> CounselorCase:
    referral = (
        StudentReferral.objects.filter(id=referral_id, school=school)
        .select_related("student")
        .first()
    )
    if referral is None:
        raise ApiError("REFERRAL_NOT_FOUND", "الإحالة غير موجودة.", status_code=404)
    if referral.status != ReferralStatus.ACKNOWLEDGED:
        raise ApiError(
            "REFERRAL_NOT_ACKNOWLEDGED",
            "يفتح الملف بعد استلام الإحالة.",
            status_code=409,
        )
    # المرشد المعيّن وحده يفتح ملفه؛ المدير يفتح إداريًا (البند 13)
    if not _is_manager(roles) and (
        not _is_counselor(roles)
        or referral.assigned_counselor_membership_id != membership.id
    ):
        raise ApiError(
            "CASE_PERMISSION_DENIED",
            "فتح الملف من صلاحية المرشد المستلم للإحالة.",
            status_code=403,
        )

    student = referral.student
    now = dj_timezone.now()
    try:
        with transaction.atomic():
            existing_live = (
                CounselorCase.objects.select_for_update()
                .filter(
                    school=school, student=student, status__in=LIVE_CASE_STATUSES
                )
                .exclude(primary_referral=referral)
                .first()
            )
            if existing_live is not None:
                # لا ملف ثانٍ تلقائيًا — القرار للمستخدم (البند 81)
                raise ApiError(
                    "OPEN_CASE_EXISTS",
                    "للطالب ملف متابعة مفتوح — أضف إليه بدل فتح ملف ثانٍ.",
                    status_code=409,
                    details={"existing_case_id": existing_live.id},
                )
            case = CounselorCase.objects.create(
                school=school,
                student=student,
                primary_referral=referral,
                assigned_counselor_membership=referral.assigned_counselor_membership
                or (membership if _is_counselor(roles) else None),
                status=CaseStatus.OPEN,
                priority=priority,
                opened_by_membership=membership,
                opened_at=now,
                last_activity_at=now,
                snapshot_data=build_case_snapshot(
                    school=school, student=student, referral=referral
                ),
            )
            log_case_event(
                case=case,
                event_type=CaseEventType.CASE_OPENED,
                membership=membership,
                metadata={"referral_id": referral.id},
            )
    except IntegrityError:
        # الحكم النهائي من قاعدة البيانات: ملف واحد لكل إحالة مهما تزامنت الطلبات
        raise ApiError(
            "CASE_ALREADY_OPEN",
            "تم فتح ملف متابعة لهذه الإحالة مسبقاً.",
            status_code=409,
        ) from None

    record_event(
        AuditAction.COUNSELOR_CASE_OPENED,
        request=request,
        actor=membership.user,
        school=school,
        target_type="CounselorCase",
        target_id=case.id,
        metadata={"student_id": student.id, "referral_id": referral.id},
    )
    return case


def change_case_status(
    *, case, membership, roles, new_status: str, request=None
) -> CounselorCase:
    require_case_management(case=case, membership=membership, roles=roles)
    if new_status not in CaseStatus.values:
        raise ApiError("VALIDATION_ERROR", "حالة غير معروفة.", status_code=400)
    if new_status in (CaseStatus.CLOSED,):
        raise ApiError(
            "VALIDATION_ERROR",
            "الإغلاق يتم عبر إجراء الإغلاق بسببه.",
            status_code=400,
        )
    require_open_case(case)
    allowed = ALLOWED_STATUS_FLOW.get(case.status, ())
    if new_status not in allowed:
        raise ApiError(
            "INVALID_CASE_STATUS_TRANSITION",
            "لا يمكن الانتقال إلى هذه الحالة من الحالة الراهنة.",
            status_code=409,
            details={"from": case.status, "allowed": list(allowed)},
        )
    previous = case.status
    case.status = new_status
    case.last_activity_at = dj_timezone.now()
    case.save(update_fields=["status", "last_activity_at", "updated_at"])
    log_case_event(
        case=case,
        event_type=CaseEventType.STATUS_CHANGED,
        membership=membership,
        metadata={"from": previous, "to": new_status},
    )
    record_event(
        AuditAction.COUNSELOR_CASE_STATUS_CHANGED,
        request=request,
        actor=membership.user,
        school=case.school,
        target_type="CounselorCase",
        target_id=case.id,
        metadata={"from": previous, "to": new_status},
    )
    return case


def close_case(
    *,
    case,
    membership,
    roles,
    closure_reason: str,
    outcome_summary: str = "",
    improvement_status: str = ImprovementStatus.NOT_ASSESSED,
    request=None,
) -> CounselorCase:
    """الإغلاق يرتب ما تركه المرشد خلفه (البند 52) — لا خطط ولا طلبات معلقة."""
    require_case_management(case=case, membership=membership, roles=roles)
    if closure_reason not in CaseClosureReason.values:
        raise ApiError(
            "CASE_CLOSURE_REASON_REQUIRED",
            "سبب الإغلاق مطلوب.",
            status_code=400,
        )
    if improvement_status and improvement_status not in ImprovementStatus.values:
        raise ApiError("VALIDATION_ERROR", "نتيجة غير معروفة.", status_code=400)

    now = dj_timezone.now()
    with transaction.atomic():
        locked = CounselorCase.objects.select_for_update().get(id=case.id)
        if locked.status == CaseStatus.CLOSED:
            raise ApiError("CASE_ALREADY_CLOSED", "الملف مغلق مسبقاً.", status_code=409)

        plans = list(locked.plans.filter(status=PlanStatus.ACTIVE))
        for plan in plans:
            plan.status = PlanStatus.COMPLETED
            plan.completed_at = now
            plan.save(update_fields=["status", "completed_at", "updated_at"])
            log_case_event(
                case=locked,
                event_type=CaseEventType.PLAN_COMPLETED,
                membership=membership,
                metadata={"plan_id": plan.id, "by_closure": True},
            )
        FollowUpActivity.objects.filter(
            plan__case=locked, status=ActivityStatus.PENDING
        ).update(status=ActivityStatus.CANCELLED)
        TeacherFollowUpRequest.objects.filter(
            case=locked, status=FollowUpRequestStatus.PENDING
        ).update(status=FollowUpRequestStatus.CANCELLED)

        locked.status = CaseStatus.CLOSED
        locked.closed_at = now
        locked.closed_by_membership = membership
        locked.closure_reason = closure_reason
        locked.outcome_summary = (outcome_summary or "")[:2000]
        locked.improvement_status = improvement_status or ImprovementStatus.NOT_ASSESSED
        locked.last_activity_at = now
        locked.save(
            update_fields=[
                "status", "closed_at", "closed_by_membership", "closure_reason",
                "outcome_summary", "improvement_status", "last_activity_at", "updated_at",
            ]
        )
        log_case_event(
            case=locked,
            event_type=CaseEventType.CASE_CLOSED,
            membership=membership,
            metadata={
                "closure_reason": closure_reason,
                "improvement_status": locked.improvement_status,
                "plans_completed": len(plans),
            },
        )
    record_event(
        AuditAction.COUNSELOR_CASE_CLOSED,
        request=request,
        actor=membership.user,
        school=locked.school,
        target_type="CounselorCase",
        target_id=locked.id,
        metadata={"closure_reason": closure_reason},
    )
    return locked


def reopen_case(*, case, membership, roles, reason: str, request=None) -> CounselorCase:
    require_case_management(case=case, membership=membership, roles=roles)
    if not (reason or "").strip():
        raise ApiError(
            "CASE_REOPEN_REASON_REQUIRED", "سبب إعادة الفتح مطلوب.", status_code=400
        )
    with transaction.atomic():
        locked = CounselorCase.objects.select_for_update().get(id=case.id)
        if locked.status != CaseStatus.CLOSED:
            raise ApiError("CASE_NOT_CLOSED", "الملف غير مغلق.", status_code=409)
        # ملف حي آخر للطالب يمنع إعادة الفتح — وإلا ملفان يعملان معًا
        if (
            CounselorCase.objects.filter(
                school=locked.school, student=locked.student, status__in=LIVE_CASE_STATUSES
            )
            .exclude(id=locked.id)
            .exists()
        ):
            raise ApiError(
                "OPEN_CASE_EXISTS",
                "للطالب ملف متابعة مفتوح — لا يعاد فتح ملف ثانٍ.",
                status_code=409,
            )
        now = dj_timezone.now()
        locked.status = CaseStatus.OPEN
        locked.closed_at = None
        locked.closed_by_membership = None
        locked.closure_reason = ""
        locked.last_activity_at = now
        locked.save(
            update_fields=[
                "status", "closed_at", "closed_by_membership", "closure_reason",
                "last_activity_at", "updated_at",
            ]
        )
        log_case_event(
            case=locked,
            event_type=CaseEventType.CASE_REOPENED,
            membership=membership,
            metadata={"reason": reason.strip()[:300]},
        )
    record_event(
        AuditAction.COUNSELOR_CASE_REOPENED,
        request=request,
        actor=membership.user,
        school=locked.school,
        target_type="CounselorCase",
        target_id=locked.id,
    )
    return locked


def reassign_case(*, case, membership, roles, counselor_id: int, request=None) -> CounselorCase:
    """تغيير المرشد المسؤول — قرار إداري (البند 72)."""
    if not _is_manager(roles):
        raise ApiError(
            "CASE_PERMISSION_DENIED", "تغيير المرشد من صلاحية المدير.", status_code=403
        )
    counselor = (
        SchoolMembership.objects.filter(
            id=counselor_id,
            school=case.school,
            status=MembershipStatus.ACTIVE,
            roles__role=SchoolRole.COUNSELOR,
        )
        .distinct()
        .first()
    )
    if counselor is None:
        raise ApiError("COUNSELOR_NOT_FOUND", "المرشد غير موجود.", status_code=404)
    previous = case.assigned_counselor_membership_id
    case.assigned_counselor_membership = counselor
    case.last_activity_at = dj_timezone.now()
    case.save(
        update_fields=[
            "assigned_counselor_membership", "last_activity_at", "updated_at",
        ]
    )
    log_case_event(
        case=case,
        event_type=CaseEventType.COUNSELOR_REASSIGNED,
        membership=membership,
        metadata={"from": previous, "to": counselor.id},
    )
    record_event(
        AuditAction.COUNSELOR_CASE_REASSIGNED,
        request=request,
        actor=membership.user,
        school=case.school,
        target_type="CounselorCase",
        target_id=case.id,
        metadata={"counselor_membership_id": counselor.id},
    )
    return case
