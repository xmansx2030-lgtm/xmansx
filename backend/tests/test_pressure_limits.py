"""Actual Redis counters and HTTP backpressure, including shared-school IPs."""

from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from django.test import override_settings
from redis.exceptions import ConnectionError
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from common.throttling import AccountPressureThrottle


def _request(user_id, path="/api/v1/auth/me/"):
    request = Request(APIRequestFactory().get(path, REMOTE_ADDR="192.0.2.1"))
    request.user = SimpleNamespace(is_authenticated=True, pk=user_id)
    return request


@override_settings(API_RATE_LIMIT_ENABLED=True, API_USER_REQUESTS_PER_MINUTE=20)
def test_account_counter_is_atomic_under_concurrency():
    def attempt(_):
        return AccountPressureThrottle().allow_request(_request(101), None)
    with ThreadPoolExecutor(max_workers=16) as executor:
        results = list(executor.map(attempt, range(40)))
    assert sum(results) == 20
    # Same NAT IP, independent account: no school-wide lockout.
    assert AccountPressureThrottle().allow_request(_request(102), None)


@override_settings(API_RATE_LIMIT_ENABLED=True, API_USER_EXPORTS_PER_MINUTE=2)
def test_exports_have_a_separate_budget_and_do_not_block_normal_reads():
    for _ in range(2):
        assert AccountPressureThrottle().allow_request(
            _request(101, "/api/v1/reports/absence/?_export_all=1"), None
        )
    throttle = AccountPressureThrottle()
    assert not throttle.allow_request(_request(101, "/api/v1/reports/absence/export.xlsx"), None)
    assert 0 < throttle.wait() <= 60
    assert AccountPressureThrottle().allow_request(_request(101), None)


@pytest.mark.django_db
def test_http_429_and_retry_after_preserve_normal_authentication(role_client, settings):
    client, _, _ = role_client(["SCHOOL_MANAGER"])
    settings.API_RATE_LIMIT_ENABLED = True
    settings.API_USER_REQUESTS_PER_MINUTE = 2
    assert client.get("/api/v1/auth/me/").status_code == 200
    assert client.get("/api/v1/auth/me/").status_code == 200
    denied = client.get("/api/v1/auth/me/")
    assert denied.status_code == 429
    assert denied.json()["code"] == "RATE_LIMITED"
    assert 0 < int(denied["Retry-After"]) <= 60
    assert client.get("/api/v1/auth/csrf/").status_code == 200
    assert client.post("/api/v1/auth/logout/").status_code == 200


@pytest.mark.django_db
def test_security_outage_fails_closed_but_health_remains_available(role_client, settings):
    client, _, _ = role_client(["SCHOOL_MANAGER"])
    settings.API_RATE_LIMIT_ENABLED = True
    backend = Mock()
    backend._cache.get_client.side_effect = ConnectionError("synthetic outage")
    with patch("common.throttling.caches", {"security": backend}):
        denied = client.get("/api/v1/auth/me/")
        assert denied.status_code == 503
        assert denied["Retry-After"] == "2"
        assert "synthetic outage" not in denied.content.decode()
        assert client.get("/api/v1/health/").status_code == 200
        assert client.get("/api/v1/readiness/").status_code == 200
        assert client.get("/api/v1/auth/csrf/").status_code == 200
        assert client.post("/api/v1/auth/logout/").status_code == 200
