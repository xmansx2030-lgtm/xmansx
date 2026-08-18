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
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "taskName", "message", "request_id",
}


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
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)
