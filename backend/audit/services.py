"""خدمة تسجيل أحداث التدقيق — الواجهة الوحيدة للكتابة في AuditLog."""

import logging

from django.conf import settings
from django.http import HttpRequest

from audit.models import AuditLog
from common.tenant_rls import tenant_context

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

    event = {
        "action": action,
        "actor": actor,
        "school": school,
        "target_type": target_type,
        "target_id": str(target_id),
        "metadata": metadata,
        "request_id": request_id,
        "ip_address": ip,
        "user_agent": user_agent,
    }

    if settings.DATABASE_RLS_ENFORCED and school is None:
        # Login and platform events have no tenant yet. PostgreSQL applies the
        # SELECT policy to Django's INSERT ... RETURNING, so use a tightly
        # scoped bypass for this single write and immediately restore context.
        # School-owned events never take this path and remain tenant-enforced.
        with tenant_context(bypass=True):
            return AuditLog.objects.create(**event)

    return AuditLog.objects.create(**event)
