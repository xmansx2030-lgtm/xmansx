"""قراءة متغيرات البيئة بشكل صريح وآمن.

القاعدة: الإعدادات الحساسة لا defaults لها في الإنتاج — نقصها يجب أن يفشل
التشغيل بوضوح (ImproperlyConfigured) بدل السقوط إلى قيمة غير آمنة.
"""

import os

from django.core.exceptions import ImproperlyConfigured

_UNSET = object()


def env_str(name: str, default: str | object = _UNSET) -> str:
    value = os.environ.get(name)
    if value is not None and value != "":
        return value
    if default is _UNSET:
        raise ImproperlyConfigured(f"Missing required environment variable: {name}")
    return default  # type: ignore[return-value]


def env_bool(name: str, default: bool | object = _UNSET) -> bool:
    value = os.environ.get(name)
    if value is None or value == "":
        if default is _UNSET:
            raise ImproperlyConfigured(f"Missing required environment variable: {name}")
        return default  # type: ignore[return-value]
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int | object = _UNSET) -> int:
    value = os.environ.get(name)
    if value is None or value == "":
        if default is _UNSET:
            raise ImproperlyConfigured(f"Missing required environment variable: {name}")
        return default  # type: ignore[return-value]
    try:
        return int(value)
    except ValueError as exc:
        raise ImproperlyConfigured(f"Environment variable {name} must be an integer") from exc


def env_float(name: str, default: float | object = _UNSET) -> float:
    value = os.environ.get(name)
    if value is None or value == "":
        if default is _UNSET:
            raise ImproperlyConfigured(f"Missing required environment variable: {name}")
        return default  # type: ignore[return-value]
    try:
        return float(value)
    except ValueError as exc:
        raise ImproperlyConfigured(f"Environment variable {name} must be a number") from exc


def env_list(name: str, default: list[str] | object = _UNSET) -> list[str]:
    value = os.environ.get(name)
    if value is None or value == "":
        if default is _UNSET:
            raise ImproperlyConfigured(f"Missing required environment variable: {name}")
        return default  # type: ignore[return-value]
    return [item.strip() for item in value.split(",") if item.strip()]
