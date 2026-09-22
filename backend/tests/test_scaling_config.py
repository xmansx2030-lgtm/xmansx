"""Regression gates for horizontally scalable database and Redis settings."""

from unittest.mock import Mock

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings

from common.health import _check_redis
from common.redis_services import configured_redis_urls, unique_redis_urls
from config.database import postgres_database


def test_native_database_pool_is_bounded_and_disables_persistent_connections(monkeypatch):
    monkeypatch.setenv("DATABASE_POOL_ENABLED", "true")
    monkeypatch.setenv("DATABASE_POOL_MIN_SIZE", "1")
    monkeypatch.setenv("DATABASE_POOL_MAX_SIZE", "6")
    monkeypatch.setenv("DATABASE_POOL_TIMEOUT_SECONDS", "7")

    database = postgres_database(production=False)

    assert database["CONN_MAX_AGE"] == 0
    assert database["CONN_HEALTH_CHECKS"] is True
    assert database["OPTIONS"]["pool"] == {
        "min_size": 1,
        "max_size": 6,
        "timeout": 7,
        "max_idle": 300,
        "max_lifetime": 1800,
    }


def test_database_pool_rejects_an_unbounded_invalid_range(monkeypatch):
    monkeypatch.setenv("DATABASE_POOL_ENABLED", "true")
    monkeypatch.setenv("DATABASE_POOL_MIN_SIZE", "5")
    monkeypatch.setenv("DATABASE_POOL_MAX_SIZE", "2")

    with pytest.raises(ImproperlyConfigured, match="DATABASE_POOL_MIN_SIZE"):
        postgres_database(production=False)


@override_settings(
    REDIS_URL="redis://legacy/0",
    CACHE_REDIS_URL="redis://cache/0",
    SECURITY_REDIS_URL="redis://security/0",
    CELERY_BROKER_URL="redis://celery/0",
    CELERY_RESULT_BACKEND="redis://celery/0",
)
def test_redis_roles_are_separate_and_duplicate_services_are_pinged_once(monkeypatch):
    clients: dict[str, Mock] = {}

    def client_for(url, **_kwargs):
        client = Mock()
        client.ping.return_value = True
        clients[url] = client
        return client

    monkeypatch.setattr("common.health.redis.Redis.from_url", client_for)

    assert configured_redis_urls()["security"] == "redis://security/0"
    assert unique_redis_urls() == (
        "redis://cache/0",
        "redis://security/0",
        "redis://celery/0",
        "redis://legacy/0",
    )
    assert _check_redis() is True
    assert set(clients) == set(unique_redis_urls())
    assert all(client.ping.call_count == 1 for client in clients.values())
