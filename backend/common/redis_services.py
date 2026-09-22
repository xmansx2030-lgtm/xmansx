"""Central Redis role discovery without exposing connection strings."""

from urllib.parse import urlsplit

from django.conf import settings


def configured_redis_urls() -> dict[str, str]:
    """Return every configured Redis role, preserving the legacy health URL."""

    legacy = settings.REDIS_URL
    return {
        "cache": getattr(settings, "CACHE_REDIS_URL", legacy),
        "security": getattr(settings, "SECURITY_REDIS_URL", legacy),
        "celery_broker": getattr(settings, "CELERY_BROKER_URL", legacy),
        "celery_results": getattr(settings, "CELERY_RESULT_BACKEND", legacy),
        "legacy": legacy,
    }


def unique_redis_urls() -> tuple[str, ...]:
    """Deduplicate logical databases that share one physical Redis service."""

    services: dict[tuple, str] = {}
    for url in configured_redis_urls().values():
        parsed = urlsplit(url)
        identity = (
            parsed.scheme,
            parsed.hostname,
            parsed.port,
            parsed.username,
            parsed.password,
        )
        services.setdefault(identity, url)
    return tuple(services.values())
