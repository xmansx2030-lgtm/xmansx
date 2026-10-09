"""Bounded Resend transport for transactional subscription mail only."""

import json
import ssl
from dataclasses import dataclass
from email.utils import parseaddr
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, HTTPSHandler, ProxyHandler, Request, build_opener
from uuid import UUID

from common.email_templates import SUBSCRIPTION_TITLES, render_subscription_email
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email

TITLES = SUBSCRIPTION_TITLES


@dataclass(frozen=True)
class DeliveryResult:
    status: str
    provider_reference: str = ""
    error_code: str = ""


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def render_message(kind, snapshot):
    return render_subscription_email(
        kind, snapshot, portal_origin=settings.PARENT_PORTAL_BASE_URL,
    )


def send_subscription_email(*, delivery_id, recipient, kind, snapshot):
    if not settings.SUBSCRIPTION_EMAIL_ENABLED:
        return DeliveryResult("FAILED", error_code="SUBSCRIPTION_EMAIL_DISABLED")
    key = settings.RESEND_API_KEY
    sender = settings.SUBSCRIPTION_EMAIL_FROM
    try:
        validate_email(recipient)
        validate_email(parseaddr(sender)[1])
        if (not key or not key.isascii() or any(ord(c) < 33 or ord(c) > 126 for c in key)
                or len(key) > 512 or len(sender) > 320 or "\r" in sender or "\n" in sender
                or not 1 <= settings.RESEND_TIMEOUT_SECONDS <= 30):
            raise ValueError("Invalid settings")
        delivery_id = str(UUID(str(delivery_id)))
        subject, text, html = render_message(kind, snapshot)
        body = json.dumps({"from": sender, "to": [recipient], "subject": subject,
                           "text": text, "html": html}, ensure_ascii=False).encode("utf-8")
        if len(body) > 16 * 1024:
            return DeliveryResult("FAILED", error_code="MESSAGE_TOO_LARGE")
    except (ValidationError, ValueError, TypeError, KeyError):
        return DeliveryResult("FAILED", error_code="SUBSCRIPTION_EMAIL_UNCONFIGURED")
    request = Request("https://api.resend.com/emails", data=body, method="POST", headers={
        "Authorization": f"Bearer {key}", "Content-Type": "application/json",
        "Accept": "application/json", "Idempotency-Key": delivery_id,
    })
    try:
        opener = build_opener(ProxyHandler({}), HTTPSHandler(context=ssl.create_default_context()),
                              NoRedirect())
        with opener.open(request, timeout=settings.RESEND_TIMEOUT_SECONDS) as response:
            raw = response.read(4097)
            if len(raw) > 4096 or not 200 <= response.status < 300:
                return DeliveryResult("UNKNOWN", error_code="RESEND_INVALID_RESPONSE")
        reference = str(UUID(json.loads(raw.decode("utf-8"))["id"]))
        return DeliveryResult("SUBMITTED_TO_PROVIDER", provider_reference=reference)
    except HTTPError as exc:
        code = exc.code
        exc.close()
        uncertain = code == 409 or code >= 500
        return DeliveryResult("UNKNOWN" if uncertain else "FAILED",
                              error_code=f"RESEND_HTTP_{code}")
    except (URLError, TimeoutError, OSError):
        return DeliveryResult("UNKNOWN", error_code="RESEND_NETWORK_UNKNOWN")
    except Exception:
        # Response parsing failures after dispatch cannot prove rejection.
        return DeliveryResult("UNKNOWN", error_code="RESEND_RESPONSE_UNKNOWN")
