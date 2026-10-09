"""Offline privacy proof through Sentry's actual default event scrubber."""

import json

from sentry_sdk.scrubber import EventScrubber

from operations.error_tracking import before_send

SYNTHETIC_SECRETS = (
    "synthetic-raw-activation-token",
    "synthetic-receipt-token",
    "+966550099000",
    "1999900001",
    "synthetic-private-verification-note",
)


def parent_exception_event():
    token, receipt, mobile, identifier, note = SYNTHETIC_SECRETS
    activation_url = f"https://family.example/parent/activate#token={token}"
    return {
        "request": {
            "url": "https://family.example/api/v1/staff/parents/registrations/42/decision/",
            "data": {"student_identifier": identifier, "mobile": mobile},
        },
        "exception": {
            "values": [
                {
                    "type": "RuntimeError",
                    "value": f"Failed parent request for {mobile}: {activation_url}",
                    "stacktrace": {
                        "frames": [
                            {
                                "module": "parents.services",
                                "filename": "parents/services.py",
                                "lineno": 101,
                                "vars": {
                                    "raw_token": token,
                                    "receipt": receipt,
                                    "activation_url": activation_url,
                                    "data": {
                                        "token": token,
                                        "mobile": mobile,
                                        "student_identifier": identifier,
                                    },
                                },
                            },
                            {
                                "module": "rest_framework.serializers",
                                "vars": {"validated_data": {"token": token, "mobile": mobile}},
                            },
                        ]
                    },
                }
            ]
        },
        "extra": {
            "error_code": "PARENT_ACTIVATION_FAILED",
            "request_id": "synthetic-request-id",
            "debug_context": f"Activation link: {activation_url}",
            "nested": [
                {
                    "activation_url": activation_url,
                    "receipt_token": receipt,
                    "raw_token": token,
                    "mobile": mobile,
                    "national_id": identifier,
                    "student_identifier": identifier,
                    "verification_note": note,
                }
            ],
        },
    }


def test_parent_exception_telemetry_has_no_bearers_plaintext_identity_or_private_proof():
    event = parent_exception_event()
    # This reproduces the actual SDK defaults, including nonrecursive frame scrubbing.
    # It performs no initialization, capture, transport or network request.
    EventScrubber().scrub_event(event)
    scrubbed = before_send(event, {})
    encoded = json.dumps(scrubbed, default=str)
    for secret in SYNTHETIC_SECRETS:
        assert secret not in encoded
    for frame in scrubbed["exception"]["values"][0]["stacktrace"]["frames"]:
        assert "vars" not in frame
    assert scrubbed["exception"]["values"][0]["type"] == "RuntimeError"
    assert scrubbed["extra"]["error_code"] == "PARENT_ACTIVATION_FAILED"
    assert scrubbed["extra"]["request_id"] == "synthetic-request-id"


def test_parent_route_scrubs_telemetry_when_no_parent_stack_frame_is_available():
    event = parent_exception_event()
    event["exception"]["values"][0]["stacktrace"]["frames"] = [
        {
            "module": "rest_framework.serializers",
            "vars": {"data": {"receipt": SYNTHETIC_SECRETS[1]}},
        }
    ]
    EventScrubber().scrub_event(event)
    encoded = json.dumps(before_send(event, {}), default=str)
    for secret in SYNTHETIC_SECRETS:
        assert secret not in encoded


def test_parent_stack_frame_scrubs_telemetry_without_http_request_context():
    event = parent_exception_event()
    event.pop("request")
    EventScrubber().scrub_event(event)
    encoded = json.dumps(before_send(event, {}), default=str)
    for secret in SYNTHETIC_SECRETS:
        assert secret not in encoded


def test_unrelated_exception_diagnostics_keep_existing_behavior():
    event = {
        "request": {"url": "https://app.example/api/v1/attendance/", "data": {"password": "bad"}},
        "exception": {
            "values": [
                {
                    "type": "RuntimeError",
                    "value": "Ordinary attendance diagnostic",
                    "stacktrace": {
                        "frames": [{"module": "attendance.api", "vars": {"counter": 7}}]
                    },
                }
            ]
        },
    }
    EventScrubber().scrub_event(event)
    scrubbed = before_send(event, {})
    assert "data" not in scrubbed["request"]
    exception = scrubbed["exception"]["values"][0]
    assert exception["value"] == "Ordinary attendance diagnostic"
    assert exception["stacktrace"]["frames"][0]["vars"] == {"counter": 7}
