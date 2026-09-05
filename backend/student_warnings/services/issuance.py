"""إصدار الإنذارات وإلغاؤها (م11) — الإصدار قرار بشري صريح، والسجل تاريخ لا يحذف.

ضمانات:
- إعادة حساب الاستحقاق خادميًا لحظة الإصدار (لا ثقة بما عرضته الواجهة — البند 45).
- ‏transaction + قيد فريد جزئي: النقر المزدوج أو طلبان متزامنان = إنذار واحد.
- ‏Snapshot كامل لحظة الإصدار: م12 تبني المستند منه وحده بلا إعادة حساب.
- الأعذار/التصحيحات اللاحقة لا تمس الإنذار الصادر — القيمة الحالية تعرض منفصلة.
"""

from django.db import IntegrityError, transaction
from django.utils import timezone as dj_timezone

from academics.models import Semester, SemesterStatus
from audit.models import AuditAction
from audit.services import record_event
from common.errors import ApiError
from devices.models import ArrivalStatus, SchoolArrival
from excuses.selectors import (
    UNEXCUSED_FULL_DAY_FILTER,
    count_excused_full_absence_days,
    count_unexcused_absent_periods,
    count_unexcused_full_absence_days,
)
from student_warnings.models import (
    StudentWarning,
    WarningLevel,
    WarningRuleType,
    WarningStatus,
)
from student_warnings.selectors.eligibility import (
    DUE,
    active_year,
    evaluate_student_warning_eligibility,
)
from student_warnings.services.rules import get_rules_map

VOID_ROLES = ("SCHOOL_MANAGER",)
WEEKDAY_NAMES = [
    "الاثنين",
    "الثلاثاء",
    "الأربعاء",
    "الخميس",
    "الجمعة",
    "السبت",
    "الأحد",
]


def _placement_snapshot(*, student, year) -> dict:
    """صف/فصل الطالب وقت الإصدار — المستند القديم لا يقرأ القيد الحالي (البند 36)."""
    enrollment = (
        student.enrollments.filter(academic_year=year)
        .select_related("grade", "section")
        .order_by("-enrolled_at")
        .first()
    )
    return {
        "student_name_snapshot": student.full_name,
        "grade_name_snapshot": enrollment.grade.name if enrollment else "",
        "section_name_snapshot": enrollment.section.name if enrollment else "",
        "national_id_masked_snapshot": student.national_id_masked,
    }


def _detail_rows_snapshot(*, school, student, year, warning_type: str) -> list[dict]:
    """تفاصيل النوع الذي أصدر الإنذار فقط، مجمدة لحظة الإصدار."""
    from attendance.models import DailyAttendanceSummary

    if warning_type == WarningRuleType.UNEXCUSED_FULL_DAY_ABSENCE:
        rows = (
            DailyAttendanceSummary.objects.filter(
                school=school,
                student=student,
                academic_year=year,
            )
            .filter(UNEXCUSED_FULL_DAY_FILTER)
            .order_by("attendance_date")
            .values("attendance_date")
        )
        return [
            {
                "date": row["attendance_date"].isoformat(),
                "weekday": WEEKDAY_NAMES[row["attendance_date"].weekday()],
                "status": "غياب يوم دراسي كامل بدون عذر",
            }
            for row in rows
        ]

    if warning_type == WarningRuleType.MORNING_LATE_OCCURRENCES:
        rows = SchoolArrival.objects.filter(
            school=school,
            student=student,
            status=ArrivalStatus.LATE,
            attendance_date__gte=year.start_date,
            attendance_date__lte=year.end_date,
        ).order_by("attendance_date")
        return [
            {
                "date": row.attendance_date.isoformat(),
                "weekday": WEEKDAY_NAMES[row.attendance_date.weekday()],
                "arrival_time": dj_timezone.localtime(row.first_arrival_at).strftime("%H:%M"),
                "late_minutes": row.counted_late_minutes,
                "status": "تأخر عن بداية الدوام الصباحي",
            }
            for row in rows
        ]
    return []


def _metrics_snapshot(*, school, student, year, warning_type: str) -> dict:
    """كل ما تحتاجه م12 لإنتاج المستند — مقاييس المرحلتين 8/8.5/10 كما هي لحظة الإصدار."""
    from django.db.models import Count, Q, Sum

    from attendance.models import DailyAbsenceStatus, DailyAttendanceSummary

    window = {
        "attendance_date__gte": year.start_date,
        "attendance_date__lte": year.end_date,
    }
    summary = DailyAttendanceSummary.objects.filter(
        school=school, student=student, academic_year=year  # نفس مرساة المقياس
    ).aggregate(
        full_days=Count("id", filter=Q(absence_status=DailyAbsenceStatus.FULL)),
        absent_periods=Sum("absent_periods"),
        period_late_occurrences=Sum("late_periods"),
        period_late_minutes=Sum("total_late_minutes"),
    )
    arrivals = SchoolArrival.objects.filter(
        school=school, student=student, status=ArrivalStatus.LATE, **window
    ).aggregate(occurrences=Count("id"), minutes=Sum("counted_late_minutes"))
    return {
        "full_absence_days_at_issue": summary["full_days"] or 0,
        "unexcused_full_absence_days_at_issue": count_unexcused_full_absence_days(
            school=school, student=student, academic_year=year
        ),
        "excused_full_absence_days_at_issue": count_excused_full_absence_days(
            school=school, student=student, academic_year=year
        ),
        "absent_periods_at_issue": summary["absent_periods"] or 0,
        "unexcused_absent_periods_at_issue": count_unexcused_absent_periods(
            school=school, student=student, academic_year=year
        ),
        # الصباحي والحصص عدادان منفصلان تمامًا — لا جمع بينهما أبدًا
        "morning_late_occurrences_at_issue": arrivals["occurrences"] or 0,
        "morning_late_minutes_at_issue": arrivals["minutes"] or 0,
        "period_late_occurrences_at_issue": summary["period_late_occurrences"] or 0,
        "period_late_minutes_at_issue": summary["period_late_minutes"] or 0,
        "detail_rows_snapshot": _detail_rows_snapshot(
            school=school,
            student=student,
            year=year,
            warning_type=warning_type,
        ),
    }


