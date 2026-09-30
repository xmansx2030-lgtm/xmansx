"""إعداد مزود المدرسة وتحضير إشعارات غياب معتمدة دون خلط المستأجرين."""

from datetime import date, timedelta

from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone

from accounts.mobile import NORMALIZED_MOBILE_RE, mask_mobile
from attendance.models import DailyAbsenceStatus, DailyAttendanceSummary
from audit.models import AuditAction
from audit.services import record_event
from common.errors import ApiError
from school_sms.models import AbsenceSmsNotice, AbsenceSmsStatus, SchoolSmsIntegration
from school_sms.security import encrypt_secret, recipient_hash
from schools.models import SchoolSettings
from schools.settings_models import DEFAULT_ABSENCE_SMS_MESSAGE_TEMPLATE
from students.models import StudentStatus
from students.services.enrollments import enrollments_on_date

MAX_SEND_BATCH = 50


def recipient_issue(mobile: str) -> str | None:
    if not mobile:
        return "MISSING_RECIPIENT"
    if not NORMALIZED_MOBILE_RE.fullmatch(mobile):
        return "INVALID_RECIPIENT"
    return None


def integration_payload(integration: SchoolSmsIntegration | None) -> dict:
    if integration is None:
        return {"provider": None, "username": "", "sender_name": "",
                "is_active": False, "has_secret": False}
    return {
        "provider": integration.provider,
        "username": integration.username,
        "sender_name": integration.sender_name,
        "is_active": integration.is_active,
        "has_secret": bool(integration.secret_encrypted),
    }


def save_integration(*, school, actor, data: dict, request=None) -> dict:
    with transaction.atomic():
        existing = SchoolSmsIntegration.objects.select_for_update().filter(school=school).first()
        provider = data["provider"]
        secret = data.get("api_key", "").strip()
        if not secret and (existing is None or existing.provider != provider):
            raise ApiError(
                "SMS_KEY_REQUIRED", "أدخل مفتاح API الخاص بالمزود المختار.", status_code=400
            )
        values = {
            "provider": provider,
            "username": data["username"].strip(),
            "sender_name": data["sender_name"].strip(),
            "is_active": data["is_active"],
        }
        if secret:
            values["secret_encrypted"] = encrypt_secret(secret)
        if existing is None:
            existing = SchoolSmsIntegration.objects.create(school=school, **values)
        else:
            for field, value in values.items():
                setattr(existing, field, value)
            existing.save(update_fields=[*values, "updated_at"])
        record_event(
            AuditAction.SMS_INTEGRATION_UPDATED, request=request, actor=actor, school=school,
            target_type="SchoolSmsIntegration", target_id=existing.id,
            metadata={"provider": provider, "is_active": existing.is_active,
                      "key_changed": bool(secret)},
        )
    return integration_payload(existing)


def candidate_absences(*, school, attendance_date: date) -> QuerySet:
    enrolled_ids = enrollments_on_date(school=school, on_date=attendance_date).values(
        "student_id"
    )
    return (
        DailyAttendanceSummary.objects.filter(
            school=school,
            attendance_date=attendance_date,
            student_id__in=enrolled_ids,
            student__status=StudentStatus.ACTIVE,
            absence_status=DailyAbsenceStatus.FULL,
        )
        .select_related("student", "section__grade")
        .order_by("section__grade__sequence", "section__code", "student__full_name", "student_id")
    )


def eligible_absences(*, school, attendance_date: date) -> QuerySet:
    return candidate_absences(school=school, attendance_date=attendance_date).filter(
        unexcused_absent_periods__gt=0,
        submitted_periods__gt=0,
    )


def absence_message_template(*, school) -> str:
    return SchoolSettings.objects.filter(school=school).values_list(
        "absence_sms_message_template", flat=True
    ).first() or DEFAULT_ABSENCE_SMS_MESSAGE_TEMPLATE


def render_absence_message(*, school, summary) -> str:
    first_name = summary.student.full_name.split(maxsplit=1)[0]
    return (
        absence_message_template(school=school)
        .replace("«اسم الطالب»", first_name)
        .replace("«التاريخ»", summary.attendance_date.isoformat())
    )


