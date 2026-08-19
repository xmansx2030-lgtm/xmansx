"""جلسات التحضير: البدء، الاعتماد، التعديل — Exception-Only + Snapshot.

سياسات موثقة:
- IN_PROGRESS: أي معلم في المدرسة يستطيع متابعة/اعتماد جلسة مفتوحة (تغطية
  واقعية للفصول) — submitted_by_membership يسجل من اعتمد فعليًا.
- Roster يثبت عند البدء (بصمة)؛ تغير جوهري قبل الاعتماد → ATTENDANCE_ROSTER_CHANGED
  والواجهة تحدّث — لا تسجيل غياب لطالب خرج من الفصل.
- التأخر: يحسب خادميًا من snapshot.start_time؛ وصول قبل البداية مرفوض (لا دقائق
  سالبة)؛ بعد نهاية الحصة مسموح والحساب من البداية يبقى صحيحًا.
- نافذة تعديل المعلم من إعداد المدرسة؛ الوكيل/المدير تصحيح إداري بلا نافذة.
"""

import hashlib
from datetime import datetime, time

from django.db import IntegrityError, transaction
from django.utils import timezone as dj_timezone

from academics.models import AcademicYear, AcademicYearStatus, Semester, SemesterStatus
from attendance.models import (
    AttendanceChange,
    AttendanceMark,
    AttendanceMarkStatus,
    AttendanceSession,
    AttendanceSessionStatus,
)
from attendance.services.periods import (
    build_period_snapshot,
    get_current_attendance_period,
)
from audit.models import AuditAction
from audit.services import record_event
from common.errors import ApiError
from memberships.models import SchoolRole
from schools.services.settings import get_or_create_settings
from students.services.enrollments import students_for_section

ADMIN_CORRECTION_ROLES = {SchoolRole.VICE_PRINCIPAL, SchoolRole.SCHOOL_MANAGER}


def _active_year(school) -> AcademicYear:
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


def get_roster(*, school, section, academic_year) -> list[dict]:
    """طلاب الفصل الفعالون فقط (ACTIVE + قيد ACTIVE بالعام الحالي) — استعلام واحد."""
    enrollments = students_for_section(
        school=school, section=section, academic_year=academic_year
    ).filter(student__status="ACTIVE")
    return [
        {
            "student_id": e.student_id,
            "full_name": e.student.full_name,
            "national_id_masked": e.student.national_id_masked,
        }
        for e in enrollments
    ]


def roster_fingerprint(roster: list[dict]) -> str:
    payload = ",".join(str(r["student_id"]) for r in sorted(roster, key=lambda r: r["student_id"]))
    return hashlib.sha256(payload.encode()).hexdigest()


