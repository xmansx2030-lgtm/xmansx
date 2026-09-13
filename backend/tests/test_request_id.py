"""اختبارات Request-ID middleware."""

import re
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.http import HttpResponse
from django.test import Client, RequestFactory
from django.test.utils import override_settings

from common.middleware import SessionActivityMiddleware


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


class _Session(dict):
    """Small session double that exposes Django's modified-state contract."""

    def __init__(self):
        super().__init__()
        self.modified = False

    def __setitem__(self, key, value):
        self.modified = True
        super().__setitem__(key, value)


@override_settings(SESSION_ACTIVITY_TOUCH_INTERVAL_SECONDS=300)
def test_session_activity_is_touched_at_a_bounded_cadence():
    request = RequestFactory().get("/api/v1/health/")
    request.user = SimpleNamespace(is_authenticated=True)
    request.session = _Session()
    middleware = SessionActivityMiddleware(lambda _request: HttpResponse())
    first = datetime(2026, 9, 13, 8, 0, tzinfo=UTC)

    with patch("common.middleware.timezone.now", return_value=first):
        middleware(request)
    assert request.session.modified is True
    assert request.session[SessionActivityMiddleware._LAST_ACTIVITY_KEY] == int(first.timestamp())

    request.session.modified = False
    with patch("common.middleware.timezone.now", return_value=first + timedelta(seconds=299)):
        middleware(request)
    assert request.session.modified is False

    with patch("common.middleware.timezone.now", return_value=first + timedelta(seconds=300)):
        middleware(request)
    assert request.session.modified is True


def test_session_activity_does_not_write_after_a_server_error():
    request = RequestFactory().get("/api/v1/health/")
    request.user = SimpleNamespace(is_authenticated=True)
    request.session = _Session()

    SessionActivityMiddleware(lambda _request: HttpResponse(status=500))(request)

    assert request.session.modified is False
