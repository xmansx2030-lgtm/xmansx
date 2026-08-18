"""اختبارات Request-ID middleware."""

import re

from django.test import Client


def test_response_includes_generated_request_id():
    response = Client().get("/api/v1/health/")
    request_id = response.headers.get("X-Request-ID")
    assert request_id is not None
    assert re.fullmatch(r"[0-9a-f]{32}", request_id)


def test_valid_incoming_request_id_is_passed_through():
    response = Client().get("/api/v1/health/", headers={"X-Request-ID": "trace-abc-12345"})
    assert response.headers["X-Request-ID"] == "trace-abc-12345"


def test_unsafe_incoming_request_id_is_replaced():
    response = Client().get("/api/v1/health/", headers={"X-Request-ID": "bad id\nInjected: x"})
    request_id = response.headers["X-Request-ID"]
    assert request_id != "bad id\nInjected: x"
    assert re.fullmatch(r"[0-9a-f]{32}", request_id)
