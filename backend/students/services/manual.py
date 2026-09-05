"""إنشاء طالب يدويًا مع نفس ضمانات الأمان والعزل المستخدمة في الاستيراد."""

from datetime import date

from django.db import IntegrityError, transaction

from audit.models import AuditAction
from audit.services import record_event
from common.errors import ApiError
from common.security.identifiers import (
    encrypt_national_id,
    mask_national_id,
    national_id_lookup_hash,
)
from students.models import Student, StudentEnrollment


@transaction.atomic
def create_student(
    *, school, academic_year, section, data: dict, actor, request=None
) -> Student:
    from subscriptions.entitlements import lock_school_capacity, require_capacity
    from subscriptions.models import EntitlementKey
    from subscriptions.usage import count_active_students

    lock_school_capacity(school)
    require_capacity(
        school,
        EntitlementKey.MAX_STUDENTS,
        current=count_active_students(school),
        adding=1,
    )

    national_id = data["national_id"]
    lookup_hash = national_id_lookup_hash(national_id)
    if Student.objects.filter(school=school, national_id_lookup_hash=lookup_hash).exists():
        raise ApiError("STUDENT_ALREADY_EXISTS", "يوجد طالب مسجل برقم الهوية هذا.", 409)

    student_number = data.get("student_number") or None
    if student_number and Student.objects.filter(
        school=school, student_number=student_number
    ).exists():
        raise ApiError("STUDENT_NUMBER_ALREADY_EXISTS", "رقم الطالب مستخدم مسبقًا.", 409)

    try:
        with transaction.atomic():
            student = Student.objects.create(
                school=school,
                national_id_encrypted=encrypt_national_id(national_id),
                national_id_lookup_hash=lookup_hash,
                national_id_masked=mask_national_id(national_id),
                student_number=student_number,
                full_name=data["full_name"],
                guardian_name=data.get("guardian_name", ""),
                guardian_mobile=data.get("guardian_mobile", ""),
            )
            enrollment = StudentEnrollment.objects.create(
                school=school,
                student=student,
                academic_year=academic_year,
                grade=section.grade,
                section=section,
                enrolled_at=date.today(),
            )
    except IntegrityError as exc:
        raise ApiError(
            "STUDENT_ALREADY_EXISTS",
            "تعذر إنشاء الطالب؛ رقم الهوية أو رقم الطالب مستخدم مسبقًا.",
            409,
        ) from exc

    record_event(
        AuditAction.STUDENT_CREATED,
        request=request,
        actor=actor,
        school=school,
        target_type="Student",
        target_id=student.id,
        metadata={"source": "MANUAL"},
    )
    record_event(
        AuditAction.STUDENT_ENROLLMENT_CREATED,
        request=request,
        actor=actor,
        school=school,
        target_type="StudentEnrollment",
        target_id=enrollment.id,
        metadata={"grade_id": section.grade_id, "section_id": section.id},
    )
    return student
