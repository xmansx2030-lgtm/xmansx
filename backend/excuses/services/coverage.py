"""حل تغطية العذر: معاينة، اعتماد، إلغاء، وReconcile مع تعديلات الحضور.

الحقيقة التشغيلية (ABSENT) لا تُمس أبدًا؛ التغطية طبقة إدارية فوقها:
- الاعتماد ينشئ Coverage نشطة لكل غياب فعلي ضمن الأهداف.
- تعديل الحضور بعد الاعتماد يمر بـreconcile: غياب زال → Void، غياب ظهر → تغطية
  جديدة تلقائيًا (ترتيب الإجراءات لا يهم — بند 55).
- قيد DB جزئي (uniq_active_coverage_per_absence) يضمن تغطية معتمدة واحدة لكل
  غياب حتى تحت التزامن.
"""

import hashlib
import json
from datetime import date as date_cls

from django.db import IntegrityError, transaction
from django.utils import timezone as dj_timezone

from attendance.models import (
    AttendanceMark,
    AttendanceMarkStatus,
    AttendanceSession,
    AttendanceSessionStatus,
)
from attendance.services.day_context import get_or_create_attendance_day_context
from audit.models import AuditAction
from audit.services import record_event
from common.errors import ApiError
from excuses.models import (
    AbsenceExcuse,
    AbsenceExcuseCoverage,
    AbsenceExcuseStatus,
    AbsenceExcuseTarget,
    ExcuseCoverageStatus,
)
from students.services.enrollments import enrollments_on_date

VOID_REASON_ATTENDANCE_CHANGED = "ATTENDANCE_CHANGED"
VOID_REASON_EXCUSE_CANCELLED = "EXCUSE_CANCELLED"

_STATUS_ERRORS = {
    AbsenceExcuseStatus.APPROVED: ("EXCUSE_ALREADY_APPROVED", "هذا العذر معتمد مسبقًا."),
    AbsenceExcuseStatus.REJECTED: ("EXCUSE_ALREADY_REJECTED", "هذا العذر مرفوض مسبقًا."),
    AbsenceExcuseStatus.CANCELLED: ("EXCUSE_ALREADY_CANCELLED", "هذا العذر ملغى مسبقًا."),
}


def _raise_not_pending(excuse: AbsenceExcuse) -> None:
    code, message = _STATUS_ERRORS.get(
        excuse.status, ("VALIDATION_ERROR", "حالة العذر لا تسمح بهذه العملية.")
    )
    raise ApiError(code, message, status_code=409)


def target_scope_by_date(targets) -> dict[date_cls, set[int] | None]:
    """‏None = يوم كامل — يبتلع أي أهداف حصص لنفس التاريخ."""
    scope: dict[date_cls, set[int] | None] = {}
    for target in targets:
        current = scope.get(target.attendance_date, set())
        if target.period_sequence is None or current is None:
            scope[target.attendance_date] = None
        else:
            current.add(target.period_sequence)
            scope[target.attendance_date] = current
    return scope


