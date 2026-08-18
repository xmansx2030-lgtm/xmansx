"""خدمات القيد الدراسي — school صريح دائمًا، وتكامل المستأجر محقق."""

from common.errors import ApiError
from students.models import EnrollmentStatus, StudentEnrollment


def get_current_enrollment(*, student, academic_year) -> StudentEnrollment | None:
    """القيد الفعال للطالب في عام — المصدر الموحد (لا تكرار للمنطق)."""
    return (
        StudentEnrollment.objects.filter(
            student=student, academic_year=academic_year, status=EnrollmentStatus.ACTIVE
        )
        .select_related("grade", "section")
        .first()
    )


def students_for_section(*, school, section, academic_year):
    """طلاب فصل في عام — سيستخدمه الحضور (المرحلة 6). Query موحد جاهز."""
    if section.school_id != school.id:
        raise ApiError("VALIDATION_ERROR", "الفصل لا يتبع هذه المدرسة.", status_code=404)
    return (
        StudentEnrollment.objects.filter(
            school=school,
            section=section,
            academic_year=academic_year,
            status=EnrollmentStatus.ACTIVE,
        )
        .select_related("student")
        .order_by("student__full_name")
    )


def validate_enrollment_integrity(*, school, student, grade, section, academic_year) -> None:
    """كل الأطراف من نفس المدرسة — Cross-Tenant FK ممنوع حتى بمعرفات يدوية."""
    for obj, label in (
        (student, "الطالب"),
        (grade, "الصف"),
        (section, "الفصل"),
        (academic_year, "العام الدراسي"),
    ):
        if obj.school_id != school.id:
            raise ApiError("INVALID_ENROLLMENT", f"{label} لا يتبع هذه المدرسة.", status_code=400)
    if section.grade_id != grade.id:
        raise ApiError("INVALID_ENROLLMENT", "الفصل لا يتبع هذا الصف.", status_code=400)
