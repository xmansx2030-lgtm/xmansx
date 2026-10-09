"""Real SMS workflows share the transport parser and persist honest delivery states."""

from unittest.mock import patch

import pytest

from parents.family_invitation_services import deliver_invitation
from parents.models import GuardianActivation, GuardianFamilyInvitation
from parents.services import deliver_activation
from school_sms.models import AbsenceSmsNotice, SchoolSmsIntegration
from school_sms.security import encrypt_secret
from school_sms.tasks import send_absence_notice
from tests.test_parent_family_invitations import STAFF, data
from tests.test_parent_family_invitations import family_env as _family_env
from tests.test_parent_portal import approve, post, register
from tests.test_parent_portal import portal_env as _portal_env
from tests.test_school_sms import HISTORY_URL, PREVIEW_URL, SEND_URL, _absence, _integration

pytestmark = pytest.mark.django_db(transaction=True)
portal_env = _portal_env
family_env = _family_env

RESPONSES = [
    pytest.param("Success", "SENT", "", id="bare-success"),
    pytest.param("Result: Success", "SENT", "", id="documented-success"),
    pytest.param("Result:123:966500000001", "SENT", "", id="numeric-reference"),
    pytest.param("-113", "FAILED", "DREAMS_113", id="rejected-insufficient-balance"),
    pytest.param("Result: unexpected", "UNKNOWN", "DREAMS_RESPONSE_UNKNOWN", id="uncertain"),
]


@pytest.mark.parametrize("raw,status,code", RESPONSES)
def test_absence_transport_response_persists_in_worker_and_history(role_client, raw, status, code):
    client, school, _ = role_client(["SCHOOL_MANAGER"])
    student, _, day = _absence(school)
    assert _integration(client).status_code == 200
    expected = "ACCEPTED" if status == "SENT" else status

    with patch("school_sms.providers._post", return_value=raw) as transport:
        response = client.post(
            SEND_URL, {"date": day.isoformat(), "student_ids": [student.id]},
            content_type="application/json",
        )
        assert response.status_code == 202, response.content
        notice = AbsenceSmsNotice.objects.get(school=school, student=student)
        assert notice.status == expected
        assert notice.failure_code == code
        assert bool(notice.accepted_at) == (expected == "ACCEPTED")
        history = client.get(HISTORY_URL.format(student_id=student.id)).json()["results"][0]
        assert history["status"] == expected
        preview = client.get(PREVIEW_URL, {"date": day.isoformat()}).json()["students"][0]
        assert preview["send_status"] == expected
        assert preview["send_error"] == code
        assert send_absence_notice(notice.id) == "skipped"
        transport.assert_called_once()


@pytest.mark.parametrize("raw,status,code", RESPONSES)
def test_registration_activation_uses_shared_parser_without_duplicate_send(
    portal_env, raw, status, code,
):
    env = portal_env
    SchoolSmsIntegration.objects.create(
        school=env["school"], provider="DREAMS", username="synthetic",
        sender_name="Synthetic", secret_encrypted=encrypt_secret("fake-test-key"), is_active=True,
    )
    item, _ = register(env)
    with patch("school_sms.providers._post", return_value=raw) as transport:
        response = approve(env, item, delivery="SMS")
        assert response["delivery_status"] == status
        activation = GuardianActivation.objects.get(request=item)
        assert activation.delivery_status == status
        assert activation.failure_code == code
        assert deliver_activation(
            school=env["school"], activation_id=activation.id, token="not-a-real-bearer",
        ) == status
        transport.assert_called_once()


@pytest.mark.parametrize("raw,status,code", RESPONSES)
def test_family_invitation_uses_shared_parser_and_never_retries(family_env, raw, status, code):
    env = family_env
    with patch("school_sms.providers._post", return_value=raw) as transport:
        response = post(env["staff"], STAFF, {"invitations": [data(env)]})
        assert response.status_code == 201, response.content
        invitation = GuardianFamilyInvitation.objects.get(
            id=response.json()["invitations"][0]["id"],
        )
        assert invitation.delivery_status == status
        assert invitation.failure_code == code
        assert set(GuardianActivation.objects.values_list("delivery_status", flat=True)) == {status}
        deliver_invitation(invitation.school_id, invitation.id, "not-a-real-bearer")
        transport.assert_called_once()
