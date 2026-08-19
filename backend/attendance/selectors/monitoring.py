"""لوحة متابعة تحضير الحصة الحالية (م7) — حالة مشتقة بالكامل، لا صفوف تنشأ.

القرارات الموثقة:
- NOT_STARTED اشتقاق: الفصول المتوقعة ناقص الجلسات الموجودة — ممنوع إنشاء جلسات
  فارغة لتمثيلها.
- الفصل المتوقع تحضيره = فعال + فيه طالب ACTIVE واحد على الأقل بقيد ACTIVE في
  العام النشط. الفصل الفارغ (أو بعد Purge كامل طلابه) خارج الإجمالي — لا معنى
  لمساءلة تحضير فصل بلا طلاب.
- SUBMITTED/IN_PROGRESS تُقيّم من snapshots الجلسة (البداية والمهلة وقت الفتح)؛
  NOT_STARTED من الحصة الحالية والإعداد الحالي (لا جلسة تثبت شيئًا).
- لا حصة حالية → لوحة فارغة بلا تنبيهات (وليس خطأ) — قبل الدوام/الفسحة/العطلة.
- عدد الاستعلامات ثابت مهما بلغ عدد الفصول (لا استعلام لكل فصل).
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from django.db.models import Count, Q

from attendance.models import AttendanceSession, AttendanceSessionStatus
from attendance.services.periods import get_current_attendance_period, school_now
from attendance.services.sessions import _active_year
from attendance.services.timing import alert_at_for, overdue_minutes, session_alert_at
from schools.services.settings import get_or_create_settings
from students.models import EnrollmentStatus, Section

NOT_STARTED = "NOT_STARTED"
ON_TIME = "ON_TIME"
OVERDUE = "OVERDUE"

# ترتيب العرض: الأكثر إلحاحًا أولًا (البند 26)
_SORT_RANK = {
    (NOT_STARTED, OVERDUE): 0,
    (AttendanceSessionStatus.IN_PROGRESS, OVERDUE): 1,
    (AttendanceSessionStatus.SUBMITTED, OVERDUE): 2,
    (AttendanceSessionStatus.IN_PROGRESS, ON_TIME): 3,
    (NOT_STARTED, ON_TIME): 4,
    (AttendanceSessionStatus.SUBMITTED, ON_TIME): 5,
}


def _membership_name(membership) -> str | None:
    if membership is None:
        return None
    profile = getattr(membership, "staff_profile", None)
    return profile.display_name if profile else membership.user.display_name


def _local_hhmm(value: datetime | None, tz) -> str | None:
    return value.astimezone(tz).strftime("%H:%M") if value else None


def get_current_section_attendance_statuses(*, school, now: datetime | None = None) -> dict:
    """حمولة اللوحة كاملة — الخادم مصدر الحقيقة للحالة والتأخر (لا حساب في الواجهة)."""
    year = _active_year(school)  # لا عام نشط → ACTIVE_ACADEMIC_YEAR_REQUIRED (409)
    settings_obj = get_or_create_settings(school=school)
    if now is None:
        now = school_now(school)
    local_now = now.astimezone(ZoneInfo(settings_obj.timezone))
    period, local_date = get_current_attendance_period(school, now)

    payload = {
        "school_time": local_now.isoformat(),
        "date": local_date.isoformat(),
        "period": None,
        "alert": None,
        "summary": None,
        "sections": [],
    }
    if period is None:
        return payload  # لا حصة → لا توقعات ولا تنبيهات (حالة واضحة، ليست خطأ)

    current_alert_at = alert_at_for(
        day=local_date,
        start_time=period.start_time,
        alert_minutes=settings_obj.unprepared_period_alert_minutes,
        tz_name=settings_obj.timezone,
    )
    tz = current_alert_at.tzinfo

    # الفصول المتوقعة: فعالة وفيها طلاب ACTIVE بقيد ACTIVE في العام النشط
    sections = list(
        Section.objects.filter(school=school, is_active=True)
        .select_related("grade")
        .annotate(
            active_students=Count(
                "enrollments",
                filter=Q(
                    enrollments__status=EnrollmentStatus.ACTIVE,
                    enrollments__academic_year=year,
                    enrollments__student__status="ACTIVE",
                ),
            )
        )
        .filter(active_students__gt=0)
        .order_by("grade__sequence", "code")
    )

    # جلسات الحصة الحالية — العزل بحقل school (جلسة مدرسة أخرى لا تنضم ولو تطابقت
    # المعرفات)، والربط بالفصل داخل نفس النتيجة المعزولة
    sessions_by_section = {
        s.section_id: s
        for s in AttendanceSession.objects.filter(
            school=school,
            attendance_date=local_date,
            period_sequence=period.sequence,
        ).select_related(
            "started_by_membership__user",
            "started_by_membership__staff_profile",
            "submitted_by_membership__user",
            "submitted_by_membership__staff_profile",
        )
    }

    rows = []
    summary = {
        "total": len(sections),
        "submitted": 0,
        "in_progress": 0,
        "not_started": 0,
        "overdue_total": 0,
        "overdue_submitted": 0,
        "overdue_in_progress": 0,
        "overdue_not_started": 0,
    }

    for section in sections:
        session = sessions_by_section.get(section.id)
        if session is None:
            status = NOT_STARTED
            minutes = overdue_minutes(current_alert_at, now)
            teacher = None  # لا جدول معلمين — قرار مقصود (البند 21)
            started_at = submitted_at = None
        elif session.status == AttendanceSessionStatus.SUBMITTED:
            status = AttendanceSessionStatus.SUBMITTED
            minutes = overdue_minutes(session_alert_at(session), session.submitted_at)
            teacher = _membership_name(session.submitted_by_membership)
            started_at = _local_hhmm(session.started_at, tz)
            submitted_at = _local_hhmm(session.submitted_at, tz)
        else:
            status = AttendanceSessionStatus.IN_PROGRESS
            minutes = overdue_minutes(session_alert_at(session), now)
            teacher = _membership_name(session.started_by_membership)
            started_at = _local_hhmm(session.started_at, tz)
            submitted_at = None

        timeliness = OVERDUE if minutes is not None else ON_TIME
        key = {
            NOT_STARTED: "not_started",
            AttendanceSessionStatus.SUBMITTED: "submitted",
            AttendanceSessionStatus.IN_PROGRESS: "in_progress",
        }[status]
        summary[key] += 1
        if timeliness == OVERDUE:
            summary["overdue_total"] += 1
            summary[f"overdue_{key}"] += 1

        rows.append(
            {
                "section_id": section.id,
                "section_name": section.name,
                "grade_id": section.grade_id,
                "grade_name": section.grade.name,
                "students_count": section.active_students,
                "attendance_status": status,
                "timeliness_status": timeliness,
                "started_at": started_at,
                "submitted_at": submitted_at,
                "minutes_overdue": minutes,
                "teacher_name": teacher,
                "session_id": session.id if session else None,
            }
        )

    rows.sort(
        key=lambda r: (
            _SORT_RANK[(r["attendance_status"], r["timeliness_status"])],
            r["grade_name"],
            r["section_name"],
        )
    )

    payload.update(
        {
            "school_time": local_now.isoformat(),
            "period": {
                "sequence": period.sequence,
                "name": period.name,
                "start_time": period.start_time.strftime("%H:%M"),
                "end_time": period.end_time.strftime("%H:%M"),
            },
            "alert": {
                "minutes": settings_obj.unprepared_period_alert_minutes,
                "alert_at": current_alert_at.strftime("%H:%M"),
            },
            "summary": summary,
            "sections": rows,
        }
    )
    return payload
