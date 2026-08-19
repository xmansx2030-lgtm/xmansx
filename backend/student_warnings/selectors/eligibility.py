"""اكتشاف استحقاق الإنذارات (م11) — مشتق بالكامل، بلا صفوف تنبيه ولا Audit.

المقاييس (لا تعاد صياغتها هنا — مصدرها م8/م8.5/م10):
- الغياب: أيام «كامل بدون عذر» عبر فلتر م10 المرجعي `UNEXCUSED_FULL_DAY_FILTER`
  (‏FULL + excused=0 + unexcused>0). المستثنى صراحة: بعذر، جزئي، غير محسوم،
  والمختلط (البند 4 — قرار MVP موثق).
- التأخر: عدد مرات `SchoolArrival.status = LATE` (م8.5) — **لا دقائق ولا تأخر حصص**
  (‏AttendanceMark.LATE يبقى منفصلًا تمامًا: البندان 6 و107).

النطاق: نافذة العام الدراسي النشط [start_date, end_date] — القرار وأدلته في
docs/WARNING_RULES.md. الأداء: استعلامات مجمعة ثابتة العدد مهما بلغ عدد الطلاب.
"""

from django.db.models import Count

from academics.models import AcademicYear, AcademicYearStatus
from attendance.models import DailyAttendanceSummary
from common.errors import ApiError
from devices.models import ArrivalStatus, SchoolArrival
from excuses.selectors import UNEXCUSED_FULL_DAY_FILTER
from student_warnings.models import (
    LEVEL_ORDER,
    StudentWarning,
    WarningRuleType,
    WarningStatus,
)
from student_warnings.services.rules import get_rules_map
from students.models import EnrollmentStatus, Student, StudentEnrollment

DUE = "DUE"
NOT_DUE = "NOT_DUE"
ISSUED = "ISSUED"


def active_year(school) -> AcademicYear:
    year = AcademicYear.objects.filter(
        school=school, status=AcademicYearStatus.ACTIVE
    ).first()
    if year is None:
        raise ApiError(
            "ACTIVE_ACADEMIC_YEAR_REQUIRED",
            "لم يتم العثور على عام دراسي نشط لهذه المدرسة.",
            status_code=409,
        )
    return year


def metric_for_students(*, school, year, rule_type: str, student_ids=None) -> dict[int, int]:
    """قيمة المقياس لكل طالب — استعلام تجميعي واحد (لا N+1 مهما كان العدد)."""
    if rule_type == WarningRuleType.UNEXCUSED_FULL_DAY_ABSENCE:
        # مرساة العام هي FK الملخص نفسه — أدق من نافذة التواريخ (صف الملخص يحمل
        # عامه الدراسي وقت التسجيل، فلا يتأثر بحدود تقويم غير مضبوطة)
        rows = DailyAttendanceSummary.objects.filter(school=school, academic_year=year)
        if student_ids is not None:
            rows = rows.filter(student_id__in=student_ids)
        return {
            row["student_id"]: row["value"]
            for row in rows.values("student_id").annotate(
                value=Count("id", filter=UNEXCUSED_FULL_DAY_FILTER)
            )
            if row["value"]
        }
    if rule_type == WarningRuleType.MORNING_LATE_OCCURRENCES:
        # ‏SchoolArrival بلا FK للعام (م8.5) — نافذة تواريخ العام هي المرساة الوحيدة
        rows = SchoolArrival.objects.filter(
            school=school,
            status=ArrivalStatus.LATE,  # الوصول في الوقت لا يحتسب
            attendance_date__gte=year.start_date,
            attendance_date__lte=year.end_date,
        )
        if student_ids is not None:
            rows = rows.filter(student_id__in=student_ids)
        return {
            row["student_id"]: row["value"]
            for row in rows.values("student_id").annotate(value=Count("id"))
            if row["value"]
        }
    raise ApiError("WARNING_RULE_NOT_FOUND", "نوع الإنذار غير معروف.", status_code=404)


def _levels_state(*, value: int, thresholds: dict, issued_levels: set) -> dict:
    """حالة كل مستوى: صادر / مستحق / غير مستحق + أعلى مستوى بلغه الطالب وأعلى مستحق."""
    levels = {}
    highest_reached = None
    highest_due = None
    for level in LEVEL_ORDER:
        threshold = thresholds.get(level)
        if threshold is None:
            continue
        reached = value >= threshold
        if reached:
            highest_reached = level
        if level in issued_levels:
            state = ISSUED
        elif reached:
            state = DUE
            highest_due = level  # الأعلى لأن الترتيب تصاعدي
        else:
            state = NOT_DUE
        levels[level] = {"threshold": threshold, "state": state}
    return {
        "levels": levels,
        "highest_reached_level": highest_reached,
        "highest_due_level": highest_due,
    }


def issued_levels_map(*, school, year, student_ids=None) -> dict[tuple[int, str], set]:
    """المستويات الصادرة (غير الملغاة) لكل (طالب، نوع) — استعلام واحد.

    الملغى لا يحجز المستوى (سياسة موثقة: يسمح بإعادة الإصدار بعد تصحيح الخطأ).
    """
    rows = StudentWarning.objects.filter(
        school=school, academic_year=year, status=WarningStatus.ISSUED
    )
    if student_ids is not None:
        rows = rows.filter(student_id__in=student_ids)
    result: dict[tuple[int, str], set] = {}
    for student_id, warning_type, level in rows.values_list(
        "student_id", "warning_type", "level"
    ):
        result.setdefault((student_id, warning_type), set()).add(level)
    return result