def start_session(
    *, school, membership, section, request=None
) -> tuple[AttendanceSession, list[dict], bool]:
    """يفتح/يستأنف جلسة الحصة الحالية — يعيد (session, roster, resumed)."""
    if section.school_id != school.id or not section.is_active:
        raise ApiError("NOT_FOUND", "المورد المطلوب غير موجود.", status_code=404)

    year = _active_year(school)
    period, local_date = get_current_attendance_period(school)
    if period is None:
        raise ApiError(
            "NO_CURRENT_ATTENDANCE_PERIOD",
            "لا توجد حصة دراسية نشطة في الوقت الحالي.",
            status_code=409,
        )

    # سياق اليوم يتجمد عند أول نشاط حضور (م8) — مرجع expected_periods التاريخي
    from attendance.services.day_context import get_or_create_attendance_day_context

    get_or_create_attendance_day_context(school=school, attendance_date=local_date)

    roster = get_roster(school=school, section=section, academic_year=year)
    settings_obj = get_or_create_settings(school=school)
    semester = Semester.objects.filter(
        school=school, status=SemesterStatus.ACTIVE
    ).first()

    try:
        with transaction.atomic():
            session = AttendanceSession.objects.create(
                school=school,
                academic_year=year,
                semester=semester,
                section=section,
                attendance_date=local_date,
                bell_period=period,
                period_sequence=period.sequence,
                bell_period_snapshot=build_period_snapshot(
                    period, local_date, settings_obj.timezone
                ),
                roster_fingerprint=roster_fingerprint(roster),
                unprepared_alert_minutes_snapshot=(
                    settings_obj.unprepared_period_alert_minutes
                ),
                started_by_membership=membership,
            )
        record_event(
            AuditAction.ATTENDANCE_STARTED,
            request=request,
            actor=membership.user,
            school=school,
            target_type="AttendanceSession",
            target_id=session.id,
            metadata={"section_id": section.id, "period": period.sequence},
        )
        return session, roster, False
    except IntegrityError:
        # جلسة قائمة لنفس (الفصل، التاريخ، الحصة) — الحكم من قاعدة البيانات
        existing = AttendanceSession.objects.select_related(
            "submitted_by_membership__user"
        ).get(
            school=school,
            section=section,
            attendance_date=local_date,
            period_sequence=period.sequence,
        )
        # SUBMITTED: تعاد الجلسة ليعرضها الواجهة (المرسل/الوقت/التعديل) —
        # منع الإرسال المزدوج مسؤولية submit (409) لا العرض.
        # IN_PROGRESS: أي معلم بالمدرسة يكمل (سياسة موثقة).
        return existing, roster, True


def _already_submitted_error(session: AttendanceSession) -> ApiError:
    submitter = ""
    if session.submitted_by_membership:
        profile = getattr(session.submitted_by_membership, "staff_profile", None)
        submitter = (
            profile.display_name if profile else session.submitted_by_membership.user.display_name
        )
    return ApiError(
        "ATTENDANCE_SESSION_ALREADY_SUBMITTED",
        "تم اعتماد حضور هذا الفصل مسبقاً.",
        status_code=409,
        details={
            "submitted_by": submitter,
            "submitted_at": session.submitted_at.isoformat() if session.submitted_at else None,
        },
    )


def _parse_snapshot_start(session: AttendanceSession) -> time:
    hour, minute = session.bell_period_snapshot["start_time"].split(":")
    return time(int(hour), int(minute))


