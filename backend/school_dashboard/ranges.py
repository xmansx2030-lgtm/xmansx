"""نطاقات التاريخ والسياق الأكاديمي للوحة الإدارة (م15).

قواعد ثابتة:
- «اليوم» دائمًا بتوقيت المدرسة (`school_now`) لا بتوقيت الخادم ولا المتصفح.
- المقارنة مع فترة سابقة **مساوية في الطول** وملاصقة لها — ولا تُقارن فترات
  غير متساوية بصمت (بند 11): الاستجابة تحمل طول كل فترة صراحة.
- لا قسمة على صفر: أساس صفري يعيد `change_pct = None` مع `is_new` (بند 57).
"""

from dataclasses import dataclass
from datetime import date, timedelta

from attendance.services.periods import school_now
from common.errors import ApiError

#: سقف النطاق — عامان دراسيان تقريبًا (بند 106)
MAX_RANGE_DAYS = 760

PRESETS = (
    "TODAY",
    "LAST_7_DAYS",
    "LAST_30_DAYS",
    "THIS_WEEK",
    "THIS_MONTH",
    "CURRENT_SEMESTER",
    "CUSTOM",
)

#: الأحد أول أيام الأسبوع الدراسي (weekday(): الاثنين=0 … الأحد=6)
_SUNDAY = 6


@dataclass(frozen=True)
class DateRange:
    """نطاق مغلق الطرفين [from_date, to_date]."""

    from_date: date
    to_date: date
    preset: str

    @property
    def days(self) -> int:
        return (self.to_date - self.from_date).days + 1

    def previous(self) -> "DateRange":
        """الفترة السابقة الملاصقة بنفس الطول تمامًا."""
        length = self.days
        end = self.from_date - timedelta(days=1)
        return DateRange(end - timedelta(days=length - 1), end, self.preset)

    def as_dict(self) -> dict:
        return {
            "from_date": self.from_date.isoformat(),
            "to_date": self.to_date.isoformat(),
            "days": self.days,
            "preset": self.preset,
        }


def _week_start(day: date) -> date:
    """بداية الأسبوع الدراسي (الأحد) لليوم المعطى."""
    return day - timedelta(days=(day.weekday() - _SUNDAY) % 7)


def _parse(value: str, field: str) -> date:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise ApiError(
            "DASHBOARD_INVALID_DATE_RANGE",
            "صيغة التاريخ غير صحيحة (YYYY-MM-DD).",
            details={"field": field},
        ) from None


def resolve_range(*, school, params) -> DateRange:
    """يحل النطاق من preset أو من from_date/to_date صريحين."""
    today = school_now(school).date()
    preset = (params.get("preset") or "").upper()

    if not preset and (params.get("from_date") or params.get("to_date")):
        preset = "CUSTOM"
    if not preset:
        preset = "TODAY"
    if preset not in PRESETS:
        raise ApiError(
            "DASHBOARD_INVALID_DATE_RANGE",
            "الفترة المحددة غير معروفة.",
            details={"field": "preset"},
        )

    if preset == "TODAY":
        return DateRange(today, today, preset)
    if preset == "LAST_7_DAYS":
        return DateRange(today - timedelta(days=6), today, preset)
    if preset == "LAST_30_DAYS":
        return DateRange(today - timedelta(days=29), today, preset)
    if preset == "THIS_WEEK":
        return DateRange(_week_start(today), today, preset)
    if preset == "THIS_MONTH":
        return DateRange(today.replace(day=1), today, preset)
    if preset == "CURRENT_SEMESTER":
        return _semester_range(school=school, today=today)

    from_date = _parse(params.get("from_date"), "from_date")
    to_date = _parse(params.get("to_date"), "to_date")
    if from_date > to_date:
        raise ApiError(
            "DASHBOARD_INVALID_DATE_RANGE",
            "تاريخ البداية بعد تاريخ النهاية.",
            details={"field": "from_date"},
        )
    if (to_date - from_date).days + 1 > MAX_RANGE_DAYS:
        raise ApiError(
            "DASHBOARD_RANGE_TOO_LARGE",
            f"النطاق يتجاوز الحد المسموح ({MAX_RANGE_DAYS} يومًا).",
            details={"max_days": MAX_RANGE_DAYS},
        )
    return DateRange(from_date, to_date, preset)


