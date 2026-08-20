"""إنشاء الإجراءات الطلابية وإلغاؤها (م12).

- الإجراء **تسجيل** لا حساب: لا يمس أي مصدر حضور/عذر/إنذار (البند 2).
- ربط الإنذار يتحقق خادميًا: نفس المدرسة ونفس الطالب وإلا `INVALID_ACTION_WARNING_LINK`.
- لا حذف: `COMPLETED → CANCELLED` بسبب وفاعل ووقت، والإلغاء مرتين مرفوض.
"""

from django.db import transaction
from django.utils import timezone as dj_timezone

from audit.models import AuditAction
from audit.services import record_event
from common.errors import ApiError
from student_actions.models import StudentAction, StudentActionStatus, StudentActionType
from student_warnings.models import StudentWarning

MAX_NOTES = 500


def _resolve_warning(*, school, student, warning_id) -> StudentWarning | None:
    if warning_id in (None, ""):
        return None
    warning = StudentWarning.objects.filter(id=warning_id, school=school).first()
    # إنذار مدرسة أخرى أو طالب آخر: نفس الرمز — لا نكشف وجوده للمستأجر الآخر
    if warning is None or warning.student_id != student.id:
        raise ApiError(
            "INVALID_ACTION_WARNING_LINK",
            "الإنذار المرتبط غير موجود أو لا يخص هذا الطالب.",
            status_code=400,
        )
    return warning


def create_student_action(
    *,
    school,
    membership,
    student,
    action_type: str,
    warning_id=None,
    performed_at=None,
    notes: str = "",
    request=None,
) -> StudentAction:
    if action_type not in StudentActionType.values:
        raise ApiError("VALIDATION_ERROR", "نوع الإجراء غير معروف.", status_code=400)
    if student.school_id != school.id:
        raise ApiError("NOT_FOUND", "المورد المطلوب غير موجود.", status_code=404)

    warning = _resolve_warning(school=school, student=student, warning_id=warning_id)
    now = dj_timezone.now()
    when = performed_at or now
    if when > now:
        raise ApiError(
            "VALIDATION_ERROR", "لا يمكن تسجيل إجراء بتاريخ مستقبلي.", status_code=400
        )

    action = StudentAction.objects.create(
        school=school,
        student=student,
        warning=warning,
        action_type=action_type,
        status=StudentActionStatus.COMPLETED,
        performed_by_membership=membership,
        performed_at=when,
        notes=(notes or "")[:MAX_NOTES],
    )
    record_event(
        AuditAction.STUDENT_ACTION_CREATED,
        request=request,
        actor=membership.user,
        school=school,
        target_type="StudentAction",
        target_id=action.id,
        metadata={  # معرفات وأنواع فقط — لا نص الملاحظة ولا اسم الطالب
            "student_id": student.id,
            "action_type": action_type,
            "warning_id": warning.id if warning else None,
        },
    )
    return action


def cancel_student_action(
    *, school, membership, action, reason: str, request=None
) -> StudentAction:
    if action.school_id != school.id:
        raise ApiError("STUDENT_ACTION_NOT_FOUND", "الإجراء غير موجود.", status_code=404)
    with transaction.atomic():
        locked = StudentAction.objects.select_for_update().get(id=action.id)
        if locked.status == StudentActionStatus.CANCELLED:
            raise ApiError(
                "STUDENT_ACTION_ALREADY_CANCELLED",
                "تم إلغاء هذا الإجراء مسبقاً.",
                status_code=409,
            )
        locked.status = StudentActionStatus.CANCELLED
        locked.cancelled_by_membership = membership
        locked.cancelled_at = dj_timezone.now()
        locked.cancellation_reason = (reason or "")[:300]
        locked.save(
            update_fields=[
                "status",
                "cancelled_by_membership",
                "cancelled_at",
                "cancellation_reason",
                "updated_at",
            ]
        )
    record_event(
        AuditAction.STUDENT_ACTION_CANCELLED,
        request=request,
        actor=membership.user,
        school=school,
        target_type="StudentAction",
        target_id=locked.id,
        metadata={"student_id": locked.student_id, "action_type": locked.action_type},
    )
    return locked
