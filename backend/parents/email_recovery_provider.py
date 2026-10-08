"""Purpose-limited Resend transport; tokens exist only in task memory.

The synthetic adapter is restricted to isolated tests and loopback staging. Its
private files are an intentionally synthetic mailbox, never a production outbox.
No provider payload, recipient, key or link is returned in errors or logs.
"""

import json
import os
import ssl
from dataclasses import dataclass
from datetime import datetime
from email.utils import formataddr, parseaddr
from html import escape
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, ProxyHandler, Request, build_opener
from uuid import UUID

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email

RESEND_ENDPOINT = "https://api.resend.com/emails"
ALLOWED_PURPOSES = frozenset({"RECOVERY_EMAIL_VERIFICATION", "PASSWORD_RESET"})
ACTIVATION_PURPOSE = "PARENT_ACCOUNT_ACTIVATION"
MAX_RESPONSE_BYTES = 4096
MAX_REQUEST_BYTES = 16 * 1024


@dataclass(frozen=True)
class EmailDeliveryResult:
    status: str
    provider_reference: str = ""
    error_code: str = ""


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Redirects could forward the Authorization header or secret body.
        return None


def _delivery_id(value):
    return str(UUID(str(value)))


def recovery_link(*, purpose, token):
    if purpose not in ALLOWED_PURPOSES | {ACTIVATION_PURPOSE}:
        raise ValueError("Unsupported recovery email purpose")
    if not isinstance(token, str) or not 32 <= len(token) <= 128:
        raise ValueError("Invalid recovery token")
    origin = str(settings.PARENT_PORTAL_BASE_URL).rstrip("/")
    parsed = urlsplit(origin)
    if (
        not parsed.hostname or parsed.username or parsed.password
        or parsed.query or parsed.fragment or parsed.path not in {"", "/"}
        or (parsed.scheme != "https" and not (
            parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1"}
        ))
    ):
        raise ValueError("Invalid recovery origin")
    path = (
        "/parent/activate" if purpose == ACTIVATION_PURPOSE else
        "/parent/verify-email" if purpose == "RECOVERY_EMAIL_VERIFICATION" else "/reset-password"
    )
    return f"{origin}{path}#token={quote(token, safe='')}"


def _content(*, purpose, link, expires_at, school_name=""):
    verification = purpose == "RECOVERY_EMAIL_VERIFICATION"
    subject = (
        "توثيق بريد الاسترداد — منصة المواظبة" if verification
        else "استعادة كلمة المرور — منصة المواظبة"
    )
    heading = "توثيق بريد الاسترداد" if verification else "إنشاء كلمة مرور جديدة"
    explanation = (
        "طلبت توثيق هذا البريد لاستعادة كلمة المرور فقط. افتح الرابط وأكمل التحقق صراحةً."
        if verification else "وصلنا طلب لاستعادة كلمة مرور حسابك في منصة المواظبة."
    )
    if purpose == ACTIVATION_PURPOSE:
        subject = f"تفعيل بوابة ولي الأمر وتوثيق البريد — {school_name}"
        heading = "تفعيل الحساب وتوثيق البريد"
        explanation = (
            f"وافقت {school_name} على طلب الربط. أكمل التفعيل وتوثيق بريدك "
            "لتتمكن من متابعة أبنائك. إن كان لديك حساب، سجل الدخول إلى حسابك الحالي."
        )
    expires = expires_at.isoformat()
    caution = "إذا لم تطلب هذه العملية، تجاهل الرسالة. لن تتغير بيانات حسابك بمجرد فتح الرابط."
    text = f"منصة المواظبة\n{explanation}\n{heading}: {link}\nينتهي الرابط: {expires}\n{caution}"
    html = (
        '<html lang="ar" dir="rtl"><body style="font-family:Arial,sans-serif;'
        'background:#f5f7fa;padding:24px"><main style="max-width:560px;margin:auto;'
        'background:#fff;padding:24px;border-radius:12px"><h1>منصة المواظبة</h1>'
        f"<h2>{escape(heading)}</h2><p>{escape(explanation)}</p>"
        f'<p><a href="{escape(link, quote=True)}" style="display:inline-block;'
        'background:#14532d;color:#fff;padding:14px 24px;text-decoration:none;'
        f'border-radius:8px">{heading}</a></p>'
        f"<p>ينتهي الرابط: <bdi>{escape(expires)}</bdi></p><p>{caution}</p>"
        "</main></body></html>"
    )
    return subject, text, html


