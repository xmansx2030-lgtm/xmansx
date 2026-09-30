"""تسجيل العذر مع اعتماده فورًا، وإدارة السجلات القديمة والمرفقات."""

import hashlib
from datetime import date as date_cls

from django.db import transaction
from django.utils import timezone as dj_timezone

from academics.models import AcademicYear
from attendance.models import (
    AttendanceDayContext,
    AttendanceMarkStatus,
    AttendanceSession,
    AttendanceSessionStatus,
)
from attendance.services.day_context import build_day_schedule_snapshot
from attendance.services.periods import school_now
from audit.models import AuditAction
from audit.services import record_event
from common.errors import ApiError
from excuses.models import (
    AbsenceExcuse,
    AbsenceExcuseAttachment,
    AbsenceExcuseStatus,
    AbsenceExcuseTarget,
)
from excuses.services.coverage import (
    _raise_not_pending,
    _recalculate_for_sessions,
    reconcile_excuse_coverage_for_date,
)
from excuses.validators import validate_excuse_attachment
from students.models import Student, StudentEnrollment
from subscriptions.entitlements import lock_school_capacity, require_storage_capacity

MAX_TARGETS_PER_EXCUSE = 60
MAX_ATTACHMENTS_PER_EXCUSE = 5


def _validate_targets(
    school, student, targets: list[dict], *, allow_future: bool = False,
) -> list[dict]:
    """يتحقق من العام والقيد والتكرار والحصص دون إنشاء سياق تاريخي خاطئ."""
    if not targets:
        raise ApiError("EXCUSE_INVALID_TARGET", "يجب تحديد يوم أو حصة واحدة على الأقل.")
    if len(targets) > MAX_TARGETS_PER_EXCUSE:
        raise ApiError(
            "EXCUSE_INVALID_TARGET",
            f"عدد الأهداف يتجاوز الحد المسموح ({MAX_TARGETS_PER_EXCUSE}).",
        )

    today = school_now(school).date()
    dates = {target["attendance_date"] for target in targets}
    years = list(AcademicYear.objects.filter(
        school=school, start_date__lte=max(dates), end_date__gte=min(dates),
    ))
    enrollments = list(StudentEnrollment.objects.filter(
        school=school, student=student, academic_year__in=years,
    ))
    contexts = {
        context.attendance_date: context
        for context in AttendanceDayContext.objects.filter(school=school, attendance_date__in=dates)
    }
    seen: set[tuple[date_cls, int | None]] = set()
    full_days: set[date_cls] = set()
    period_days: set[date_cls] = set()
    for target in targets:
        day = target["attendance_date"]
        sequence = target.get("period_sequence")
        if day > today and not allow_future:
            raise ApiError("EXCUSE_FUTURE_DATE_NOT_ALLOWED", "لا يمكن تسجيل عذر لتاريخ مستقبلي.")
        year = next((year for year in years if year.start_date <= day <= year.end_date), None)
        if year is None:
            raise ApiError(
                "EXCUSE_DATE_OUTSIDE_ACADEMIC_YEAR",
                "تاريخ العذر خارج الأعوام الدراسية المسجلة للمدرسة.",
                details={"attendance_date": day.isoformat()},
            )
        if not any(
            enrollment.academic_year_id == year.id
            and enrollment.enrolled_at <= day
            and (enrollment.ended_at is None or enrollment.ended_at > day)
            for enrollment in enrollments
        ):
            raise ApiError(
                "EXCUSE_STUDENT_NOT_ENROLLED_ON_DATE",
                "الطالب غير مقيد في المدرسة بتاريخ العذر.",
                details={"attendance_date": day.isoformat()},
            )
        key = (day, sequence)
        if key in seen:
            raise ApiError("EXCUSE_INVALID_TARGET", "توجد أهداف مكررة في العذر.")
        seen.add(key)
        if sequence is None:
            full_days.add(day)
        else:
            period_days.add(day)
            context = contexts.get(day)
            if context is not None and context.academic_year_id == year.id:
                valid_sequences = {p["sequence"] for p in context.attendance_periods}
            elif day < today:
                # لا نستنتج جدول يوم قديم من الجدول الحالي إذا لم تحفظ له لقطة.
                valid_sequences = set(AttendanceSession.objects.filter(
                    school=school, attendance_date=day, academic_year=year,
                    status=AttendanceSessionStatus.SUBMITTED,
                ).values_list("period_sequence", flat=True))
            else:
                valid_sequences = {
                    period["sequence"]
                    for period in build_day_schedule_snapshot(school, day)["periods"]
                    if period["is_attendance_period"]
                }
            if sequence not in valid_sequences:
                raise ApiError(
                    "EXCUSE_INVALID_TARGET",
                    "الحصة المحددة غير موجودة في جدول ذلك اليوم أو في سجله التاريخي.",
                    details={"attendance_date": day.isoformat(), "period_sequence": sequence},
                )
    conflicting = full_days & period_days
    if conflicting:
        raise ApiError(
            "EXCUSE_INVALID_TARGET",
            "لا يمكن الجمع بين هدف يوم كامل وأهداف حصص لنفس التاريخ.",
            details={"dates": sorted(d.isoformat() for d in conflicting)},
        )
    return targets