def absence_preview(*, school, attendance_date: date, page: int = 1) -> dict:
    integration = SchoolSmsIntegration.objects.filter(school=school).first()
    rows = list(candidate_absences(school=school, attendance_date=attendance_date))
    candidate_ids = [row.student_id for row in rows]
    ready_ids = [
        row.student_id
        for row in eligible_absences(school=school, attendance_date=attendance_date)
        if recipient_issue(row.student.guardian_mobile) is None
    ]
    page = max(page, 1)
    entries = rows[(page - 1) * MAX_SEND_BATCH:page * MAX_SEND_BATCH]
    stale_before = timezone.now() - timedelta(minutes=5)
    notice_states = {}
    for notice in AbsenceSmsNotice.objects.filter(
        school=school, attendance_date=attendance_date,
    ):
        status = (
            AbsenceSmsStatus.UNKNOWN
            if notice.status == AbsenceSmsStatus.SENDING and notice.updated_at < stale_before
            else notice.status
        )
        notice_states[notice.student_id] = (status, notice.failure_code)
    selectable_ids = [
        student_id for student_id in ready_ids
        if notice_states.get(student_id, (None, ""))[0] in (None, AbsenceSmsStatus.FAILED)
    ]

    def candidate_payload(row) -> dict:
        if row.submitted_periods == 0:
            reason = "NO_APPROVED_ATTENDANCE"
        elif row.unexcused_absent_periods == 0:
            reason = "EXCUSED_ABSENCE"
        elif recipient_issue(row.student.guardian_mobile):
            reason = recipient_issue(row.student.guardian_mobile)
        else:
            reason = None
        return {
            "student_id": row.student_id,
            "full_name": row.student.full_name,
            "grade_name": row.section.grade.name,
            "section_name": row.section.name,
            "absence_status": row.absence_status,
            "submitted_periods": row.submitted_periods,
            "expected_periods": row.expected_periods,
            "required_periods": 1,  # Compatibility with clients loaded before this release.
            "eligibility_reason": reason,
            "recipient_masked": mask_mobile(row.student.guardian_mobile)
            if row.student.guardian_mobile else "",
            "send_status": notice_states.get(row.student_id, (None, ""))[0],
            "send_error": notice_states.get(row.student_id, (None, ""))[1],
        }

    return {
        "date": attendance_date.isoformat(),
        "page": page,
        "page_size": MAX_SEND_BATCH,
        "total": len(candidate_ids),
        "ready_total": len(selectable_ids),
        "candidate_student_ids": candidate_ids,
        "selectable_student_ids": selectable_ids,
        "contact_issues": [
            {
                "student_id": row.student_id,
                "full_name": row.student.full_name,
                "grade_name": row.section.grade.name,
                "section_name": row.section.name,
                "reason": recipient_issue(row.student.guardian_mobile),
            }
            for row in rows
            if recipient_issue(row.student.guardian_mobile)
        ],
        "min_approved_periods": 1,  # Effective policy for older clients.
        "message_template": absence_message_template(school=school),
        "default_message_template": DEFAULT_ABSENCE_SMS_MESSAGE_TEMPLATE,
        "integration": {
            "provider": integration.provider if integration else None,
            "sender_name": integration.sender_name if integration else "",
            "is_active": bool(integration and integration.is_active),
        },
        "students": [candidate_payload(row) for row in entries],
    }


def queue_absence_sms(*, school, actor, attendance_date: date,
                      student_ids: list[int], request=None) -> dict:
    if (
        not student_ids or len(student_ids) > MAX_SEND_BATCH
        or len(set(student_ids)) != len(student_ids)
    ):
        raise ApiError("SMS_SELECTION_INVALID", "حدد من 1 إلى 50 طالبًا دون تكرار.")
    with transaction.atomic():
        integration = SchoolSmsIntegration.objects.select_for_update().filter(school=school).first()
        if integration is None or not integration.is_active:
            raise ApiError("SMS_INTEGRATION_INACTIVE", "فعّل ربط الرسائل في إعدادات المدرسة.")
        summaries = {
            row.student_id: row
            for row in eligible_absences(school=school, attendance_date=attendance_date)
            .filter(student_id__in=student_ids)
        }
        if len(summaries) != len(student_ids):
            raise ApiError(
                "SMS_ABSENCE_CHANGED", "تغيرت بيانات الغياب؛ حدّث المعاينة قبل الإرسال.",
                status_code=409,
            )
        if any(not row.student.guardian_mobile for row in summaries.values()):
            raise ApiError("SMS_RECIPIENT_MISSING", "يوجد طالب بلا جوال ولي أمر؛ صحح رقمه أولًا.")
        if any(recipient_issue(row.student.guardian_mobile) for row in summaries.values()):
            raise ApiError("SMS_RECIPIENT_INVALID", "يوجد رقم جوال ولي أمر غير صحيح؛ صححه أولًا.")
        queued = []
        skipped = []
        for student_id in student_ids:
            row = summaries[student_id]
            defaults = {
                "absence_status": row.absence_status,
                "provider": integration.provider,
                "recipient_masked": mask_mobile(row.student.guardian_mobile),
                "recipient_hash": recipient_hash(row.student.guardian_mobile),
                "requested_by": actor,
            }
            notice, created = AbsenceSmsNotice.objects.get_or_create(
                school=school, student_id=student_id, attendance_date=attendance_date,
                defaults=defaults,
            )
            if not created:
                notice = AbsenceSmsNotice.objects.select_for_update().get(pk=notice.pk)
                if notice.status != AbsenceSmsStatus.FAILED:
                    skipped.append(student_id)
                    continue
                for field, value in defaults.items():
                    setattr(notice, field, value)
                notice.status = AbsenceSmsStatus.QUEUED
                notice.failure_code = ""
                notice.provider_reference = ""
                notice.accepted_at = None
                notice.attempts += 1
                notice.save()
            queued.append(notice.id)
            record_event(
                AuditAction.SMS_ABSENCE_QUEUED, request=request, actor=actor, school=school,
                target_type="AbsenceSmsNotice", target_id=notice.id,
                metadata={"student_id": student_id, "date": attendance_date.isoformat(),
                          "provider": integration.provider},
            )

    from school_sms.tasks import send_absence_notice

    queue_failed = []
    for notice_id in queued:
        try:
            send_absence_notice.delay(notice_id)
        except Exception:
            AbsenceSmsNotice.objects.filter(
                id=notice_id, school=school, status=AbsenceSmsStatus.QUEUED
            ).update(status=AbsenceSmsStatus.FAILED, failure_code="QUEUE_UNAVAILABLE")
            queue_failed.append(notice_id)
    return {"queued": len(queued) - len(queue_failed), "skipped": len(skipped),
            "queue_failed": len(queue_failed)}
