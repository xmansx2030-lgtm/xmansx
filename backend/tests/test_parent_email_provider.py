"""Resend's bounded protocol and synthetic mailbox; no external email is sent."""

import io
import json
import stat
from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock
from urllib.error import HTTPError, URLError
from uuid import uuid4

import pytest
from django.test import override_settings

from parents.email_recovery_provider import (
    MAX_RESPONSE_BYTES,
    RESEND_ENDPOINT,
    EmailDeliveryResult,
    _NoRedirect,
    recovery_link,
    send_recovery_email,
)


@pytest.fixture
def message():
    return {
        "delivery_id": str(uuid4()), "recipient": "parent@example.invalid",
        "purpose": "PASSWORD_RESET", "token": "synthetic-token-" + "x" * 48,
        "expires_at": datetime.now(UTC) + timedelta(minutes=15),
    }


@pytest.fixture(autouse=True)
def provider_settings():
    with override_settings(
        PARENT_RECOVERY_EMAIL_ENABLED=True, PARENT_RECOVERY_EMAIL_ADAPTER="resend",
        RESEND_API_KEY="test-only-key-not-a-real-provider-key",
        RESEND_FROM_EMAIL="منصة المواظبة <recovery@example.invalid>",
        RESEND_TIMEOUT_SECONDS=10, PARENT_PORTAL_BASE_URL="https://localhost:8445",
    ):
        yield


def _response(monkeypatch, raw=None, status=200, failure=None):
    reference = str(uuid4())
    response = Mock(status=status)
    response.read.return_value = raw if raw is not None else json.dumps({"id": reference}).encode()
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    opener = Mock()
    opener.open.side_effect = failure
    if failure is None:
        opener.open.return_value = response
    build = Mock(return_value=opener)
    monkeypatch.setattr("parents.email_recovery_provider.build_opener", build)
    return reference, response, opener, build


@pytest.mark.parametrize("purpose", ["RECOVERY_EMAIL_VERIFICATION", "PASSWORD_RESET"])
def test_resend_explicit_protocol_and_secret_free_result(monkeypatch, message, purpose, caplog):
    message["purpose"] = purpose
    reference, response, opener, build = _response(monkeypatch)
    result = send_recovery_email(**message)
    assert result == EmailDeliveryResult("SUBMITTED_TO_PROVIDER", reference)
    request = opener.open.call_args.args[0]
    assert request.full_url == RESEND_ENDPOINT
    assert request.get_method() == "POST"
    assert request.get_header("Authorization") == "Bearer test-only-key-not-a-real-provider-key"
    assert request.get_header("Idempotency-key") == message["delivery_id"]
    assert opener.open.call_args.kwargs == {"timeout": 10.0}
    payload = json.loads(request.data)
    assert payload["to"] == [message["recipient"]]
    assert set(payload) == {"from", "to", "subject", "text", "html"}
    assert "#token=" in payload["text"]
    assert message["token"] in payload["text"]
    assert "school" not in payload and "student" not in payload
    assert response.read.call_args.args == (MAX_RESPONSE_BYTES + 1,)
    assert any(isinstance(handler, _NoRedirect) for handler in build.call_args.args)
    assert message["token"] not in repr(result) + caplog.text
    assert message["recipient"] not in repr(result) + caplog.text
    assert "test-only-key-not-a-real-provider-key" not in repr(result) + caplog.text


@pytest.mark.parametrize("status, expected, code", [
    (400, "FAILED", "RESEND_HTTP_400"), (401, "FAILED", "RESEND_HTTP_401"),
    (403, "FAILED", "RESEND_HTTP_403"), (409, "UNKNOWN", "RESEND_IDEMPOTENCY_UNKNOWN"),
    (422, "FAILED", "RESEND_HTTP_422"), (429, "FAILED", "RESEND_RATE_LIMITED"),
    (301, "FAILED", "RESEND_REDIRECT_REJECTED"), (307, "FAILED", "RESEND_REDIRECT_REJECTED"),
    (500, "UNKNOWN", "RESEND_SERVER_ERROR"), (503, "UNKNOWN", "RESEND_SERVER_ERROR"),
])
def test_provider_http_failures_never_parse_or_log_body(
    monkeypatch, message, status, expected, code, caplog,
):
    raw = io.BytesIO((message["token"] + message["recipient"]).encode())
    error = HTTPError(RESEND_ENDPOINT, status, message["token"], {}, raw)
    _, _, opener, _ = _response(monkeypatch, failure=error)
    result = send_recovery_email(**message)
    assert result == EmailDeliveryResult(expected, error_code=code)
    assert opener.open.call_count == 1
    assert raw.closed
    assert message["token"] not in repr(result) + caplog.text
    assert message["recipient"] not in repr(result) + caplog.text


