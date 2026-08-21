"""Optional privacy-first Sentry initialization."""

import logging

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
}


def _scrub(value):
    if isinstance(value, dict):
        return {
            key: "[Filtered]" if key.lower() in _SENSITIVE_KEYS else _scrub(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_scrub(item) for item in value]
    return value


def before_send(event, hint):
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
    return _scrub(event)


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
