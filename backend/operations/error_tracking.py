"""Optional privacy-first Sentry initialization."""

import logging
import re
from urllib.parse import urlsplit

from django.conf import settings

logger = logging.getLogger("xmansx.operations")

_initialized = False

_SENSITIVE_KEYS = {
    "authorization",
    "cookie",
    "cookies",
    "password",
    "temporary_password",
    "national_id",
    "bridge_secret",
    "device_secret",
    "email",
    "manager_email",
    "recipient",
}

_PARENT_SENSITIVE_KEYS = {
    "token", "raw_token", "activation_token", "activation_url", "receipt", "receipt_token",
    "receipt_url", "mobile", "guardian_mobile", "new_mobile", "student_identifier", "identifier",
    "guardian_name", "verification_note", "resolution_verification_note", "applicant_note",
    "decision_note", "decision_reason", "resolution_reason", "notes", "body",
    "new_password", "confirm_password", "current_password",
    "account_password_fingerprint", "account_mobile_fingerprint", "source_mobile_hash",
    "note_encrypted", "reference_id", "note", "reason",
    "email", "email_encrypted", "email_hash", "pending_email", "recipient", "html", "text",
    "resend_api_key", "api_key", "recovery_url", "verification_url", "token_hash",
}
_PARENT_BEARER_FRAGMENT = re.compile(
    r"#(?:token|receipt_token|activation_token)=[^\s\"'<>]+", re.IGNORECASE
)


def _event_frames(event):
    traces = [event.get("stacktrace", {})]
    exception_data = event.get("exception") or {}
    exceptions = exception_data.get("values") or []
    traces.extend(exception.get("stacktrace", {}) for exception in exceptions)
    return [frame for trace in traces if trace for frame in trace.get("frames", [])]


def _parent_context(event, frames):
    request_data = event.get("request")
    request_url = (request_data.get("url") or "") if isinstance(request_data, dict) else ""
    if urlsplit(request_url).path.startswith(
        (
            "/api/v1/parent/", "/api/v1/staff/parents/",
            "/api/v1/identity-review/parent-recovery/", "/api/v1/auth/parent-password-recovery/",
            "/api/v1/auth/register-school/", "/api/v1/auth/change-initial-password/",
            "/api/v1/auth/change-password/",
        )
    ):
        return True
    for frame in frames:
        module = frame.get("module") or ""
        filename = (frame.get("filename") or frame.get("abs_path") or "").replace("\\", "/")
        if (
            module == "parents"
            or module.startswith("parents.")
            or filename.startswith("parents/")
            or "/parents/" in filename
        ):
            return True
    return False


def _scrub(value, *, parent=False):
    if isinstance(value, dict):
        return {
            key: "[Filtered]"
            if key.lower() in _SENSITIVE_KEYS or (parent and key.lower() in _PARENT_SENSITIVE_KEYS)
            else _scrub(item, parent=parent)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_scrub(item, parent=parent) for item in value]
    if parent and isinstance(value, str):
        return _PARENT_BEARER_FRAGMENT.sub("#[Filtered]", value)
    return value


def before_send(event, hint):
    frames = _event_frames(event)
    parent = _parent_context(event, frames)
    if parent:
        # SDK default scrubbing is not recursive. Parent locals can hold decrypted
        # contacts, bearer URLs and whole validated payloads under arbitrary names.
        for frame in frames:
            frame.pop("vars", None)
        for exception in (event.get("exception") or {}).get("values") or []:
            if "value" in exception:
                exception["value"] = "[Filtered parent exception message]"
    request = event.get("request")
    if isinstance(request, dict):
        request.pop("data", None)
        request.pop("cookies", None)
        headers = request.get("headers")
        if isinstance(headers, dict):
            request["headers"] = {
                key: value
                for key, value in headers.items()
                if key.lower() not in {"authorization", "cookie", "x-bridge-token"}
            }
    event.pop("user", None)
    return _scrub(event, parent=parent)


def initialize_error_tracking() -> None:
    global _initialized
    dsn = getattr(settings, "SENTRY_DSN", "")
    if _initialized or not dsn:
        return
    import sentry_sdk

    sentry_sdk.init(
        dsn=dsn,
        environment=getattr(settings, "SENTRY_ENVIRONMENT", "production"),
        release=getattr(settings, "SENTRY_RELEASE", None) or None,
        send_default_pii=False,
        traces_sample_rate=getattr(settings, "SENTRY_TRACES_SAMPLE_RATE", 0.0),
        before_send=before_send,
    )
    _initialized = True
    logger.info("error_tracking_initialized")


def capture_operational_failure(code: str) -> None:
    logger.error("operational_failure", extra={"error_code": code})
    if not _initialized:
        return
    import sentry_sdk

    with sentry_sdk.push_scope() as scope:
        scope.set_tag("operational_error_code", code)
        sentry_sdk.capture_message(code, level="error")
