"""جلسات المرشد داخل الحالة (م14).

الجلسة سجل مهني بحقول واضحة (ملخص/ملاحظات/نتيجة) لا نص حر واحد، ولا تحذف: الخطأ
يعالج بالإلغاء (VOIDED) بسبب وفاعل ووقت (البند 23).

**تكامل م12 (البنود 86-88):** مقابلة الطالب/ولي الأمر والاتصال تسجل كذلك
`StudentAction` واحدًا داخل نفس المعاملة — سجل إداري عام، بينما تفاصيل الإرشاد
تبقى في الجلسة وحدها.
"""

from django.db import transaction
from django.utils import timezone as dj_timezone

from audit.models import AuditAction
from audit.services import record_event
from common.errors import ApiError
from counseling.models import (
    CaseEventType,
    CounselorSession,
    SessionStatus,
    SessionType,
)
from counseling.services.cases import (
    log_case_event,
    require_case_management,
    require_open_case,
    touch_case,
)
from student_actions.models import StudentActionType

#: نوع الجلسة ← الإجراء الإداري المكافئ (لا سجل ثانٍ موازٍ بلا داعٍ — البند 86)
ACTION_FOR_SESSION = {
    SessionType.STUDENT_MEETING: StudentActionType.STUDENT_MEETING,
    SessionType.PARENT_MEETING: StudentActionType.PARENT_MEETING,
    SessionType.PHONE_CALL: StudentActionType.PARENT_CONTACT,
}


def add_session(
    *,
    case,
    membership,
    roles,
    session_type: str,
    occurred_at=None,
    summary: str,
    observations: str = "",
    outcome: str = "",
    request=None,
) -> CounselorSession:
    require_case_management(case=case, membership=membership, roles=roles)
    require_open_case(case)
    if session_type not in SessionType.values:
        raise ApiError("VALIDATION_ERROR", "نوع الجلسة غير معروف.", status_code=400)
    if not (summary or "").strip():
        raise ApiError("VALIDATION_ERROR", "ملخص الجلسة مطلوب.", status_code=400)

    now = dj_timezone.now()
    when = occurred_at or now
    if when > now:
        raise ApiError(
            "VALIDATION_ERROR", "لا يمكن تسجيل جلسة بتاريخ مستقبلي.", status_code=400
        )

    with transaction.atomic():
        session = CounselorSession.objects.create(
            school=case.school,
            case=case,
            session_type=session_type,
            occurred_at=when,
            summary=summary.strip()[:2000],
            observations=(observations or "").strip()[:2000],
            outcome=(outcome or "").strip()[:1000],
            created_by_membership=membership,
        )
        log_case_event(
            case=case,
            event_type=CaseEventType.SESSION_ADDED,
            membership=membership,
            metadata={"session_id": session.id, "session_type": session_type},
        )
        action_type = ACTION_FOR_SESSION.get(session_type)
        if action_type is not None:
            from student_actions.services import create_student_action

            create_student_action(
                school=case.school,
                membership=membership,
                student=case.student,
                action_type=action_type,
                performed_at=when,
                # لا نص إرشادي في السجل الإداري العام — إشارة للملف فقط
                notes=f"ضمن ملف المتابعة رقم {case.id}",
                request=request,
            )
        touch_case(case, when=now)

    record_event(
        AuditAction.COUNSELOR_SESSION_ADDED,
        request=request,
        actor=membership.user,
        school=case.school,
        target_type="CounselorSession",
        target_id=session.id,
        metadata={"case_id": case.id, "session_type": session_type},
    )
    return session


def void_session(*, session, membership, roles, reason: str, request=None) -> CounselorSession:
    require_case_management(case=session.case, membership=membership, roles=roles)
    if not (reason or "").strip():
        raise ApiError("VALIDATION_ERROR", "سبب الإلغاء مطلوب.", status_code=400)
    with transaction.atomic():
        locked = CounselorSession.objects.select_for_update().get(id=session.id)
        if locked.status == SessionStatus.VOIDED:
            raise ApiError(
                "SESSION_ALREADY_VOIDED", "الجلسة ملغاة مسبقاً.", status_code=409
            )
        locked.status = SessionStatus.VOIDED
        locked.voided_by_membership = membership
        locked.voided_at = dj_timezone.now()
        locked.void_reason = reason.strip()[:300]
        locked.save(
            update_fields=[
                "status", "voided_by_membership", "voided_at", "void_reason", "updated_at",
            ]
        )
        log_case_event(
            case=locked.case,
            event_type=CaseEventType.SESSION_VOIDED,
            membership=membership,
            metadata={"session_id": locked.id},
        )
        touch_case(locked.case)
    record_event(
        AuditAction.COUNSELOR_SESSION_VOIDED,
        request=request,
        actor=membership.user,
        school=locked.school,
        target_type="CounselorSession",
        target_id=locked.id,
    )
    return locked
