"""استعلامات قوائم الطلاب — بلا N+1، والبحث بالهوية عبر HMAC حصرًا."""

from django.core.exceptions import ValidationError
from django.db.models import Prefetch

from common.security.identifiers import national_id_lookup_hash, normalize_national_id
from students.models import EnrollmentStatus, Student, StudentEnrollment


def students_queryset(*, school, academic_year=None, search: str = "",
                      national_id: str = "", grade_id=None, section_id=None, status=""):
    """قائمة الطلاب مع القيد الفعال (صف/فصل) بثلاثة استعلامات ثابتة."""
    queryset = Student.objects.filter(school=school)

    if status:
        queryset = queryset.filter(status=status)
    if search:
        queryset = queryset.filter(full_name__icontains=search)
    if national_id:
        # بحث دقيق عبر HMAC — لا contains على قيمة مشفرة
        try:
            normalized = normalize_national_id(national_id)
        except ValidationError:
            return queryset.none()
        queryset = queryset.filter(
            national_id_lookup_hash=national_id_lookup_hash(normalized)
        )

    active_enrollments = StudentEnrollment.objects.filter(
        status=EnrollmentStatus.ACTIVE
    ).select_related("grade", "section")
    if academic_year is not None:
        active_enrollments = active_enrollments.filter(academic_year=academic_year)
    if grade_id:
        queryset = queryset.filter(
            enrollments__grade_id=grade_id, enrollments__status=EnrollmentStatus.ACTIVE
        )
    if section_id:
        queryset = queryset.filter(
            enrollments__section_id=section_id, enrollments__status=EnrollmentStatus.ACTIVE
        )

    return (
        queryset.distinct()
        .prefetch_related(
            Prefetch("enrollments", queryset=active_enrollments, to_attr="active_enrollments")
        )
        .order_by("full_name")
    )
