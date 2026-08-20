"""طلبات متابعة المعلمين وردودهم (م14).

خصوصية المعلم هي القاعدة الحاكمة هنا (البنود 68-71، 98-99):
- المعلم يرى **طلباته هو** فقط: الطالب والسؤال والموعد وردّه — لا الحالة ولا جلساتها
  ولا ردود زملائه ولا تحليل الإغلاق.
- الرد يحل الطلب عبر **عضوية الطالب الحالية** لا بالمعرف وحده: تمرير معرف طلب زميل
  يعطي 404 لا 403 (لا نؤكد وجوده أصلًا).
- الرد **ثابت بعد الإرسال** (البند 44): التصحيح بطلب جديد.
"""

from django.db import IntegrityError, transaction
from django.utils import timezone as dj_timezone

from audit.models import AuditAction
from audit.services import record_event
from common.errors import ApiError
from counseling.models import (
    CaseEventType,
    FollowUpRequestStatus,
    FollowUpRequestType,
    TeacherFollowUpRequest,
    TeacherFollowUpResponse,
    TeacherImprovementStatus,
)
from counseling.services.cases import (
    log_case_event,
    require_case_management,
    require_open_case,
    touch_case,
)
from memberships.models import MembershipStatus, SchoolMembership, SchoolRole

REQUEST_NOT_FOUND = ApiError(
    "FOLLOW_UP_REQUEST_NOT_FOUND", "طلب المتابعة غير موجود.", status_code=404
)


def validate_teacher(*, school, teacher_membership_id: int) -> SchoolMembership:
    """معلم نشط في **نفس المدرسة** حصرًا (البند 40)."""
    teacher = (
        SchoolMembership.objects.filter(
            id=teacher_membership_id,
            school=school,
            status=MembershipStatus.ACTIVE,
            roles__role=SchoolRole.TEACHER,
        )
        .select_related("user", "staff_profile")
        .distinct()
        .first()
    )
    if teacher is None:
        raise ApiError(
            "TEACHER_NOT_FOUND", "المعلم غير موجود أو غير نشط في هذه المدرسة.", status_code=404
        )
    return teacher


def request_teacher_follow_up(
    *,
    case,
    membership,
    roles,
    teacher_membership_id: int,
    request_type: str,
    question: str,
    due_date=None,
    request=None,
) -> TeacherFollowUpRequest:
    require_case_management(case=case, membership=membership, roles=roles)
    require_open_case(case)
    if request_type not in FollowUpRequestType.values:
        raise ApiError("VALIDATION_ERROR", "نوع الطلب غير معروف.", status_code=400)
    if not (question or "").strip():
        raise ApiError("VALIDATION_ERROR", "نص السؤال مطلوب.", status_code=400)
    teacher = validate_teacher(school=case.school, teacher_membership_id=teacher_membership_id)

    with transaction.atomic():
        follow_up = TeacherFollowUpRequest.objects.create(
            school=case.school,
            case=case,
            requested_from_membership=teacher,
            requested_by_membership=membership,
            request_type=request_type,
            question=question.strip()[:1000],
            due_date=due_date,
        )
        log_case_event(
            case=case,
            event_type=CaseEventType.TEACHER_FOLLOW_UP_REQUESTED,
            membership=membership,
            metadata={"request_id": follow_up.id, "teacher_membership_id": teacher.id},
        )
        touch_case(case)
    record_event(
        AuditAction.TEACHER_FOLLOW_UP_REQUESTED,
        request=request,
        actor=membership.user,
        school=case.school,
        target_type="TeacherFollowUpRequest",
        target_id=follow_up.id,
        metadata={"case_id": case.id, "request_type": request_type},
    )
    return follow_up


def teacher_request_for(*, school, membership, request_id: int) -> TeacherFollowUpRequest:
    """يحل الطلب بعضوية المعلم الحالية — معرف زميله ليس مفتاحًا (البند 99)."""
    follow_up = (
        TeacherFollowUpRequest.objects.filter(
            id=request_id, school=school, requested_from_membership=membership
        )
        .select_related("case", "case__student", "requested_by_membership")
        .first()
    )
    if follow_up is None:
        raise REQUEST_NOT_FOUND
    return follow_up


def respond_to_request(
    *,
    school,
    membership,
    request_id: int,
    observation: str,
    improvement_status: str,
    notes: str = "",
    request=None,
) -> TeacherFollowUpResponse:
    follow_up = teacher_request_for(school=school, membership=membership, request_id=request_id)
    if improvement_status not in TeacherImprovementStatus.values:
        raise ApiError("VALIDATION_ERROR", "تقييم التحسن غير معروف.", status_code=400)
    if not (observation or "").strip():
        raise ApiError("VALIDATION_ERROR", "نص الملاحظة مطلوب.", status_code=400)
    if follow_up.status == FollowUpRequestStatus.CANCELLED:
        raise ApiError(
            "FOLLOW_UP_REQUEST_CANCELLED", "تم إلغاء هذا الطلب.", status_code=409
        )

    try:
        with transaction.atomic():
            response = TeacherFollowUpResponse.objects.create(
                school=school,
                request=follow_up,
                responded_by_membership=membership,
                observation=observation.strip()[:2000],
                improvement_status=improvement_status,
                notes=(notes or "").strip()[:1000],
            )
            follow_up.status = FollowUpRequestStatus.ANSWERED
            follow_up.responded_at = dj_timezone.now()
            follow_up.save(update_fields=["status", "responded_at", "updated_at"])
            log_case_event(
                case=follow_up.case,
                event_type=CaseEventType.TEACHER_RESPONSE_RECEIVED,
                membership=membership,
                metadata={
                    "request_id": follow_up.id,
                    "improvement_status": improvement_status,
                },
            )
            touch_case(follow_up.case)
    except IntegrityError:
        # OneToOne: الرد الثاني مرفوض — الرد ثابت بعد الإرسال (البند 44)
        raise ApiError(
            "FOLLOW_UP_ALREADY_ANSWERED",
            "تم إرسال الرد مسبقاً ولا يمكن تعديله.",
            status_code=409,
        ) from None

    record_event(
        AuditAction.TEACHER_FOLLOW_UP_ANSWERED,
        request=request,
        actor=membership.user,
        school=school,
        target_type="TeacherFollowUpResponse",
        target_id=response.id,
        metadata={"request_id": follow_up.id, "improvement_status": improvement_status},
    )
    return response