def issue_student_warning(
    *, school, membership, student, warning_type: str, level: str, notes: str = "",
    request=None,
) -> StudentWarning:
    if warning_type not in WarningRuleType.values:
        raise ApiError("WARNING_RULE_NOT_FOUND", "نوع الإنذار غير معروف.", status_code=404)
    if level not in WarningLevel.values:
        raise ApiError("WARNING_RULE_NOT_FOUND", "مستوى الإنذار غير معروف.", status_code=404)
    if student.school_id != school.id:
        raise ApiError("NOT_FOUND", "المورد المطلوب غير موجود.", status_code=404)

    year = active_year(school)
    rules = get_rules_map(school=school)
    config = rules.get(warning_type)
    if config is None:
        raise ApiError("WARNING_RULE_NOT_FOUND", "قاعدة الإنذار غير معرفة.", status_code=404)
    if not config["is_enabled"]:
        raise ApiError(
            "WARNING_TYPE_DISABLED",
            "هذا النوع من الإنذارات غير مفعّل في إعدادات المدرسة.",
            status_code=409,
        )

    # إعادة حساب لحظة الإصدار — القاعدة قد تتغير بين عرض اللوحة والضغط
    evaluation = evaluate_student_warning_eligibility(school=school, student=student, year=year)
    type_state = evaluation["types"][warning_type]
    level_state = type_state["levels"].get(level)
    if level_state is None:
        raise ApiError("WARNING_RULE_NOT_FOUND", "مستوى الإنذار غير معرف.", status_code=404)
    if level_state["state"] != DUE:
        if level_state["state"] == "ISSUED":
            raise ApiError(
                "WARNING_ALREADY_ISSUED",
                "تم إصدار هذا المستوى من الإنذار للطالب مسبقاً.",
                status_code=409,
            )
        raise ApiError(
            "WARNING_LEVEL_NOT_REACHED",
            "لم يصل الطالب بعد إلى الحد المحدد لهذا الإنذار.",
            status_code=409,
            details={
                "current_value": type_state["current_value"],
                "threshold": level_state["threshold"],
            },
        )

    semester = Semester.objects.filter(school=school, status=SemesterStatus.ACTIVE).first()
    now = dj_timezone.now()
    try:
        with transaction.atomic():
            warning = StudentWarning.objects.create(
                school=school,
                student=student,
                academic_year=year,
                semester=semester,
                warning_type=warning_type,
                level=level,
                status=WarningStatus.ISSUED,
                threshold_at_issue=level_state["threshold"],
                metric_value_at_issue=type_state["current_value"],
                issued_by_membership=membership,
                issued_at=now,
                notes=notes[:300],
                **_placement_snapshot(student=student, year=year),
                **_metrics_snapshot(
                    school=school,
                    student=student,
                    year=year,
                    warning_type=warning_type,
                ),
            )
    except IntegrityError:
        # الحكم النهائي من قاعدة البيانات (نقر مزدوج/تزامن) — إنذار واحد لا اثنان
        raise ApiError(
            "WARNING_ALREADY_ISSUED",
            "تم إصدار هذا المستوى من الإنذار للطالب مسبقاً.",
            status_code=409,
        ) from None

    record_event(
        AuditAction.STUDENT_WARNING_ISSUED,
        request=request,
        actor=membership.user,
        school=school,
        target_type="StudentWarning",
        target_id=warning.id,
        metadata={  # بلا اسم/هوية — المعرفات والأرقام فقط
            "student_id": student.id,
            "warning_type": warning_type,
            "level": level,
            "threshold_at_issue": warning.threshold_at_issue,
            "metric_value_at_issue": warning.metric_value_at_issue,
        },
    )
    return warning


def void_student_warning(*, school, membership, warning, reason: str, request=None):
    if warning.school_id != school.id:
        raise ApiError("WARNING_NOT_FOUND", "الإنذار غير موجود.", status_code=404)
    with transaction.atomic():
        locked = StudentWarning.objects.select_for_update().get(id=warning.id)
        if locked.status == WarningStatus.VOIDED:
            raise ApiError(
                "WARNING_ALREADY_VOIDED", "تم إلغاء هذا الإنذار مسبقاً.", status_code=409
            )
        locked.status = WarningStatus.VOIDED
        locked.voided_by_membership = membership
        locked.voided_at = dj_timezone.now()
        locked.void_reason = reason[:300]
        locked.save(
            update_fields=[
                "status", "voided_by_membership", "voided_at", "void_reason", "updated_at",
            ]
        )
    record_event(
        AuditAction.STUDENT_WARNING_VOIDED,
        request=request,
        actor=membership.user,
        school=school,
        target_type="StudentWarning",
        target_id=locked.id,
        metadata={"student_id": locked.student_id, "level": locked.level},
    )
    return locked
