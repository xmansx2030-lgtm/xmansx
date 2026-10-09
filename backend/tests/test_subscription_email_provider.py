"""Provider acceptance, uncertain responses and privacy; no external delivery."""

import json
from types import SimpleNamespace
from urllib.error import HTTPError, URLError
from uuid import uuid4

import pytest

from subscriptions.email_provider import send_subscription_email


@pytest.fixture
def message(settings):
    settings.SUBSCRIPTION_EMAIL_ENABLED = True
    settings.SUBSCRIPTION_EMAIL_FROM = "Subscription <billing@example.invalid>"
    settings.RESEND_API_KEY = "test-only-provider-key"
    return {"delivery_id": str(uuid4()), "recipient": "manager@example.invalid", "kind": "DETAILS",
            "snapshot": {"school_name": "<مدرسة>", "plan_name": "الباقة", "ends_at": "2026-11-01"}}


class Response:
    status = 200

    def __init__(self, raw):
        self.raw = raw

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self, size):
        return self.raw[:size]


def test_resend_protocol_idempotency_and_escaped_content(message, monkeypatch):
    reference = str(uuid4())
    captured = []

    def send(request, timeout):
        captured.append(request)
        assert timeout == 10
        return Response(json.dumps({"id": reference}).encode())

    monkeypatch.setattr("subscriptions.email_provider.build_opener",
                        lambda *args: SimpleNamespace(open=send))
    result = send_subscription_email(**message)
    assert result.status == "SUBMITTED_TO_PROVIDER" and result.provider_reference == reference
    request = captured[0]
    assert request.full_url == "https://api.resend.com/emails" and request.get_method() == "POST"
    assert request.get_header("Idempotency-key") == message["delivery_id"]
    body = json.loads(request.data)
    assert body["to"] == [message["recipient"]]
    assert "&lt;مدرسة&gt;" in body["html"]
    assert "password" not in body and "student" not in body


@pytest.mark.parametrize("code,status", [(400, "FAILED"), (401, "FAILED"), (429, "FAILED"),
                                        (302, "FAILED"), (409, "UNKNOWN"), (500, "UNKNOWN")])
def test_http_failures_do_not_persist_provider_payload(message, monkeypatch, code, status):
    def send(*args, **kwargs):
        raise HTTPError("https://api.resend.com/emails", code, message["recipient"], {}, None)

    monkeypatch.setattr("subscriptions.email_provider.build_opener",
                        lambda *args: SimpleNamespace(open=send))
    result = send_subscription_email(**message)
    assert result.status == status
    assert message["recipient"] not in str(result)


@pytest.mark.parametrize("raw", [b'{}', b'not-json', b'{"id":"not-a-uuid"}', b'x' * 4097])
def test_ambiguous_acceptance_is_unknown(message, monkeypatch, raw):
    monkeypatch.setattr("subscriptions.email_provider.build_opener",
                        lambda *args: SimpleNamespace(open=lambda *a, **k: Response(raw)))
    assert send_subscription_email(**message).status == "UNKNOWN"


def test_disabled_or_unconfigured_provider_makes_no_network_call(message, settings, monkeypatch):
    def forbidden(*args):
        raise AssertionError("network must not run")

    monkeypatch.setattr("subscriptions.email_provider.build_opener", forbidden)
    settings.SUBSCRIPTION_EMAIL_ENABLED = False
    assert send_subscription_email(**message).status == "FAILED"
    settings.SUBSCRIPTION_EMAIL_ENABLED = True
    settings.RESEND_API_KEY = ""
    assert send_subscription_email(**message).error_code == "SUBSCRIPTION_EMAIL_UNCONFIGURED"


def test_network_failure_is_unknown_without_raw_error(message, monkeypatch):
    def send(*args, **kwargs):
        raise URLError(message["recipient"])

    monkeypatch.setattr("subscriptions.email_provider.build_opener",
                        lambda *args: SimpleNamespace(open=send))
    result = send_subscription_email(**message)
    assert result.status == "UNKNOWN" and message["recipient"] not in str(result)