def resolve_coverage_plan(excuse: AbsenceExcuse) -> dict:
    """يحل أهداف العذر مقابل الحالة الفعلية الحالية لسجل الحضور.

    يعيد dict فيه:
    - covered: قائمة علامات ABSENT ضمن النطاق غير المغطاة بعذر آخر
    - already_excused: علامات ABSENT ضمن النطاق مغطاة بعذر معتمد آخر
    - days: تفصيل المعاينة لكل تاريخ
    - preview_hash: بصمة الحالة (لكشف Stale Preview عند الاعتماد)
    """
    targets = list(excuse.targets.all())
    scope = target_scope_by_date(targets)
    dates = sorted(scope)
    school = excuse.school

    marks = list(
        AttendanceMark.objects.filter(
            school=school,
            student=excuse.student,
            session__attendance_date__in=dates,
            session__status=AttendanceSessionStatus.SUBMITTED,
        ).select_related("session")
    )
    in_scope = [
        mark
        for mark in marks
        if scope[mark.session.attendance_date] is None
        or mark.session.period_sequence in scope[mark.session.attendance_date]
    ]
    absent_in_scope = [m for m in in_scope if m.status == AttendanceMarkStatus.ABSENT]

    covered_by_other = set(
        AbsenceExcuseCoverage.objects.filter(
            school=school,
            student=excuse.student,
            attendance_date__in=dates,
            status=ExcuseCoverageStatus.ACTIVE,
        )
        .exclude(excuse=excuse)
        .values_list("attendance_session_id", flat=True)
    )
    covered = [m for m in absent_in_scope if m.session_id not in covered_by_other]
    already_excused = [m for m in absent_in_scope if m.session_id in covered_by_other]

    days = [
        _day_preview(excuse, day, scope[day], marks)
        for day in dates
    ]
    # البصمة تربط: هوية العذر + نطاقه المعلن + حالات الغياب المحلولة.
    # بدون النطاق كان تعديل الأهداف بعد المعاينة يبقي البصمة صالحة (يوم واحد
    # يُعاين ثم يستبدل بثلاثين يومًا ويعتمد)، وبدون هوية العذر كانت بصمة النطاق
    # الفارغ ثابتة عالميًا فتصلح لاعتماد أي عذر بلا معاينة إطلاقًا.
    fingerprint = {
        "excuse": excuse.id,
        "targets": sorted(
            [t.attendance_date.isoformat(), t.period_sequence] for t in targets
        ),
        "absences": sorted(
            [
                mark.session.attendance_date.isoformat(),
                mark.session.period_sequence,
                mark.session_id,
                mark.session_id in covered_by_other,
            ]
            for mark in absent_in_scope
        ),
    }
    preview_hash = hashlib.sha256(
        json.dumps(fingerprint, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()
    return {
        "covered": covered,
        "already_excused": already_excused,
        "days": days,
        "preview_hash": preview_hash,
    }


def _day_preview(excuse, day: date_cls, day_scope, marks) -> dict:
    school = excuse.school
    context = get_or_create_attendance_day_context(school=school, attendance_date=day)
    expected_sequences = {p["sequence"] for p in context.attendance_periods}

    # ترتيب صريح: طالب بقيدين ساريين في نفس اليوم (نقل منتصف اليوم) كان يعطي
    # فصلًا عشوائيًا حسب ترتيب قاعدة البيانات فتتذبذب أعداد المعاينة
    enrollment = (
        enrollments_on_date(school=school, on_date=day)
        .filter(student=excuse.student)
        .select_related("section")
        .order_by("-enrolled_at", "-id")
        .first()
    )
    submitted_sequences = set(
        AttendanceSession.objects.filter(
            school=school,
            section_id=enrollment.section_id,
            attendance_date=day,
            status=AttendanceSessionStatus.SUBMITTED,
        ).values_list("period_sequence", flat=True)
    ) if enrollment else set()

    scope_sequences = expected_sequences if day_scope is None else set(day_scope)
    day_marks = [
        m for m in marks
        if m.session.attendance_date == day
        and m.session.period_sequence in scope_sequences
    ]
    absent = [m for m in day_marks if m.status == AttendanceMarkStatus.ABSENT]
    late = [m for m in day_marks if m.status == AttendanceMarkStatus.LATE]
    submitted_in_scope = scope_sequences & submitted_sequences
    missing_in_scope = scope_sequences - submitted_sequences
    present = len(submitted_in_scope) - len(day_marks)

    return {
        "attendance_date": day.isoformat(),
        "scope": "FULL_DAY" if day_scope is None else sorted(day_scope),
        "expected_periods": len(expected_sequences),
        "scope_periods": len(scope_sequences),
        "submitted_periods": len(submitted_in_scope),
        "missing_periods": len(missing_in_scope),
        "absent_periods": len(absent),
        "present_periods": max(present, 0),
        "late_periods": len(late),
        "complete": not missing_in_scope and bool(scope_sequences),
    }


def approve_excuse(
    *, excuse_id: int, school, membership, preview_hash: str, request=None
) -> AbsenceExcuse:
    """اعتماد العذر — atomic + idempotent + محمي من Stale Preview والتداخل."""
    with transaction.atomic():
        excuse = (
            AbsenceExcuse.objects.select_for_update()
            .select_related("student")
            .get(id=excuse_id, school=school)
        )
        if excuse.status != AbsenceExcuseStatus.PENDING:
            _raise_not_pending(excuse)

        plan = resolve_coverage_plan(excuse)
        if preview_hash != plan["preview_hash"]:
            raise ApiError(
                "EXCUSE_PREVIEW_STALE",
                "تغير سجل الحضور منذ معاينة العذر. يرجى إعادة المعاينة.",
                status_code=409,
            )
        if plan["already_excused"]:
            raise ApiError(
                "ABSENCE_ALREADY_EXCUSED",
                "بعض حالات الغياب المستهدفة مغطاة مسبقًا بعذر معتمد آخر.",
                status_code=409,
                details={
                    "dates": sorted(
                        {
                            m.session.attendance_date.isoformat()
                            for m in plan["already_excused"]
                        }
                    )
                },
            )
        has_incomplete_day = any(day["missing_periods"] for day in plan["days"])
        if not plan["covered"] and not has_incomplete_day:
            raise ApiError(
                "EXCUSE_NO_ABSENCE_FOUND",
                "لا توجد حالة غياب مسجلة ضمن نطاق هذا العذر.",
                status_code=409,
            )

        now = dj_timezone.now()
        try:
            AbsenceExcuseCoverage.objects.bulk_create(
                AbsenceExcuseCoverage(
                    school=school,
                    excuse=excuse,
                    student=excuse.student,
                    attendance_session_id=mark.session_id,
                    attendance_date=mark.session.attendance_date,
                    period_sequence_snapshot=mark.session.period_sequence,
                )
                for mark in plan["covered"]
            )
        except IntegrityError:
            # سباق اعتماد متزامن لعذر متداخل — القيد الجزئي حسم أحدهما
            raise ApiError(
                "ABSENCE_ALREADY_EXCUSED",
                "بعض حالات الغياب المستهدفة مغطاة مسبقًا بعذر معتمد آخر.",
                status_code=409,
            ) from None
        excuse.status = AbsenceExcuseStatus.APPROVED
        excuse.approved_by_membership = membership
        excuse.approved_at = now
        excuse.save(
            update_fields=["status", "approved_by_membership", "approved_at", "updated_at"]
        )
        record_event(
            AuditAction.EXCUSE_APPROVED,
            request=request,
            actor=membership.user,
            school=school,
            target_type="AbsenceExcuse",
            target_id=excuse.id,
            metadata={"coverage_count": len(plan["covered"])},
        )
    _recalculate_for_sessions([mark.session for mark in plan["covered"]], school=school)
    return excuse


def cancel_excuse(
    *, excuse_id: int, school, membership, reason: str, request=None
) -> AbsenceExcuse:
    """‏APPROVED → CANCELLED مع Void للتغطيات — لا Hard Delete (بند 10)."""
    with transaction.atomic():
        excuse = AbsenceExcuse.objects.select_for_update().get(id=excuse_id, school=school)
        if excuse.status != AbsenceExcuseStatus.APPROVED:
            if excuse.status == AbsenceExcuseStatus.CANCELLED:
                _raise_not_pending(excuse)
            raise ApiError(
                "VALIDATION_ERROR", "لا يمكن إلغاء عذر غير معتمد.", status_code=409
            )
        now = dj_timezone.now()
        active = list(
            excuse.coverages.filter(status=ExcuseCoverageStatus.ACTIVE).select_related(
                "attendance_session"
            )
        )
        excuse.coverages.filter(status=ExcuseCoverageStatus.ACTIVE).update(
            status=ExcuseCoverageStatus.VOIDED,
            voided_at=now,
            void_reason=VOID_REASON_EXCUSE_CANCELLED,
            updated_at=now,
        )
        excuse.status = AbsenceExcuseStatus.CANCELLED
        excuse.cancelled_by_membership = membership
        excuse.cancelled_at = now
        excuse.cancellation_reason = reason[:300]
        excuse.save(
            update_fields=[
                "status",
                "cancelled_by_membership",
                "cancelled_at",
                "cancellation_reason",
                "updated_at",
            ]
        )
        record_event(
            AuditAction.EXCUSE_CANCELLED,
            request=request,
            actor=membership.user,
            school=school,
            target_type="AbsenceExcuse",
            target_id=excuse.id,
            metadata={"voided_coverage_count": len(active)},
        )
    # عذر معتمد آخر قد يستهدف نفس الغياب — المواءمة تلتقطه فورًا بدل انتظار
    # تعديل حضور عابر يقلب التصنيف لاحقًا (ترتيب الإجراءات لا يهم — بند 55)
    for attendance_date in {coverage.attendance_date for coverage in active}:
        reconcile_excuse_coverage_for_date(
            school=school,
            attendance_date=attendance_date,
            student_ids=[excuse.student_id],
        )
    _recalculate_for_sessions(
        [coverage.attendance_session for coverage in active], school=school
    )
    return excuse


def reconcile_excuse_coverage_for_date(
    *, school, attendance_date: date_cls, student_ids: list[int] | None = None
) -> set[int]:
    """يعيد مواءمة التغطيات مع الحالة الفعلية بعد أي تعديل/اعتماد حضور.

    - تغطية نشطة لغياب لم يعد موجودًا → VOIDED (ATTENDANCE_CHANGED).
    - غياب ظهر ضمن هدف عذر معتمد وغير مغطى → تغطية جديدة تلقائيًا.
    يعمل فقط على طلاب لهم أهداف معتمدة أو تغطيات نشطة في هذا التاريخ — لا مسح
    لكل طلاب المدرسة (بند 57). يعيد student_ids المتأثرين.
    """
    affected: set[int] = set()
    now = dj_timezone.now()
    # كل القراءات داخل الـ transaction: قراءتها خارجه كانت تسمح بإلغاء عذر
    # متزامن بين القراءة والكتابة فتُنشأ تغطية نشطة لعذر ملغى (ولا يزيلها شيء
    # لاحقًا لأن المواءمة تقرأ الأعذار المعتمدة فقط).
    with transaction.atomic():
        targets = list(
            AbsenceExcuseTarget.objects.filter(
                school=school,
                attendance_date=attendance_date,
                excuse__status=AbsenceExcuseStatus.APPROVED,
            ).select_related("excuse")
        )
        students = {t.excuse.student_id for t in targets}
        active_coverages = list(
            AbsenceExcuseCoverage.objects.filter(
                school=school,
                attendance_date=attendance_date,
                status=ExcuseCoverageStatus.ACTIVE,
            ).select_related("excuse")
        )
        students |= {c.student_id for c in active_coverages}
        if student_ids is not None:
            students &= set(student_ids)
        if not students:
            return set()

        # قفل الأعذار المرشحة: الإلغاء المتزامن ينتظر انتهاء المواءمة ثم يرى
        # التغطية الجديدة ويبطلها — بدل أن يسبقها فتنجو تغطية ليتيمة
        locked_approved = set(
            AbsenceExcuse.objects.select_for_update()
            .filter(
                id__in={t.excuse_id for t in targets},
                status=AbsenceExcuseStatus.APPROVED,
            )
            .values_list("id", flat=True)
        )
        targets = [t for t in targets if t.excuse_id in locked_approved]

        absent_marks = {
            (mark.student_id, mark.session_id): mark
            for mark in AttendanceMark.objects.filter(
                school=school,
                student_id__in=students,
                status=AttendanceMarkStatus.ABSENT,
                session__attendance_date=attendance_date,
                session__status=AttendanceSessionStatus.SUBMITTED,
            ).select_related("session")
        }

        to_void = [
            coverage
            for coverage in active_coverages
            if coverage.student_id in students
            and (coverage.student_id, coverage.attendance_session_id) not in absent_marks
        ]
        if to_void:
            AbsenceExcuseCoverage.objects.filter(id__in=[c.id for c in to_void]).update(
                status=ExcuseCoverageStatus.VOIDED,
                voided_at=now,
                void_reason=VOID_REASON_ATTENDANCE_CHANGED,
                updated_at=now,
            )
            affected |= {c.student_id for c in to_void}

        still_covered = {
            (c.student_id, c.attendance_session_id)
            for c in active_coverages
            if c not in to_void
        }
        candidates = _approved_targets_by_student(targets)
        to_create = []
        for (student_id, session_id), mark in absent_marks.items():
            if (student_id, session_id) in still_covered:
                continue
            excuse = _pick_excuse(
                candidates.get(student_id, []), mark.session.period_sequence
            )
            if excuse is None:
                continue
            to_create.append(
                AbsenceExcuseCoverage(
                    school=school,
                    excuse=excuse,
                    student_id=student_id,
                    attendance_session_id=session_id,
                    attendance_date=attendance_date,
                    period_sequence_snapshot=mark.session.period_sequence,
                )
            )
        if to_create:
            AbsenceExcuseCoverage.objects.bulk_create(to_create, ignore_conflicts=True)
            affected |= {c.student_id for c in to_create}
    return affected


def _approved_targets_by_student(targets) -> dict[int, list]:
    by_student: dict[int, list] = {}
    for target in targets:
        by_student.setdefault(target.excuse.student_id, []).append(target)
    return by_student


def _pick_excuse(student_targets, period_sequence: int):
    """أقدم عذر معتمد يستهدف الحصة (يوم كامل أو الحصة نفسها) — deterministic."""
    matching = [
        t.excuse
        for t in student_targets
        if t.period_sequence is None or t.period_sequence == period_sequence
    ]
    if not matching:
        return None
    return min(matching, key=lambda e: (e.approved_at, e.id))


def _recalculate_for_sessions(sessions, *, school) -> None:
    """إعادة حساب ملخصات اليوم للأزواج (فصل، تاريخ) المتأثرة — بعد commit."""
    from attendance.services.daily_summary import recalculate_daily_attendance_for_section
    from students.models import Section

    pairs = {(s.section_id, s.attendance_date) for s in sessions}
    if not pairs:
        return
    sections = Section.objects.in_bulk([section_id for section_id, _ in pairs])
    for section_id, attendance_date in pairs:
        recalculate_daily_attendance_for_section(
            school=school, section=sections[section_id], attendance_date=attendance_date
        )