def evaluate_student_warning_eligibility(*, school, student, year=None) -> dict:
    """تقييم طالب واحد — يستخدم عند الإصدار (إعادة حساب خادمية، لا ثقة بالواجهة)."""
    year = year or active_year(school)
    rules = get_rules_map(school=school)
    issued = issued_levels_map(school=school, year=year, student_ids=[student.id])
    result = {"academic_year_id": year.id, "types": {}}
    for rule_type, config in rules.items():
        value = metric_for_students(
            school=school, year=year, rule_type=rule_type, student_ids=[student.id]
        ).get(student.id, 0)
        state = _levels_state(
            value=value,
            thresholds=config["levels"],
            issued_levels=issued.get((student.id, rule_type), set()),
        )
        result["types"][rule_type] = {
            "is_enabled": config["is_enabled"],
            "current_value": value,
            **state,
        }
    return result


def eligibility_dashboard(
    *,
    school,
    rule_type: str | None = None,
    grade_id: int | None = None,
    section_id: int | None = None,
    status_filter: str = "due",
    page: int = 1,
    page_size: int = 25,
) -> dict:
    """قائمة «يحتاج متابعة» — المقاييس أولًا ثم بيانات المرشحين فقط.

    الترتيب مقصود للأداء: التجميع يعيد الطلاب ذوي القيمة > 0 فقط (نسبة صغيرة)،
    فلا نحمّل قيود وأسماء كل طلاب المدرسة (قياس: 1.4s → عشرات المللي ثانية عند 5000).
    """
    year = active_year(school)
    rules = get_rules_map(school=school)
    types = [rule_type] if rule_type else list(rules)

    values_by_type = {
        current_type: metric_for_students(
            school=school, year=year, rule_type=current_type
        )
        for current_type in types
        if current_type in rules
    }
    candidate_ids = {
        student_id for values in values_by_type.values() for student_id in values
    }
    if not candidate_ids:
        return {
            "academic_year": {"id": year.id, "name": year.name},
            "summary": {t: {"due_students": 0, "issued_students": 0} for t in types},
            "results": [], "count": 0, "page": max(page, 1),
            "page_size": page_size if page_size in (25, 50, 100) else 25,
        }

    # القيد الفعال يحدد الصف/الفصل ويستبعد غير المنتظمين — والفلاتر تطبق هنا
    enrollments = StudentEnrollment.objects.filter(
        school=school, academic_year=year, status=EnrollmentStatus.ACTIVE,
        student_id__in=candidate_ids,
    ).select_related("grade", "section")
    if grade_id:
        enrollments = enrollments.filter(grade_id=grade_id)
    if section_id:
        enrollments = enrollments.filter(section_id=section_id)
    placement = {row.student_id: row for row in enrollments}
    names = dict(
        Student.objects.filter(id__in=list(placement), status="ACTIVE").values_list(
            "id", "full_name"
        )
    )
    issued = issued_levels_map(school=school, year=year, student_ids=list(names))

    rows = []
    summary = {t: {"due_students": 0, "issued_students": 0} for t in types}
    for current_type in types:
        config = rules.get(current_type)
        if config is None:
            continue
        values = values_by_type.get(current_type, {})
        for student_id, full_name in names.items():
            value = values.get(student_id, 0)
            if value == 0:
                continue
            issued_for = issued.get((student_id, current_type), set())
            state = _levels_state(
                value=value, thresholds=config["levels"], issued_levels=issued_for
            )
            if state["highest_reached_level"] is None:
                continue
            if state["highest_due_level"] is not None:
                summary[current_type]["due_students"] += 1
            if issued_for:
                summary[current_type]["issued_students"] += 1
            if status_filter == "due" and state["highest_due_level"] is None:
                continue
            if status_filter == "issued" and not issued_for:
                continue
            enrollment = placement[student_id]
            rows.append(
                {
                    "student_id": student_id,
                    "full_name": full_name,
                    "grade_id": enrollment.grade_id,
                    "grade_name": enrollment.grade.name,
                    "section_name": enrollment.section.name,
                    "warning_type": current_type,
                    "is_enabled": config["is_enabled"],
                    "current_value": value,
                    "highest_reached_level": state["highest_reached_level"],
                    "highest_due_level": state["highest_due_level"],
                    "issued_levels": sorted(issued_for),
                    "levels": state["levels"],
                    "_sort": (
                        enrollment.grade.sequence,
                        enrollment.section.code,
                        full_name,
                    ),
                }
            )
    rows.sort(key=lambda row: (row["warning_type"], row["_sort"]))
    for row in rows:
        del row["_sort"]

    total = len(rows)
    page = max(page, 1)
    page_size = page_size if page_size in (25, 50, 100) else 25
    start = (page - 1) * page_size
    return {
        "academic_year": {"id": year.id, "name": year.name},
        "summary": summary,
        "results": rows[start : start + page_size],
        "count": total,
        "page": page,
        "page_size": page_size,
    }


def get_warning_current_metric(*, warning: StudentWarning) -> int:
    """القيمة الحالية للمقياس نفسه (drift) — لا تمس Snapshot أبدًا (البند 55)."""
    return metric_for_students(
        school=warning.school,
        year=warning.academic_year,
        rule_type=warning.warning_type,
        student_ids=[warning.student_id],
    ).get(warning.student_id, 0)