def create_excuse(
    *, school, membership, student, reason_type: str, notes: str,
    targets: list[dict], request=None, approve_immediately: bool = False,
) -> AbsenceExcuse:
    """واجهة API تستخدم الاعتماد المباشر؛ المسار القديم متاح لسجلات الانتقال والاختبارات."""
    with transaction.atomic():
        if approve_immediately:
            # تسلسل إنشاء أعذار الطالب نفسه يمنع هدفين متداخلين في سباق متزامن.
            Student.objects.select_for_update().get(id=student.id, school=school)
        validated = _validate_targets(
            school, student, targets, allow_future=approve_immediately,
        )
        if approve_immediately:
            dates = {target["attendance_date"] for target in validated}
            existing_targets = AbsenceExcuseTarget.objects.filter(
                school=school, attendance_date__in=dates,
                excuse__student=student,
                excuse__status=AbsenceExcuseStatus.APPROVED,
            ).values_list("attendance_date", "period_sequence")
            for existing_day, existing_period in existing_targets:
                if any(
                    target["attendance_date"] == existing_day
                    and (existing_period is None
                         or target.get("period_sequence") is None
                         or existing_period == target.get("period_sequence"))
                    for target in validated
                ):
                    raise ApiError(
                        "EXCUSE_TARGET_ALREADY_COVERED",
                        "يوجد عذر معتمد للطالب في هذا اليوم أو الحصة.",
                        status_code=409,
                        details={"attendance_date": existing_day.isoformat()},
                    )
        now = dj_timezone.now()
        excuse = AbsenceExcuse.objects.create(
            school=school,
            student=student,
            reason_type=reason_type,
            notes=notes[:500],
            recorded_by_membership=membership,
            recorded_at=now,
            status=(AbsenceExcuseStatus.APPROVED if approve_immediately
                    else AbsenceExcuseStatus.PENDING),
            approved_by_membership=membership if approve_immediately else None,
            approved_at=now if approve_immediately else None,
        )
        AbsenceExcuseTarget.objects.bulk_create(
            AbsenceExcuseTarget(
                school=school,
                excuse=excuse,
                attendance_date=t["attendance_date"],
                period_sequence=t.get("period_sequence"),
            )
            for t in validated
        )
        record_event(
            AuditAction.EXCUSE_CREATED,
            request=request,
            actor=membership.user,
            school=school,
            target_type="AbsenceExcuse",
            target_id=excuse.id,
            metadata={"student_id": student.id, "targets": len(validated)},
        )
        if approve_immediately:
            record_event(
                AuditAction.EXCUSE_APPROVED,
                request=request,
                actor=membership.user,
                school=school,
                target_type="AbsenceExcuse",
                target_id=excuse.id,
                metadata={"automatic": True, "targets": len(validated)},
            )
            target_dates = {target["attendance_date"] for target in validated}
            days_with_absence = AttendanceSession.objects.filter(
                school=school,
                attendance_date__in=target_dates,
                status=AttendanceSessionStatus.SUBMITTED,
                marks__student=student,
                marks__status=AttendanceMarkStatus.ABSENT,
            ).values_list("attendance_date", flat=True).distinct()
            for day in days_with_absence:
                reconcile_excuse_coverage_for_date(
                    school=school, attendance_date=day, student_ids=[student.id],
                )
    if not approve_immediately:
        return excuse
    covered_sessions = [coverage.attendance_session for coverage in excuse.coverages.filter(
            status="ACTIVE",
        ).select_related("attendance_session")]
    if covered_sessions:
        _recalculate_for_sessions(
            covered_sessions, school=school, membership=membership, request=request,
        )
        from school_dashboard.cache import invalidate_school

        invalidate_school(school.id)
    return excuse


