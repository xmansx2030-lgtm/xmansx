"""Family invitations only. Existing absence send selection is never called here."""

import json
import os
import re
from pathlib import Path
from urllib.parse import urlsplit

from django.conf import settings

from parents.security import decrypt_value
from parents.services import portal_url
from school_sms.models import SchoolSmsIntegration
from school_sms.providers import SmsProviderError, send_sms
from school_sms.security import decrypt_secret


def send_family_sms(invitation, token):
    if not settings.PARENT_FAMILY_INVITATION_SMS_ENABLED:
        return "FAILED", "SMS_DISABLED", ""
    integration = SchoolSmsIntegration.objects.filter(
        school_id=invitation.school_id, is_active=True
    ).first()
    if integration is None:
        return "FAILED", "SMS_UNAVAILABLE", ""
    link = portal_url(f"/parent/invitation#token={token}")
    adapter = settings.PARENT_FAMILY_INVITATION_SMS_ADAPTER
    if adapter == "synthetic-file":
        isolated = getattr(settings, "SETTINGS_MODULE", "") == "config.settings.test" or (
            getattr(settings, "SETTINGS_MODULE", "") == "config.settings.parent_staging"
            and getattr(settings, "PARENT_STAGING_LOCAL_ONLY", False)
        )
        if not isolated or urlsplit(link).hostname not in {"localhost", "127.0.0.1"}:
            return "FAILED", "SYNTHETIC_ADAPTER_FORBIDDEN", ""
        root = Path(str(settings.PARENT_RECOVERY_SYNTHETIC_EMAIL_ROOT)) / "family-invitations"
        if (
            not root.is_absolute()
            or root.is_symlink()
            or any(parent.is_symlink() for parent in root.parents)
        ):
            return "FAILED", "SYNTHETIC_STORAGE_UNAVAILABLE", ""
        try:
            root.mkdir(mode=0o700, parents=True, exist_ok=True)
            root.chmod(0o700)
            descriptor = os.open(
                root / f"{invitation.id}.json",
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                0o600,
            )
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(
                    {
                        "id": str(invitation.id),
                        "purpose": "FAMILY_INVITATION_SMS",
                        "link": link,
                        "expires_at": invitation.expires_at.isoformat(),
                    },
                    stream,
                )
                stream.flush()
                os.fsync(stream.fileno())
            return "SENT", "", str(invitation.id)
        except OSError:
            return "UNKNOWN", "SYNTHETIC_STORAGE_UNAVAILABLE", ""
    if adapter != "provider":
        return "FAILED", "SMS_ADAPTER_UNCONFIGURED", ""
    try:
        secret = decrypt_secret(integration.secret_encrypted)
    except Exception:
        return "FAILED", "CREDENTIAL_UNAVAILABLE", ""
    try:
        outcome = send_sms(
            provider=integration.provider,
            username=integration.username,
            secret=secret,
            sender=integration.sender_name,
            mobile=decrypt_value(invitation.mobile_encrypted),
            message=(
                f"{invitation.school.name}: دعوة لتفعيل متابعة أبنائك على منصة المواظبة. {link}"
            ),
        )
    except SmsProviderError as exc:
        code = (
            exc.code if re.fullmatch(r"[A-Z0-9_]{1,60}", exc.code or "") else "SMS_PROVIDER_ERROR"
        )
        return "UNKNOWN" if exc.ambiguous else "FAILED", code, ""
    reference = (
        outcome.reference if re.fullmatch(r"[A-Za-z0-9_-]{1,100}", outcome.reference or "") else ""
    )
    return "SENT", "", reference
