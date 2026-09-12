"""Read-only setup readiness for a newly provisioned school.

The dashboard must not infer operational readiness from the absence of errors.
This selector keeps the prerequisites tenant-scoped and returns no counts or
sensitive records, only the ordered steps a school manager can act on.
"""

from academics.models import (
    AcademicYear,
    AcademicYearStatus,
    BellSchedule,
    BellScheduleStatus,
    SchoolWeekDay,
    Semester,
    SemesterStatus,
)
from memberships.models import (
    MembershipStatus,
    SchoolMembershipRole,
    SchoolRole,
)
from schools.role_labels import school_students_label
from students.models import EnrollmentStatus, Section, StudentEnrollment, StudentStatus


def setup_readiness(*, school) -> dict:
    """Return the ordered, actionable prerequisites for live school operation."""
    active_year = (
        AcademicYear.objects.filter(school=school, status=AcademicYearStatus.ACTIVE)
        .only("id")
        .first()
    )
    has_active_year = active_year is not None
    has_active_semester = bool(
        active_year
        and Semester.objects.filter(
            school=school,
            academic_year=active_year,
            status=SemesterStatus.ACTIVE,
        ).exists()
    )
    has_structure = Section.objects.filter(
        school=school,
        is_active=True,
        grade__is_active=True,
    ).exists()

    usable_schedule_ids = BellSchedule.objects.filter(
        school=school,
        status=BellScheduleStatus.ACTIVE,
        periods__is_attendance_period=True,
    ).values("id")
    has_usable_schedule = usable_schedule_ids.exists()
    school_days = SchoolWeekDay.objects.filter(school=school, is_school_day=True)
    school_day_count = school_days.count()
    mapped_school_day_count = school_days.filter(
        bell_schedule_id__in=usable_schedule_ids,
    ).count()
    has_mapped_school_day = (
        has_usable_schedule
        and school_day_count > 0
        and mapped_school_day_count == school_day_count
    )
    has_students = bool(
        active_year
        and StudentEnrollment.objects.filter(
            school=school,
            academic_year=active_year,
            status=EnrollmentStatus.ACTIVE,
            student__status=StudentStatus.ACTIVE,
        ).exists()
    )
    has_teachers = SchoolMembershipRole.objects.filter(
        membership__school=school,
        membership__status=MembershipStatus.ACTIVE,
        role=SchoolRole.TEACHER,
    ).exists()

    year_block = None if has_active_year else "فعّل العام الدراسي أولًا."
    schedule_href = (
        "/settings?section=week-days"
        if has_usable_schedule
        else "/settings?section=bell-schedules"
    )
    students_label = school_students_label(school.school_type)
    steps = [
        {
            "key": "academic_year",
            "label": "تفعيل العام الدراسي",
            "description": "أنشئ العام الدراسي ثم فعّله ليصبح السياق التشغيلي للمدرسة.",
            "complete": has_active_year,
            "href": "/settings?section=calendar",
            "actionable": True,
            "blocked_reason": None,
        },
        {
            "key": "semester",
            "label": "تفعيل الفصل الدراسي",
            "description": "أضف الفصل الحالي وفعّله داخل العام الدراسي النشط.",
            "complete": has_active_semester,
            "href": "/settings?section=calendar",
            "actionable": has_active_year,
            "blocked_reason": year_block,
        },
        {
            "key": "structure",
            "label": "تجهيز الصفوف والفصول",
            "description": "أضف هيكل المدرسة يدويًا أو أنشئه أثناء استيراد البيانات.",
            "complete": has_structure,
            "href": "/settings?section=structure",
            "actionable": has_active_year,
            "blocked_reason": year_block,
        },
        {
            "key": "schedule",
            "label": (
                "ربط الجدول بأيام الدوام"
                if has_usable_schedule
                else "إعداد جدول الحصص"
            ),
            "description": "أنشئ حصص التحضير واربط جدولًا صالحًا بجميع أيام الدوام.",
            "complete": has_mapped_school_day,
            "href": schedule_href,
            "actionable": has_active_year,
            "blocked_reason": year_block,
        },
        {
            "key": "students",
            "label": f"إضافة بيانات {students_label}",
            "description": f"استورد {students_label} واربطهم بالعام الدراسي النشط.",
            "complete": has_students,
            "href": "/students/import",
            "actionable": has_active_year,
            "blocked_reason": year_block,
        },
        {
            "key": "teachers",
            "label": "إضافة الكادر التعليمي",
            "description": "استورد حسابات المعلمين أو أضفها يدويًا لبدء التحضير.",
            "complete": has_teachers,
            "href": "/staff/import",
            "actionable": True,
            "blocked_reason": None,
        },
    ]
    completed_steps = sum(step["complete"] for step in steps)
    return {
        "ready": completed_steps == len(steps),
        "completed_steps": completed_steps,
        "total_steps": len(steps),
        "steps": steps,
    }