def update_excuse(
    *, excuse_id: int, school, membership, reason_type: str | None = None,
    notes: str | None = None, targets: list[dict] | None = None, request=None,
) -> AbsenceExcuse:
    """تعديل عذر PENDING فقط — المعتمد يلغى ويعاد تسجيله، لا يعدل بصمت."""
    with transaction.atomic():
        excuse = AbsenceExcuse.objects.select_for_update().get(id=excuse_id, school=school)
        if excuse.status != AbsenceExcuseStatus.PENDING:
            _raise_not_pending(excuse)
        update_fields = ["updated_at"]
        if reason_type is not None:
            excuse.reason_type = reason_type
            update_fields.append("reason_type")
        if notes is not None:
            excuse.notes = notes[:500]
            update_fields.append("notes")
        if targets is not None:
            validated = _validate_targets(school, excuse.student, targets, allow_future=True)
            excuse.targets.all().delete()
            AbsenceExcuseTarget.objects.bulk_create(
                AbsenceExcuseTarget(
                    school=school,
                    excuse=excuse,
                    attendance_date=t["attendance_date"],
                    period_sequence=t.get("period_sequence"),
                )
                for t in validated
            )
        excuse.save(update_fields=update_fields)
        record_event(
            AuditAction.EXCUSE_UPDATED,
            request=request,
            actor=membership.user,
            school=school,
            target_type="AbsenceExcuse",
            target_id=excuse.id,
            metadata={"targets_replaced": targets is not None},
        )
    return excuse


def reject_excuse(
    *, excuse_id: int, school, membership, reason: str, request=None
) -> AbsenceExcuse:
    with transaction.atomic():
        excuse = AbsenceExcuse.objects.select_for_update().get(id=excuse_id, school=school)
        if excuse.status != AbsenceExcuseStatus.PENDING:
            _raise_not_pending(excuse)
        excuse.status = AbsenceExcuseStatus.REJECTED
        excuse.rejected_by_membership = membership
        excuse.rejected_at = dj_timezone.now()
        excuse.rejection_reason = reason[:300]
        excuse.save(
            update_fields=[
                "status",
                "rejected_by_membership",
                "rejected_at",
                "rejection_reason",
                "updated_at",
            ]
        )
        record_event(
            AuditAction.EXCUSE_REJECTED,
            request=request,
            actor=membership.user,
            school=school,
            target_type="AbsenceExcuse",
            target_id=excuse.id,
        )
    return excuse


def add_attachment(
    *, excuse: AbsenceExcuse, school, membership, uploaded_file, request=None
) -> AbsenceExcuseAttachment:
    if excuse.status not in (AbsenceExcuseStatus.PENDING, AbsenceExcuseStatus.APPROVED):
        raise ApiError(
            "VALIDATION_ERROR", "لا يمكن إضافة مرفق لعذر مرفوض أو ملغى.", status_code=409
        )
    mime_type = validate_excuse_attachment(uploaded_file)
    digest = hashlib.sha256()
    for chunk in uploaded_file.chunks():
        digest.update(chunk)
    uploaded_file.seek(0)

    with transaction.atomic():
        lock_school_capacity(school)
        require_storage_capacity(school, adding_bytes=uploaded_file.size)
        # قفل العذر: رفعان متزامنان كانا يقرآن العدد نفسه فيتجاوزان الحد معًا
        locked = AbsenceExcuse.objects.select_for_update().get(id=excuse.id)
        if locked.attachments.count() >= MAX_ATTACHMENTS_PER_EXCUSE:
            raise ApiError(
                "EXCUSE_ATTACHMENT_INVALID",
                f"عدد المرفقات يتجاوز الحد المسموح ({MAX_ATTACHMENTS_PER_EXCUSE}).",
            )
        attachment = AbsenceExcuseAttachment.objects.create(
            school=school,
            excuse=excuse,
            file=uploaded_file,
            original_filename=uploaded_file.name[:255],
            mime_type=mime_type,
            size_bytes=uploaded_file.size,
            checksum=digest.hexdigest(),
            uploaded_by_membership=membership,
        )
    record_event(
        AuditAction.EXCUSE_ATTACHMENT_UPLOADED,
        request=request,
        actor=membership.user,
        school=school,
        target_type="AbsenceExcuseAttachment",
        target_id=attachment.id,
        metadata={"excuse_id": excuse.id, "size_bytes": attachment.size_bytes},
    )
    return attachment


def remove_attachment(
    *, attachment: AbsenceExcuseAttachment, school, membership, request=None
) -> None:
    if attachment.excuse.status not in (AbsenceExcuseStatus.PENDING, AbsenceExcuseStatus.APPROVED):
        raise ApiError(
            "VALIDATION_ERROR",
            "لا يمكن حذف مرفق من عذر مرفوض أو ملغى.",
            status_code=409,
        )
    excuse_id = attachment.excuse_id
    stored_file = attachment.file
    # الصف أولًا ثم الملف بعد الـcommit (نفس قاعدة الحذف النهائي): العكس كان يترك
    # صفًا يشير إلى ملف مفقود فينكسر التنزيل بـ500 إذا فشل حذف الصف
    with transaction.atomic():
        attachment.delete()
        transaction.on_commit(lambda: stored_file.delete(save=False))
    record_event(
        AuditAction.EXCUSE_ATTACHMENT_REMOVED,
        request=request,
        actor=membership.user,
        school=school,
        target_type="AbsenceExcuseAttachment",
        metadata={"excuse_id": excuse_id},
    )