def _valid_sender(value):
    if (
        not isinstance(value, str) or not value or len(value) > 320
        or "\r" in value or "\n" in value
    ):
        return False
    _, address = parseaddr(value)
    try:
        validate_email(address)
    except ValidationError:
        return False
    return bool(address)


def _send_resend(*, delivery_id, recipient, purpose, token, expires_at, school_name=""):
    key = getattr(settings, "RESEND_API_KEY", "")
    sender = getattr(settings, "RESEND_FROM_EMAIL", "")
    if (
        not isinstance(key, str) or not key or len(key) > 512
        or not key.isascii() or any(ord(char) < 33 or ord(char) > 126 for char in key)
        or not _valid_sender(sender)
    ):
        return EmailDeliveryResult("FAILED", error_code="RESEND_UNCONFIGURED")
    try:
        timeout = float(getattr(settings, "RESEND_TIMEOUT_SECONDS", 10))
        if not 1 <= timeout <= 30:
            return EmailDeliveryResult("FAILED", error_code="RESEND_UNCONFIGURED")
        link = recovery_link(purpose=purpose, token=token)
        subject, text, html = _content(
            purpose=purpose, link=link, expires_at=expires_at, school_name=school_name,
        )
        if purpose == ACTIVATION_PURPOSE:
            sender = formataddr((f"{school_name} — منصة المواظبة", parseaddr(sender)[1]))
        body = json.dumps({
            "from": sender, "to": [recipient], "subject": subject, "html": html, "text": text,
        }, ensure_ascii=False).encode("utf-8")
        if len(body) > MAX_REQUEST_BYTES:
            return EmailDeliveryResult("FAILED", error_code="MESSAGE_TOO_LARGE")
        request = Request(
            RESEND_ENDPOINT, data=body, method="POST", headers={
                "Authorization": f"Bearer {key}", "Content-Type": "application/json",
                "Accept": "application/json", "Idempotency-Key": delivery_id,
                "User-Agent": "xmansx-parent-recovery/1",
            },
        )
        # Ignore process proxy variables; the transport destination is fixed.
        opener = build_opener(
            ProxyHandler({}), HTTPSHandler(context=ssl.create_default_context()), _NoRedirect(),
        )
        with opener.open(request, timeout=timeout) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES or not 200 <= response.status < 300:
                return EmailDeliveryResult("UNKNOWN", error_code="RESEND_INVALID_RESPONSE")
        try:
            payload = json.loads(raw.decode("utf-8"))
            reference = _delivery_id(payload["id"])
        except (ValueError, TypeError, KeyError, UnicodeError):
            return EmailDeliveryResult("UNKNOWN", error_code="RESEND_INVALID_RESPONSE")
        return EmailDeliveryResult("SUBMITTED_TO_PROVIDER", provider_reference=reference)
    except HTTPError as exc:
        # Deliberately do not parse, log or persist error bodies/headers.
        code = exc.code
        exc.close()
        if code == 429:
            return EmailDeliveryResult("FAILED", error_code="RESEND_RATE_LIMITED")
        if code == 409:
            # Resend also uses 409 for an identical request still in progress.
            # Without retaining/parsing its body, acceptance remains uncertain.
            return EmailDeliveryResult("UNKNOWN", error_code="RESEND_IDEMPOTENCY_UNKNOWN")
        if 300 <= code < 400:
            return EmailDeliveryResult("FAILED", error_code="RESEND_REDIRECT_REJECTED")
        if 400 <= code < 500:
            return EmailDeliveryResult("FAILED", error_code=f"RESEND_HTTP_{code}")
        return EmailDeliveryResult("UNKNOWN", error_code="RESEND_SERVER_ERROR")
    except (URLError, TimeoutError, OSError):
        return EmailDeliveryResult("UNKNOWN", error_code="RESEND_NETWORK_UNKNOWN")
    except (ValueError, TypeError, AttributeError):
        return EmailDeliveryResult("FAILED", error_code="RESEND_UNCONFIGURED")
    except Exception:
        # An unexpected failure after sending could still have been accepted.
        return EmailDeliveryResult("UNKNOWN", error_code="RESEND_DELIVERY_UNKNOWN")


def _synthetic_allowed(recipient):
    module = getattr(settings, "SETTINGS_MODULE", "")
    isolated = module == "config.settings.test" or (
        module == "config.settings.parent_staging"
        and getattr(settings, "PARENT_STAGING_LOCAL_ONLY", False)
    )
    origin = urlsplit(str(settings.PARENT_PORTAL_BASE_URL))
    return (
        isolated and not getattr(settings, "RESEND_API_KEY", "")
        and origin.hostname in {"localhost", "127.0.0.1"}
        and recipient.rsplit("@", 1)[-1].lower().endswith(".invalid")
    )


