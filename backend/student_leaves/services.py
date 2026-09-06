"""إنشاء الاستئذان وإلغاؤه مع سجل غير قابل للمحو وعزل مدرسي صريح."""

from django.db import IntegrityError, transaction
from django.utils import timezone

from audit.models import AuditAction
from audit.services import record_event
from common.errors import ApiError
from student_leaves.models import StudentLeavePermission, StudentLeaveStatus
from students.models import EnrollmentStatus, StudentEnrollment, StudentStatus


@transaction.atomic
def record_student_leave(
    *, school, membership, student, leave_date, leave_time, reason: str, request=None
) -> StudentLeavePermission:
    if student.school_id != school.id:
        raise ApiError("NOT_FOUND", "المورد المطلوب غير موجود.", status_code=404)
    if student.status != StudentStatus.ACTIVE:
        raise ApiError(
            "ACTIVE_STUDENT_REQUIRED",
            "لا يمكن تسجيل استئذان لطالب غير نشط.",
            status_code=409,
        )
    if leave_date > timezone.localdate():
        raise ApiError(
            "FUTURE_STUDENT_LEAVE_NOT_ALLOWED",
            "لا يمكن تسجيل استئذان بتاريخ مستقبلي.",
            status_code=400,
        )

    enrollment = (
        StudentEnrollment.objects.filter(
            school=school,
            student=student,
            status=EnrollmentStatus.ACTIVE,
        )
        .select_related("grade", "section", "academic_year")
        .order_by("-academic_year__start_date")
        .first()
    )
    try:
        with transaction.atomic():
            leave = StudentLeavePermission.objects.create(
                school=school,
                student=student,
                leave_date=leave_date,
                leave_time=leave_time,
                reason=reason.strip(),
                grade_name=enrollment.grade.name if enrollment else "",
                section_name=enrollment.section.name if enrollment else "",
                recorded_by_membership=membership,
            )
    except IntegrityError as exc:
        raise ApiError(
            "ACTIVE_STUDENT_LEAVE_ALREADY_EXISTS",
            "يوجد استئذان ساري لهذا الطالب في التاريخ المحدد.",
            status_code=409,
        ) from exc

    record_event(
        AuditAction.STUDENT_LEAVE_RECORDED,
        request=request,
        actor=membership.user,
        school=school,
        target_type="StudentLeavePermission",
        target_id=leave.id,
        metadata={"student_id": student.id, "leave_date": leave_date.isoformat()},
    )
    return leave


@transaction.atomic
def cancel_student_leave(
    *, school, membership, leave: StudentLeavePermission, reason: str, request=None
) -> StudentLeavePermission:
    locked = StudentLeavePermission.objects.select_for_update().filter(
        id=leave.id, school=school
    ).first()
    if locked is None:
        raise ApiError("STUDENT_LEAVE_NOT_FOUND", "الاستئذان غير موجود.", status_code=404)
    if locked.status == StudentLeaveStatus.CANCELLED:
        raise ApiError(
            "STUDENT_LEAVE_ALREADY_CANCELLED",
            "تم إلغاء هذا الاستئذان مسبقًا.",
            status_code=409,
        )
    locked.status = StudentLeaveStatus.CANCELLED
    locked.cancelled_by_membership = membership
    locked.cancelled_at = timezone.now()
    locked.cancellation_reason = reason.strip()
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
        AuditAction.STUDENT_LEAVE_CANCELLED,
        request=request,
        actor=membership.user,
        school=school,
        target_type="StudentLeavePermission",
        target_id=locked.id,
        metadata={"student_id": locked.student_id},
    )
    return locked
