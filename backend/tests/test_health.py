"""اختبارات health/readiness — readiness يتصل بـ PostgreSQL وRedis حقيقيين."""

import pytest
from django.test import Client, override_settings


def test_health_returns_ok():
    response = Client().get("/api/v1/health/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_does_not_leak_internals():
    body = Client().get("/api/v1/health/").json()
    assert set(body.keys()) == {"status"}


@pytest.mark.django_db
def test_readiness_ok_with_real_services():
    response = Client().get("/api/v1/readiness/")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["checks"] == {"database": "ok", "redis": "ok"}


@pytest.mark.django_db
@override_settings(REDIS_URL="redis://localhost:6390/0", READINESS_CHECK_TIMEOUT_SECONDS=1)
def test_readiness_fails_when_redis_unreachable():
    response = Client().get("/api/v1/readiness/")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["checks"]["redis"] == "error"
    assert body["checks"]["database"] == "ok"
    # لا تفاصيل داخلية في الاستجابة
    assert set(body.keys()) == {"status", "checks"}