def _send_synthetic(*, delivery_id, recipient, purpose, token, expires_at, school_name=""):
    if not _synthetic_allowed(recipient):
        return EmailDeliveryResult("FAILED", error_code="SYNTHETIC_ADAPTER_FORBIDDEN")
    root = Path(str(getattr(settings, "PARENT_RECOVERY_SYNTHETIC_EMAIL_ROOT", "")))
    if not root.is_absolute() or root.is_symlink() or any(
        parent.is_symlink() for parent in root.parents
    ):
        return EmailDeliveryResult("FAILED", error_code="SYNTHETIC_STORAGE_UNAVAILABLE")
    try:
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        root.chmod(0o700)
        link = recovery_link(purpose=purpose, token=token)
        target = root / f"{delivery_id}.json"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(target, flags, 0o600)
        except FileExistsError:
            # The same attempt never overwrites its previous synthetic message.
            if target.is_symlink():
                return EmailDeliveryResult("UNKNOWN", error_code="SYNTHETIC_STORAGE_UNAVAILABLE")
            descriptor = os.open(target, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            with os.fdopen(descriptor, "rb") as stream:
                raw = stream.read(MAX_REQUEST_BYTES + 1)
            if len(raw) > MAX_REQUEST_BYTES:
                return EmailDeliveryResult("UNKNOWN", error_code="SYNTHETIC_STORAGE_UNAVAILABLE")
            existing = json.loads(raw.decode("utf-8"))
            if existing != {
                "delivery_id": delivery_id, "purpose": purpose, "to": recipient,
                "link": link, "expires_at": expires_at.isoformat(),
            }:
                return EmailDeliveryResult("UNKNOWN", error_code="SYNTHETIC_STORAGE_UNAVAILABLE")
            return EmailDeliveryResult("SUBMITTED_TO_PROVIDER", provider_reference=delivery_id)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump({
                "delivery_id": delivery_id, "purpose": purpose, "to": recipient,
                "link": link, "expires_at": expires_at.isoformat(),
            }, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        return EmailDeliveryResult("SUBMITTED_TO_PROVIDER", provider_reference=delivery_id)
    except (OSError, ValueError, TypeError):
        return EmailDeliveryResult("UNKNOWN", error_code="SYNTHETIC_STORAGE_UNAVAILABLE")


def send_recovery_email(*, delivery_id, recipient, purpose, token, expires_at: datetime):
    """Accept only the two credential purposes; never fall back to SMTP/SMS."""
    if purpose not in ALLOWED_PURPOSES:
        raise ValueError("Unsupported recovery email purpose")
    return _send_email(
        delivery_id=delivery_id, recipient=recipient, purpose=purpose, token=token,
        expires_at=expires_at,
    )


def send_activation_email(*, delivery_id, recipient, token, expires_at, school_name):
    """School-approved activation only; no students, notices or school password reset."""
    if not isinstance(school_name, str) or not school_name or len(school_name) > 250:
        return EmailDeliveryResult("FAILED", error_code="INVALID_SCHOOL_NAME")
    if "\r" in school_name or "\n" in school_name:
        return EmailDeliveryResult("FAILED", error_code="INVALID_SCHOOL_NAME")
    return _send_email(
        delivery_id=delivery_id, recipient=recipient, purpose=ACTIVATION_PURPOSE,
        token=token, expires_at=expires_at, school_name=school_name,
    )


def _send_email(*, delivery_id, recipient, purpose, token, expires_at, school_name=""):
    delivery_id = _delivery_id(delivery_id)
    try:
        validate_email(recipient)
    except (ValidationError, TypeError):
        return EmailDeliveryResult("FAILED", error_code="INVALID_RECIPIENT")
    if not getattr(settings, "PARENT_RECOVERY_EMAIL_ENABLED", False):
        return EmailDeliveryResult("FAILED", error_code="RECOVERY_EMAIL_DISABLED")
    arguments = {
        "delivery_id": delivery_id, "recipient": recipient, "purpose": purpose,
        "token": token, "expires_at": expires_at,
    }
    if purpose == ACTIVATION_PURPOSE:
        arguments["school_name"] = school_name
    adapter = getattr(settings, "PARENT_RECOVERY_EMAIL_ADAPTER", "resend")
    if adapter == "synthetic-file":
        return _send_synthetic(**arguments)
    if adapter != "resend":
        return EmailDeliveryResult("FAILED", error_code="RECOVERY_ADAPTER_UNCONFIGURED")
    return _send_resend(**arguments)
