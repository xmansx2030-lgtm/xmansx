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
from students.models import EnrollmentStatus, Student, StudentEnrollment


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


@transaction.atomic
def update_student(
    *, school, student_id: int, academic_year, section, data: dict, actor, request=None
) -> Student:
    """تصحيح بيانات طالب يدويًا مع حفظ الهوية مشفرة وتاريخ القيد."""
    student = Student.objects.select_for_update().get(id=student_id, school=school)
    changed_fields: list[str] = []

    national_id = data.get("national_id")
    if national_id:
        lookup_hash = national_id_lookup_hash(national_id)
        if lookup_hash != student.national_id_lookup_hash:
            if Student.objects.filter(
                school=school, national_id_lookup_hash=lookup_hash
            ).exclude(id=student.id).exists():
                raise ApiError(
                    "STUDENT_ALREADY_EXISTS",
                    "يوجد طالب مسجل برقم الهوية/الإقامة هذا.",
                    409,
                )
            student.national_id_encrypted = encrypt_national_id(national_id)
            student.national_id_lookup_hash = lookup_hash
            student.national_id_masked = mask_national_id(national_id)
            changed_fields.append("national_id")

    if "student_number" in data:
        student_number = data["student_number"] or None
        if student_number != student.student_number:
            if student_number and Student.objects.filter(
                school=school, student_number=student_number
            ).exclude(id=student.id).exists():
                raise ApiError(
                    "STUDENT_NUMBER_ALREADY_EXISTS",
                    "رقم الطالب مستخدم مسبقًا.",
                    409,
                )
            student.student_number = student_number
            changed_fields.append("student_number")

    for field in ("full_name", "guardian_name", "guardian_mobile"):
        if field in data and getattr(student, field) != data[field]:
            setattr(student, field, data[field])
            changed_fields.append(field)

    try:
        if changed_fields:
            student.save()
    except IntegrityError as exc:
        raise ApiError(
            "STUDENT_ALREADY_EXISTS",
            "تعذر تحديث الطالب؛ رقم الهوية/الإقامة أو رقم الطالب مستخدم مسبقًا.",
            409,
        ) from exc

    enrollment_changed = False
    if section is not None:
        current = (
            StudentEnrollment.objects.select_for_update()
            .filter(
                school=school,
                student=student,
                academic_year=academic_year,
                status=EnrollmentStatus.ACTIVE,
            )
            .first()
        )
        if current is None:
            new_enrollment = StudentEnrollment.objects.create(
                school=school,
                student=student,
                academic_year=academic_year,
                grade=section.grade,
                section=section,
                enrolled_at=date.today(),
            )
            enrollment_changed = True
        elif current.section_id != section.id:
            current.status = EnrollmentStatus.TRANSFERRED
            current.ended_at = date.today()
            current.save(update_fields=["status", "ended_at", "updated_at"])
            record_event(
                AuditAction.STUDENT_ENROLLMENT_ENDED,
                request=request,
                actor=actor,
                school=school,
                target_type="StudentEnrollment",
                target_id=current.id,
                metadata={"reason": "MANUAL_CORRECTION"},
            )
            new_enrollment = StudentEnrollment.objects.create(
                school=school,
                student=student,
                academic_year=academic_year,
                grade=section.grade,
                section=section,
                enrolled_at=date.today(),
            )
            enrollment_changed = True
        if enrollment_changed:
            record_event(
                AuditAction.STUDENT_ENROLLMENT_CREATED,
                request=request,
                actor=actor,
                school=school,
                target_type="StudentEnrollment",
                target_id=new_enrollment.id,
                metadata={"grade_id": section.grade_id, "section_id": section.id},
            )

    if changed_fields or enrollment_changed:
        audit_fields = sorted(changed_fields + (["section"] if enrollment_changed else []))
        record_event(
            AuditAction.STUDENT_UPDATED,
            request=request,
            actor=actor,
            school=school,
            target_type="Student",
            target_id=student.id,
            metadata={"changed_fields": audit_fields},
        )
    return student