@pytest.mark.parametrize("failure", [
    TimeoutError("secret-token"), URLError("secret-recipient"),
    OSError("private-key"), RuntimeError("raw-email-payload"),
])
def test_uncertain_transport_never_blindly_retries(monkeypatch, message, failure, caplog):
    _, _, opener, _ = _response(monkeypatch, failure=failure)
    result = send_recovery_email(**message)
    assert result.status == "UNKNOWN"
    assert opener.open.call_count == 1
    assert str(failure) not in repr(result) + caplog.text


@pytest.mark.parametrize("body", [
    b"not-json", b"[]", b"{}", b'{"id":"token-reflection"}', b"\xff",
    b"x" * (MAX_RESPONSE_BYTES + 1),
])
def test_accepted_but_invalid_response_stays_unknown(monkeypatch, message, body):
    _response(monkeypatch, raw=body)
    assert send_recovery_email(**message) == EmailDeliveryResult(
        "UNKNOWN", error_code="RESEND_INVALID_RESPONSE",
    )


@pytest.mark.parametrize("values", [
    {"RESEND_API_KEY": ""}, {"RESEND_API_KEY": "bad\nkey"},
    {"RESEND_FROM_EMAIL": ""}, {"RESEND_FROM_EMAIL": "sender@example.invalid\r\nBcc: x"},
    {"RESEND_TIMEOUT_SECONDS": 0}, {"RESEND_TIMEOUT_SECONDS": 31},
    {"PARENT_PORTAL_BASE_URL": "https://outside.invalid/base"},
    {"PARENT_PORTAL_BASE_URL": "http://outside.invalid"},
    {"PARENT_PORTAL_BASE_URL": "https://user:pass@outside.invalid"},
])
def test_invalid_provider_configuration_prevents_transport(monkeypatch, message, values):
    _, _, opener, _ = _response(monkeypatch)
    with override_settings(**values):
        result = send_recovery_email(**message)
    assert result.status == "FAILED"
    assert result.error_code == "RESEND_UNCONFIGURED"
    opener.open.assert_not_called()


def test_disallowed_purpose_and_disabled_feature_never_send(monkeypatch, message):
    _, _, opener, _ = _response(monkeypatch)
    with pytest.raises(ValueError, match="Unsupported recovery email purpose"):
        send_recovery_email(**(message | {"purpose": "STUDENT_ABSENCE"}))
    with override_settings(PARENT_RECOVERY_EMAIL_ENABLED=False):
        assert send_recovery_email(**message).error_code == "RECOVERY_EMAIL_DISABLED"
    with override_settings(PARENT_RECOVERY_EMAIL_ADAPTER="smtp"):
        assert send_recovery_email(**message).error_code == "RECOVERY_ADAPTER_UNCONFIGURED"
    opener.open.assert_not_called()


def test_redirect_handler_never_forwards_secret_request():
    result = _NoRedirect().redirect_request(None, None, 307, "redirect", {}, "https://evil.invalid")
    assert result is None


def test_fragment_link_has_no_query_and_templates_use_separate_routes(message):
    verify = recovery_link(purpose="RECOVERY_EMAIL_VERIFICATION", token=message["token"])
    reset = recovery_link(purpose="PASSWORD_RESET", token=message["token"])
    assert verify.startswith("https://localhost:8445/parent/verify-email#token=")
    assert reset.startswith("https://localhost:8445/reset-password#token=")
    assert "?" not in verify + reset


def test_synthetic_file_is_private_idempotent_and_not_an_external_send(
    monkeypatch, message, tmp_path,
):
    _, _, opener, _ = _response(monkeypatch)
    root = tmp_path / "mailbox"
    with override_settings(
        SETTINGS_MODULE="config.settings.test", PARENT_RECOVERY_EMAIL_ADAPTER="synthetic-file",
        PARENT_RECOVERY_SYNTHETIC_EMAIL_ROOT=root, RESEND_API_KEY="",
    ):
        result = send_recovery_email(**message)
        duplicate = send_recovery_email(**message)
        conflict = send_recovery_email(**(message | {"token": "changed-token-" + "x" * 48}))
    assert result == duplicate == EmailDeliveryResult(
        "SUBMITTED_TO_PROVIDER", message["delivery_id"],
    )
    assert conflict.status == "UNKNOWN"
    files = list(root.iterdir())
    assert len(files) == 1
    payload = json.loads(files[0].read_text(encoding="utf-8"))
    assert payload["purpose"] == "PASSWORD_RESET"
    assert payload["link"].endswith("#token=" + message["token"])
    assert stat.S_IMODE(root.stat().st_mode) == 0o700
    assert stat.S_IMODE(files[0].stat().st_mode) == 0o600
    opener.open.assert_not_called()