def _compute_late_minutes(session: AttendanceSession, arrival: time) -> int:
    """من snapshot البداية حصرًا — لا BellPeriod الحالي ولا قيمة من العميل."""
    start = _parse_snapshot_start(session)
    delta = (
        datetime.combine(session.attendance_date, arrival)
        - datetime.combine(session.attendance_date, start)
    )
    minutes = int(delta.total_seconds() // 60)
    if minutes < 0:
        raise ApiError(
            "INVALID_ARRIVAL_TIME",
            "وقت الوصول قبل بداية الحصة — تحقق من الوقت المدخل.",
        )
    return minutes


def _validate_marks(
    session: AttendanceSession, marks: list[dict], roster: list[dict]
) -> list[dict]:
    roster_ids = {r["student_id"] for r in roster}
    seen: set[int] = set()
    validated = []
    for mark in marks:
        student_id = mark["student_id"]
        if student_id in seen:
            raise ApiError("VALIDATION_ERROR", "طالب مكرر في قائمة العلامات.")
        seen.add(student_id)
        if student_id not in roster_ids:
            raise ApiError(
                "INVALID_ATTENDANCE_STUDENT",
                "أحد الطلاب لا ينتمي لهذا الفصل — حدّث الصفحة.",
            )
        status = mark["status"]
        arrival = None
        late_minutes = None
        if status == AttendanceMarkStatus.LATE:
            arrival = mark.get("arrival_time")
            if arrival is None:
                raise ApiError("INVALID_ARRIVAL_TIME", "حدد وقت وصول الطالب المتأخر.")
            late_minutes = _compute_late_minutes(session, arrival)
        validated.append(
            {
                "student_id": student_id,
                "status": status,
                "arrival_time": arrival,
                "late_minutes": late_minutes,
            }
        )
    return validated


_ROSTER_CHANGED_ERROR = (
    "ATTENDANCE_ROSTER_CHANGED",
    "تغيرت قائمة طلاب الفصل، يرجى تحديث الصفحة قبل الاعتماد.",
)


def submit_session(*, session_id: int, school, membership, marks: list[dict],
                   request=None) -> AttendanceSession:
    """تحديث بصمة الـ roster عند التغير يجب أن يثبت رغم رفض الاعتماد —
    لذا الخطأ يرفع بعد خروج الـ transaction بنجاح (نمط المرحلة 4)."""
    with transaction.atomic():
        session, roster, deferred_error = _submit_locked(
            session_id=session_id, school=school, membership=membership, marks=marks
        )
    if deferred_error is not None:
        raise deferred_error

    # م10 — عذر Full-Day اعتُمد ويوم كان ناقصًا: التغطية تتوسع تلقائيًا (بند 56)
    from excuses.services.coverage import reconcile_excuse_coverage_for_date

    reconcile_excuse_coverage_for_date(
        school=school, attendance_date=session.attendance_date
    )

    # تحديث ملخصات اليوم متزامنًا (م8) — الوكيل لا ينتظر worker ليرى التحليلات
    from attendance.services.daily_summary import recalculate_daily_attendance_for_section

    recalculate_daily_attendance_for_section(
        school=school, section=session.section, attendance_date=session.attendance_date
    )

    validated_count = session.marks.count()
    absent = session.marks.filter(status=AttendanceMarkStatus.ABSENT).count()
    record_event(
        AuditAction.ATTENDANCE_SUBMITTED,
        request=request,
        actor=membership.user,
        school=school,
        target_type="AttendanceSession",
        target_id=session.id,
        metadata={  # أعداد فقط — لا أسماء ولا هويات
            "students": len(roster),
            "absent": absent,
            "late": validated_count - absent,
        },
    )
    return session


def _submit_locked(*, session_id: int, school, membership, marks: list[dict]):
    session = (
        AttendanceSession.objects.select_for_update()
        .select_related("section")
        .get(id=session_id, school=school)
    )
    if session.status == AttendanceSessionStatus.SUBMITTED:
        raise _already_submitted_error(session)

    roster = get_roster(
        school=school, section=session.section, academic_year=session.academic_year
    )
    if roster_fingerprint(roster) != session.roster_fingerprint:
        # الفصل تغير منذ البدء — تثبت البصمة الجديدة ثم يرفض الاعتماد
        session.roster_fingerprint = roster_fingerprint(roster)
        session.save(update_fields=["roster_fingerprint", "updated_at"])
        code, message = _ROSTER_CHANGED_ERROR
        return session, roster, ApiError(code, message, status_code=409)

    validated = _validate_marks(session, marks, roster)

    session.marks.all().delete()  # مسودات سابقة إن وجدت
    AttendanceMark.objects.bulk_create(
        AttendanceMark(
            school=school,
            session=session,
            student_id=m["student_id"],
            status=m["status"],
            arrival_time=m["arrival_time"],
            late_minutes=m["late_minutes"],
        )
        for m in validated
    )
    session.status = AttendanceSessionStatus.SUBMITTED
    session.submitted_by_membership = membership
    session.submitted_at = dj_timezone.now()
    session.save(
        update_fields=["status", "submitted_by_membership", "submitted_at", "updated_at"]
    )
    return session, roster, None


def _can_edit(session: AttendanceSession, membership, roles: list[str]) -> None:
    if ADMIN_CORRECTION_ROLES & set(roles):
        return  # تصحيح إداري — بلا نافذة
    if SchoolRole.TEACHER not in roles:
        raise ApiError(
            "ATTENDANCE_PERMISSION_DENIED",
            "ليست لديك صلاحية تعديل هذا التحضير.",
            status_code=403,
        )
    if session.submitted_by_membership_id != membership.id:
        raise ApiError(
            "ATTENDANCE_PERMISSION_DENIED",
            "لا يمكنك تعديل تحضير اعتمده معلم آخر.",
            status_code=403,
        )
    settings_obj = get_or_create_settings(school=session.school)
    window = settings_obj.attendance_edit_window_minutes
    elapsed = (dj_timezone.now() - session.submitted_at).total_seconds() / 60
    if elapsed > window:
        raise ApiError(
            "ATTENDANCE_EDIT_WINDOW_EXPIRED",
            "انتهت المدة المسموحة لك لتعديل التحضير.",
            status_code=403,
        )


def edit_session(*, session_id: int, school, membership, roles: list[str],
                 marks: list[dict], reason: str = "", request=None) -> AttendanceSession:
    """تعديل جلسة معتمدة — كل فرق يسجل في AttendanceChange (يشمل PRESENT)."""
    with transaction.atomic():
        session = (
            AttendanceSession.objects.select_for_update()
            .select_related("section")
            .get(id=session_id, school=school)
        )
        if session.status != AttendanceSessionStatus.SUBMITTED:
            raise ApiError("VALIDATION_ERROR", "لا يمكن تعديل جلسة غير معتمدة.")
        _can_edit(session, membership, roles)

        roster = get_roster(
            school=school, section=session.section, academic_year=session.academic_year
        )
        validated = _validate_marks(session, marks, roster)

        old_marks = {m.student_id: m for m in session.marks.all()}
        new_marks = {m["student_id"]: m for m in validated}
        changes = []

        for student_id in set(old_marks) | set(new_marks):
            old = old_marks.get(student_id)
            new = new_marks.get(student_id)
            old_status = old.status if old else "PRESENT"
            new_status = new["status"] if new else "PRESENT"
            old_late = old.late_minutes if old else None
            new_late = new["late_minutes"] if new else None
            if old_status != new_status or old_late != new_late:
                changes.append(
                    AttendanceChange(
                        school=school,
                        session=session,
                        student_id=student_id,
                        actor_membership=membership,
                        previous_status=old_status,
                        new_status=new_status,
                        previous_late_minutes=old_late,
                        new_late_minutes=new_late,
                        reason=reason[:300],
                    )
                )

        if changes:
            AttendanceChange.objects.bulk_create(changes)
            session.marks.all().delete()
            AttendanceMark.objects.bulk_create(
                AttendanceMark(
                    school=school,
                    session=session,
                    student_id=m["student_id"],
                    status=m["status"],
                    arrival_time=m["arrival_time"],
                    late_minutes=m["late_minutes"],
                )
                for m in validated
            )
            session.save(update_fields=["updated_at"])
            record_event(
                AuditAction.ATTENDANCE_EDITED,
                request=request,
                actor=membership.user,
                school=school,
                target_type="AttendanceSession",
                target_id=session.id,
                metadata={"changes": len(changes)},
            )
    if changes:
        # م10 — مواءمة تغطيات الأعذار قبل الملخصات: غياب زال → Void،
        # غياب ظهر ضمن عذر معتمد → تغطية تلقائية (ترتيب الإجراءات لا يهم)
        from excuses.services.coverage import reconcile_excuse_coverage_for_date

        reconcile_excuse_coverage_for_date(
            school=school,
            attendance_date=session.attendance_date,
            student_ids=[c.student_id for c in changes],
        )

        # التعديل يعيد حساب ملخصات اليوم فورًا (م8) — بعد commit العلامات
        from attendance.services.daily_summary import (
            recalculate_daily_attendance_for_section,
        )

        recalculate_daily_attendance_for_section(
            school=school, section=session.section, attendance_date=session.attendance_date
        )
    return session
