"""دورة حياة الطالب — التصنيف الفردي والجماعي وإغلاق القيود.

القاعدة الإلزامية: الطالب المفقود من ملف نور لا يحذف تلقائيًا أبدًا —
مراجعة → تصنيف → (حذف نهائي اختياري لاحقًا).
"""

from datetime import date

from django.db import transaction
from django.utils import timezone

from audit.models import AuditAction
from audit.services import record_event
from common.errors import ApiError
from students.models import (
    EnrollmentStatus,
    Student,
    StudentEnrollment,
    StudentStatus,
)

# حالة الطالب → حالة إغلاق قيده الفعال
_ENROLLMENT_CLOSE_MAP = {
    StudentStatus.GRADUATED: EnrollmentStatus.COMPLETED,
    StudentStatus.TRANSFERRED: EnrollmentStatus.TRANSFERRED,
    StudentStatus.WITHDRAWN: EnrollmentStatus.WITHDRAWN,
    StudentStatus.INACTIVE: EnrollmentStatus.ARCHIVED,
    StudentStatus.ARCHIVED: EnrollmentStatus.ARCHIVED,
}

ALLOWED_TARGET_STATUSES = {
    StudentStatus.ACTIVE,
    StudentStatus.GRADUATED,
    StudentStatus.TRANSFERRED,
    StudentStatus.WITHDRAWN,
    StudentStatus.INACTIVE,
}


@transaction.atomic
def set_student_status(
    *,
    student: Student,
    new_status: str,
    actor,
    exit_date: date | None = None,
    exit_reason: str = "",
    request=None,
) -> Student:
    if new_status not in ALLOWED_TARGET_STATUSES:
        raise ApiError("VALIDATION_ERROR", "حالة الطالب المطلوبة غير معروفة.")
    old_status = student.status
    if old_status == new_status:
        return student

    student.status = new_status
    student.status_changed_at = timezone.now()
    student.status_changed_by = actor
    if new_status != StudentStatus.ACTIVE:
        student.exit_date = exit_date or date.today()
        student.exit_reason = exit_reason[:300]
    else:
        student.exit_date = None
        student.exit_reason = ""
    student.save()

    # إغلاق القيود الفعالة — لا يبقى قيد ACTIVE لطالب خارج
    if new_status != StudentStatus.ACTIVE:
        close_status = _ENROLLMENT_CLOSE_MAP[new_status]
        StudentEnrollment.objects.filter(
            student=student, status=EnrollmentStatus.ACTIVE
        ).update(status=close_status, ended_at=student.exit_date, updated_at=timezone.now())

    record_event(
        AuditAction.STUDENT_STATUS_CHANGED,
        request=request,
        actor=actor,
        school=student.school,
        target_type="Student",
        target_id=student.id,
        metadata={"from": old_status, "to": new_status},
    )
    return student


def get_students_for_school(*, school, student_ids: list[int]) -> list[Student]:
    """يتحقق أن كل المعرفات تتبع المدرسة — معرف أجنبي واحد يرفض العملية كلها."""
    unique_ids = list(dict.fromkeys(student_ids))
    students = list(Student.objects.filter(school=school, id__in=unique_ids))
    if len(students) != len(unique_ids):
        raise ApiError(
            "STUDENT_NOT_FOUND",
            "بعض الطلاب المحددين غير موجودين في هذه المدرسة — أعد تحميل القائمة.",
            status_code=404,
        )
    return students


@transaction.atomic
def bulk_set_status(
    *,
    school,
    actor,
    student_ids: list[int],
    new_status: str,
    exit_reason: str = "",
    request=None,
) -> int:
    students = get_students_for_school(school=school, student_ids=student_ids)
    for student in students:
        set_student_status(
            student=student,
            new_status=new_status,
            actor=actor,
            exit_reason=exit_reason,
            request=request,
        )
    return len(students)
