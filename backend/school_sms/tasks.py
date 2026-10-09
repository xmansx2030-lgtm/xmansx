"""إرسال إشعار واحد: حالات غير مؤكدة لا يعاد إرسالها تلقائيًا."""

import logging

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from audit.models import AuditAction
from audit.services import record_event
from common.errors import ApiError
from common.tenant_rls import tenant_context
from parents.contact_security import recipient_blocked
from school_sms.models import AbsenceSmsNotice, AbsenceSmsStatus, SchoolSmsIntegration
from school_sms.providers import SmsProviderError, send_sms
from school_sms.security import decrypt_secret, recipient_hash
from school_sms.services import eligible_absences, recipient_issue, render_absence_message
from subscriptions.entitlements import has_entitlement

logger = logging.getLogger("xmansx.sms")


def _finish(notice_id: int, *, school_id: int, status: str,
            code: str = "", reference: str = "") -> None:
    with tenant_context(school_id=school_id), transaction.atomic():
        notice = AbsenceSmsNotice.objects.select_for_update().get(id=notice_id, school_id=school_id)
        if notice.status != AbsenceSmsStatus.SENDING:
            return
        notice.status = status
        notice.failure_code = code
        notice.provider_reference = reference[:100]
        if status == AbsenceSmsStatus.ACCEPTED:
            notice.accepted_at = timezone.now()
        notice.save(update_fields=["status", "failure_code", "provider_reference",
                                   "accepted_at", "updated_at"])
        record_event(
            AuditAction.SMS_ABSENCE_RESULT, school=notice.school,
            target_type="AbsenceSmsNotice", target_id=notice.id,
            metadata={"status": status, "code": code, "provider": notice.provider},
        )


@shared_task(name="school_sms.send_absence_notice", ignore_result=True)
def send_absence_notice(notice_id: int) -> str:
    # الـ queue يحمل معرفًا فقط؛ نقرأ المدرسة في bypass ضيق ثم نعود لعزلها.
    with tenant_context(bypass=True):
        school_id = AbsenceSmsNotice.objects.filter(id=notice_id).values_list(
            "school_id", flat=True
        ).first()
    if school_id is None:
        return "skipped"

    with tenant_context(school_id=school_id), transaction.atomic():
        notice = (
            AbsenceSmsNotice.objects.select_for_update().select_related("school", "student")
            .filter(id=notice_id, school_id=school_id).first()
        )
        if notice is None or notice.status != AbsenceSmsStatus.QUEUED:
            return "skipped"
        if not has_entitlement(notice.school, "ABSENCE_SMS"):
            notice.status = AbsenceSmsStatus.FAILED
            notice.failure_code = "FEATURE_NOT_INCLUDED_IN_PLAN"
            notice.save(update_fields=["status", "failure_code", "updated_at"])
            return "failed"
        integration = SchoolSmsIntegration.objects.filter(
            school_id=school_id, is_active=True
        ).first()
        summary = (
            eligible_absences(school=notice.school, attendance_date=notice.attendance_date)
            .filter(student_id=notice.student_id).first()
        )
        if (
            integration is None or summary is None
            or summary.absence_status != notice.absence_status
            or integration.provider != notice.provider
            or recipient_issue(summary.student.guardian_mobile)
            or recipient_hash(summary.student.guardian_mobile) != notice.recipient_hash
            or recipient_blocked(
                school=notice.school, student_id=notice.student_id,
                mobile=summary.student.guardian_mobile,
            )
            or not notice.school.is_operational
        ):
            notice.status = AbsenceSmsStatus.FAILED
            notice.failure_code = "PRE_SEND_STATE_CHANGED"
            notice.save(update_fields=["status", "failure_code", "updated_at"])
            return "failed"
        try:
            secret = decrypt_secret(integration.secret_encrypted)
        except ApiError:
            notice.status = AbsenceSmsStatus.FAILED
            notice.failure_code = "CREDENTIAL_UNAVAILABLE"
            notice.save(update_fields=["status", "failure_code", "updated_at"])
            return "failed"
        message = render_absence_message(school=notice.school, summary=summary)
        mobile = summary.student.guardian_mobile
        provider = integration.provider
        username = integration.username
        sender = integration.sender_name
        notice.status = AbsenceSmsStatus.SENDING
        notice.message_text = message
        notice.attempted_at = timezone.now()
        notice.save(update_fields=["status", "message_text", "attempted_at", "updated_at"])

    try:
        result = send_sms(
            provider=provider, username=username, secret=secret,
            sender=sender, mobile=mobile, message=message,
        )
    except SmsProviderError as exc:
        status = AbsenceSmsStatus.UNKNOWN if exc.ambiguous else AbsenceSmsStatus.FAILED
        _finish(notice_id, school_id=school_id, status=status, code=exc.code)
        return status.lower()
    except Exception:
        # قد يكون الطلب وصل رغم استثناء غير متوقع؛ لا نعيده تلقائيًا ولا نسجل الأسرار.
        logger.exception("SMS delivery outcome unknown for notice %s", notice_id)
        _finish(notice_id, school_id=school_id, status=AbsenceSmsStatus.UNKNOWN,
                code="UNEXPECTED_ERROR")
        return "unknown"
    _finish(notice_id, school_id=school_id, status=AbsenceSmsStatus.ACCEPTED,
            reference=result.reference)
    return "accepted"
