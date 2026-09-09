"""خدمة تسجيل أحداث التدقيق — الواجهة الوحيدة للكتابة في AuditLog."""

import logging

from django.http import HttpRequest

from audit.models import AuditLog

logger = logging.getLogger("xmansx.audit")

_SENSITIVE_KEYS = {"password", "raw_password", "password_confirmation", "national_id", "mobile"}


def client_ip(request: HttpRequest) -> str | None:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def record_event(
    action: str,
    *,
    request: HttpRequest | None = None,
    actor=None,
    school=None,
    target_type: str = "",
    target_id: str | int = "",
    metadata: dict | None = None,
) -> AuditLog:
    metadata = dict(metadata or {})
    # حارس أخير ضد تسرب الحقول الحساسة إلى سجل التدقيق
    for key in list(metadata):
        if key.lower() in _SENSITIVE_KEYS:
            metadata.pop(key)

    ip = None
    user_agent = ""
    request_id = ""
    if request is not None:
        ip = client_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")[:256]
        request_id = getattr(request, "request_id", "")[:64]
        if actor is None and getattr(request, "user", None) is not None:
            if request.user.is_authenticated:
                actor = request.user

    return AuditLog.objects.create(
        action=action,
        actor=actor,
        school=school,
        target_type=target_type,
        target_id=str(target_id),
        metadata=metadata,
        request_id=request_id,
        ip_address=ip,
        user_agent=user_agent,
    )
