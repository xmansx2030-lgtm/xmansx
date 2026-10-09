"""Bounded Redis cache connections; security failures remain fail-closed."""

import math

from django.core.exceptions import ImproperlyConfigured

from config.env import env_float, env_int


def cache_options(role: str) -> dict:
    prefix = f"{role.upper()}_REDIS"
    maximum = env_int(f"{prefix}_MAX_CONNECTIONS", 8)
    wait = env_float(f"{prefix}_POOL_TIMEOUT_SECONDS", 0.25)
    connect = env_float(f"{prefix}_CONNECT_TIMEOUT_SECONDS", 1.0)
    read = env_float(f"{prefix}_SOCKET_TIMEOUT_SECONDS", 1.0)
    invalid_timeouts = any(
        not math.isfinite(value) or value <= 0 for value in (wait, connect, read)
    )
    if maximum < 1 or invalid_timeouts:
        raise ImproperlyConfigured(f"{prefix} connection bounds must be positive")
    return {
        "pool_class": "redis.BlockingConnectionPool",
        "max_connections": maximum,
        "timeout": wait,
        "socket_connect_timeout": connect,
        "socket_timeout": read,
        "retry_on_timeout": False,
        "health_check_interval": 30,
    }