@pytest.mark.parametrize("values", [
    {"SETTINGS_MODULE": "config.settings.production"},
    {"SETTINGS_MODULE": "config.settings.local"},
    {"SETTINGS_MODULE": "config.settings.parent_staging", "PARENT_STAGING_LOCAL_ONLY": False},
    {"SETTINGS_MODULE": "config.settings.test", "RESEND_API_KEY": "not-empty"},
    {"SETTINGS_MODULE": "config.settings.test", "PARENT_PORTAL_BASE_URL": "https://outside.invalid"},
])
def test_synthetic_adapter_rejects_external_or_unrestricted_profiles(
    monkeypatch, message, tmp_path, values,
):
    _, _, opener, _ = _response(monkeypatch)
    root = tmp_path / "mailbox"
    with override_settings(
        PARENT_RECOVERY_EMAIL_ADAPTER="synthetic-file", PARENT_RECOVERY_SYNTHETIC_EMAIL_ROOT=root,
        RESEND_API_KEY="",
    ), override_settings(**values):
        result = send_recovery_email(**message)
    assert result.error_code == "SYNTHETIC_ADAPTER_FORBIDDEN"
    assert not root.exists()
    opener.open.assert_not_called()


def test_synthetic_recipient_requires_reserved_invalid_domain(message, tmp_path):
    with override_settings(
        SETTINGS_MODULE="config.settings.test", PARENT_RECOVERY_EMAIL_ADAPTER="synthetic-file",
        PARENT_RECOVERY_SYNTHETIC_EMAIL_ROOT=tmp_path / "mailbox", RESEND_API_KEY="",
    ):
        result = send_recovery_email(**(message | {"recipient": "possibly.real@example.com"}))
    assert result.error_code == "SYNTHETIC_ADAPTER_FORBIDDEN"


def test_synthetic_corrupt_existing_attempt_cannot_be_reported_submitted(message, tmp_path):
    target = tmp_path / f"{message['delivery_id']}.json"
    target.write_text("{}", encoding="utf-8")
    with override_settings(
        SETTINGS_MODULE="config.settings.test", PARENT_RECOVERY_EMAIL_ADAPTER="synthetic-file",
        PARENT_RECOVERY_SYNTHETIC_EMAIL_ROOT=tmp_path, RESEND_API_KEY="",
    ):
        result = send_recovery_email(**message)
    assert result.status == "UNKNOWN"
    assert target.read_text(encoding="utf-8") == "{}"


def _worker_services(monkeypatch, prepared, permitted=True):
    prepare = Mock(return_value=prepared)
    scope = Mock(side_effect=lambda value: nullcontext(permitted))
    finalize = Mock()
    monkeypatch.setattr("parents.email_recovery_services.prepare_email_delivery", prepare)
    monkeypatch.setattr("parents.email_recovery_services.email_delivery_send_scope", scope)
    monkeypatch.setattr("parents.email_recovery_services.finalize_email_delivery", finalize)
    return prepare, scope, finalize


@pytest.mark.parametrize("prepare_ok,scope_ok", [(False, True), (True, False)])
def test_worker_fresh_security_gate_prevents_any_provider_call(
    monkeypatch, message, prepare_ok, scope_ok,
):
    from parents.email_recovery_tasks import send_parent_recovery_email

    prepare, scope, finalize = _worker_services(
        monkeypatch, message if prepare_ok else None, scope_ok,
    )
    send = Mock()
    monkeypatch.setattr("parents.email_recovery_tasks.send_recovery_email", send)
    assert send_parent_recovery_email.run(message["delivery_id"]) == "skipped"
    prepare.assert_called_once_with(message["delivery_id"])
    assert scope.call_count == int(prepare_ok)
    send.assert_not_called()
    finalize.assert_not_called()


def test_worker_unexpected_provider_exception_cannot_reach_celery_log(
    monkeypatch, message, caplog,
):
    from parents.email_recovery_tasks import send_parent_recovery_email

    _, _, finalize = _worker_services(monkeypatch, message)
    send = Mock(side_effect=RuntimeError(message["token"] + message["recipient"]))
    monkeypatch.setattr("parents.email_recovery_tasks.send_recovery_email", send)
    assert send_parent_recovery_email.run(message["delivery_id"]) == "unknown"
    assert send.call_count == 1
    finalize.assert_called_once_with(
        message["delivery_id"], status="UNKNOWN", provider_reference="",
        error_code="DELIVERY_STATE_UNKNOWN",
    )
    assert send_parent_recovery_email.ignore_result
    assert send_parent_recovery_email.max_retries == 0
    assert message["token"] not in caplog.text
    assert message["recipient"] not in caplog.text


def test_worker_only_returns_bounded_status_and_finishes_under_send_scope(monkeypatch, message):
    from parents.email_recovery_tasks import send_parent_recovery_email

    _, _, finalize = _worker_services(monkeypatch, message)
    reference = str(uuid4())
    send = Mock(return_value=EmailDeliveryResult("SUBMITTED_TO_PROVIDER", reference))
    monkeypatch.setattr("parents.email_recovery_tasks.send_recovery_email", send)
    assert send_parent_recovery_email.run(message["delivery_id"]) == "submitted_to_provider"
    finalize.assert_called_once_with(
        message["delivery_id"], status="SUBMITTED_TO_PROVIDER", provider_reference=reference,
        error_code="",
    )
    assert send.call_args.kwargs == message
