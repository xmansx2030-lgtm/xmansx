"""Structured JSON logging.

ممنوع تسجيل: Authorization headers, cookies, passwords, national IDs,
محتوى المستندات المرفوعة. هذه الطبقة لا تستقبل أصلًا إلا حقولًا صريحة.
"""

import json
import logging
from contextvars import ContextVar
from datetime import UTC, datetime

# يضبطه RequestIDMiddleware لكل طلب
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

# حقول قياسية في LogRecord لا نكررها داخل الإخراج
_RESERVED = {
    "name",
    "msg",
    "args",
    "levelname",
    "levelno",
    "pathname",
    "filename",
    "module",
    "exc_info",
    "exc_text",
    "stack_info",
    "lineno",
    "funcName",
    "created",
    "msecs",
    "relativeCreated",
    "thread",
    "threadName",
    "processName",
    "process",
    "taskName",
    "message",
    "request_id",
}

_SENSITIVE_KEYS = {
    "authorization",
    "cookie",
    "cookies",
    "password",
    "temporary_password",
    "national_id",
    "bridge_secret",
    "device_secret",
    "secret_key",
    "token",
    "attachment_contents",
    "counselor_notes",
}


def _safe_value(key: str, value):
    normalized = key.lower()
    if normalized in _SENSITIVE_KEYS or any(
        marker in normalized for marker in ("password", "authorization", "secret", "national_id")
    ):
        return "[Filtered]"
    if isinstance(value, dict):
        return {nested_key: _safe_value(nested_key, item) for nested_key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe_value(key, item) for item in value]
    return value


class RequestIDFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
        }
        # حقول إضافية ممررة عبر extra= (مثل method/path/status_code/duration_ms)
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = _safe_value(key, value)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)