def _semester_range(*, school, today: date) -> DateRange:
    """الفصل الدراسي النشط — وإلا العام النشط، وإلا آخر 30 يومًا."""
    from academics.models import AcademicYear, AcademicYearStatus, Semester, SemesterStatus

    semester = Semester.objects.filter(
        school=school, status=SemesterStatus.ACTIVE
    ).first()
    if semester is not None:
        return DateRange(semester.start_date, min(semester.end_date, today), "CURRENT_SEMESTER")
    year = AcademicYear.objects.filter(
        school=school, status=AcademicYearStatus.ACTIVE
    ).first()
    if year is not None:
        return DateRange(year.start_date, min(year.end_date, today), "CURRENT_SEMESTER")
    return DateRange(today - timedelta(days=29), today, "CURRENT_SEMESTER")


def resolve_scope(*, school, params) -> dict:
    """فلاتر الصف/الفصل — معرف من مدرسة أخرى يُرفض ولا يُتجاهل بصمت (بند 90)."""
    from students.models import Grade, Section

    scope = {"grade_id": None, "section_id": None}
    grade_raw = params.get("grade")
    if grade_raw:
        grade_id = _int_or_error(grade_raw, "DASHBOARD_INVALID_GRADE", "grade")
        if not Grade.objects.filter(school=school, id=grade_id).exists():
            raise ApiError(
                "DASHBOARD_INVALID_GRADE", "الصف غير موجود.", status_code=404
            )
        scope["grade_id"] = grade_id

    section_raw = params.get("section")
    if section_raw:
        section_id = _int_or_error(section_raw, "DASHBOARD_INVALID_SECTION", "section")
        section = Section.objects.filter(school=school, id=section_id).first()
        if section is None:
            raise ApiError(
                "DASHBOARD_INVALID_SECTION", "الفصل غير موجود.", status_code=404
            )
        if scope["grade_id"] is not None and section.grade_id != scope["grade_id"]:
            raise ApiError(
                "DASHBOARD_INVALID_SECTION",
                "الفصل لا ينتمي إلى الصف المحدد.",
                details={"section": section_id},
            )
        scope["section_id"] = section_id
    return scope


def _int_or_error(value, code: str, field: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ApiError(code, "قيمة الفلتر غير صحيحة.", details={"field": field}) from None


def compare(current: int | float, previous: int | float) -> dict:
    """مقارنة فترتين — تُحسب في الخادم لا في الواجهة (بند 58)."""
    delta = current - previous
    if previous == 0:
        # لا +∞%: قيمة جديدة بلا أساس للمقارنة (بند 57)
        return {
            "current": current,
            "previous": previous,
            "delta": delta,
            "change_pct": None,
            "is_new": current > 0,
        }
    return {
        "current": current,
        "previous": previous,
        "delta": delta,
        "change_pct": round((delta / previous) * 100, 1),
        "is_new": False,
    }


def academic_context(school) -> dict:
    """العام/الفصل النشط والمنطقة الزمنية — تُعرض صراحة مع كل استجابة."""
    from academics.models import AcademicYear, AcademicYearStatus, Semester, SemesterStatus
    from schools.services.settings import get_or_create_settings

    year = AcademicYear.objects.filter(
        school=school, status=AcademicYearStatus.ACTIVE
    ).first()
    semester = Semester.objects.filter(
        school=school, status=SemesterStatus.ACTIVE
    ).first()
    return {
        "academic_year": {"id": year.id, "name": year.name} if year else None,
        "semester": {"id": semester.id, "name": semester.name} if semester else None,
        "timezone": get_or_create_settings(school=school).timezone,
        "today": school_now(school).date().isoformat(),
    }
