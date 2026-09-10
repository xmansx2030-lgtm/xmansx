"""استعلامات دليل الموظفين — بلا N+1، وبحث محدود (لا Global User Search)."""

from django.core.exceptions import ValidationError
from django.db.models import Prefetch, Q

from accounts.mobile import normalize_mobile
from memberships.models import SchoolMembership
from staff.models import CounselorSectionAssignment, StaffProfile

COUNSELOR_SECTIONS_PREFETCH = Prefetch(
    "membership__counselor_section_assignments",
    queryset=CounselorSectionAssignment.objects.select_related("section__grade"),
)


def staff_queryset(*, school, search: str = "", role: str = "", status: str = ""):
    queryset = (
        StaffProfile.objects.filter(school=school)
        .select_related("membership__user")
        .prefetch_related(
            "membership__roles",
            "membership__capabilities",
            COUNSELOR_SECTIONS_PREFETCH,
        )
        .order_by("display_name")
    )
    if search:
        filters = Q(display_name__icontains=search) | Q(employee_number=search)
        # الجوال: مطابقة تامة فقط (بعد التطبيع) — لا بحث جزئي بالأرقام
        try:
            filters |= Q(membership__user__mobile=normalize_mobile(search))
        except ValidationError:
            pass
        queryset = queryset.filter(filters)
    if role:
        queryset = queryset.filter(membership__roles__role=role)
    if status:
        queryset = queryset.filter(membership__status=status)
    return queryset.distinct()


def get_current_staff_profile(*, user, school) -> StaffProfile | None:
    """Selector موحد — ستحتاجه شاشة الحضور (المرحلة 6) لهوية المعلم داخل المدرسة."""
    membership = SchoolMembership.objects.filter(user=user, school=school).first()
    if membership is None:
        return None
    return getattr(membership, "staff_profile", None)
