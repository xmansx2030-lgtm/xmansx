"""Regression coverage for school-owned absence SMS and uncertain delivery."""

from unittest.mock import patch
from uuid import uuid4

import pytest
from django.db import connection
from django.utils import timezone

from attendance.models import DailyAbsenceStatus, DailyAttendanceSummary, DailyCompleteness
from common.tenant_rls import clear_tenant_context, tenant_context
from school_sms.models import AbsenceSmsNotice, AbsenceSmsStatus, SchoolSmsIntegration
from school_sms.providers import SmsProviderError, SmsProviderResult, send_sms
from school_sms.security import decrypt_secret
from school_sms.tasks import send_absence_notice
from tests.attendance_helpers import setup_attendance_env

INTEGRATION_URL = "/api/v1/school/sms/integration/"
PREVIEW_URL = "/api/v1/school/sms/absences/preview/"
SEND_URL = "/api/v1/school/sms/absences/send/"


def _integration(client, *, provider="DREAMS", key="school-only-key"):
    return client.put(
        INTEGRATION_URL,
        {
            "provider": provider,
            "username": "school-account",
            "api_key": key,
            "sender_name": "School",
            "is_active": True,
        },
        content_type="application/json",
    )


def _absence(
    school, *, status=DailyAbsenceStatus.FULL, completeness=DailyCompleteness.COMPLETE, unexcused=1
):
    env = setup_attendance_env(school, students_count=1)
    student = env["students"][0]
    student.guardian_mobile = "+966500000001"
    student.save(update_fields=["guardian_mobile"])
    day = env["local_now"].date()
    summary = DailyAttendanceSummary.objects.create(
        school=school,
        student=student,
        academic_year=env["year"],
        section=env["section"],
        attendance_date=day,
        expected_periods=1,
        submitted_periods=1,
        absent_periods=1,
        present_periods=0,
        excused_absent_periods=1 - unexcused,
        unexcused_absent_periods=unexcused,
        completeness_status=completeness,
        absence_status=status,
        calculated_at=timezone.now(),
    )
    return student, summary, day


@pytest.mark.django_db
def test_school_integration_keeps_keys_encrypted_and_separate(role_client, make_school):
    school_a = make_school("مدرسة أ")
    school_b = make_school("مدرسة ب")
    manager_a, _, _ = role_client(["SCHOOL_MANAGER"], school_a)
    manager_b, _, _ = role_client(["SCHOOL_MANAGER"], school_b)

    assert _integration(manager_a, key="dreams-a-secret").status_code == 200
    stored_a = SchoolSmsIntegration.objects.get(school=school_a)
    assert stored_a.secret_encrypted != "dreams-a-secret"
    assert "dreams-a-secret" not in stored_a.secret_encrypted
    assert decrypt_secret(stored_a.secret_encrypted) == "dreams-a-secret"
    response_a = manager_a.get(INTEGRATION_URL)
    assert response_a.status_code == 200
    assert response_a.json()["has_secret"] is True
    assert "secret" not in str(response_a.content).lower().replace("has_secret", "")
    assert manager_b.get(INTEGRATION_URL).json()["provider"] is None

    assert _integration(manager_b, provider="MSEGAT", key="msegat-b-secret").status_code == 200
    assert SchoolSmsIntegration.objects.get(school=school_b).provider == "MSEGAT"
    assert (
        decrypt_secret(SchoolSmsIntegration.objects.get(school=school_a).secret_encrypted)
        == "dreams-a-secret"
    )

    # Keeping an unchanged provider keeps its current key; changing provider needs a new key.
    assert _integration(manager_a, key="").status_code == 200
    assert (
        decrypt_secret(SchoolSmsIntegration.objects.get(school=school_a).secret_encrypted)
        == "dreams-a-secret"
    )
    assert _integration(manager_a, provider="MSEGAT", key="").status_code == 400


@pytest.mark.django_db
def test_preview_and_send_are_school_scoped_deduplicated_and_mocked(role_client, make_school):
    school_a = make_school("مدرسة أ")
    school_b = make_school("مدرسة ب")
    manager_a, _, _ = role_client(["SCHOOL_MANAGER"], school_a)
    manager_b, _, _ = role_client(["SCHOOL_MANAGER"], school_b)
    student_a, _, day = _absence(school_a)
    student_b, _, _ = _absence(school_b)
    assert _integration(manager_a).status_code == 200
    assert _integration(manager_b, provider="MSEGAT", key="school-b-key").status_code == 200

    preview = manager_a.get(PREVIEW_URL, {"date": day.isoformat()})
    assert preview.status_code == 200
    assert preview.json()["total"] == 1
    candidate = preview.json()["students"][0]
    assert candidate["student_id"] == student_a.id
    assert candidate["recipient_masked"] != student_a.guardian_mobile
    assert candidate["send_error"] == ""
    assert student_b.id != candidate["student_id"]

    with patch(
        "school_sms.tasks.send_sms", return_value=SmsProviderResult(reference="42")
    ) as provider:
        sent = manager_a.post(
            SEND_URL,
            {"date": day.isoformat(), "student_ids": [student_a.id]},
            content_type="application/json",
        )
        assert sent.status_code == 202
        assert sent.json()["queued"] == 1
        assert provider.call_count == 1
        assert provider.call_args.kwargs["secret"] == "school-only-key"
        assert provider.call_args.kwargs["mobile"] == student_a.guardian_mobile
        notice = AbsenceSmsNotice.objects.get(school=school_a, student=student_a)
        assert notice.status == AbsenceSmsStatus.ACCEPTED
        assert notice.provider_reference == "42"

        duplicate = manager_a.post(
            SEND_URL,
            {"date": day.isoformat(), "student_ids": [student_a.id]},
            content_type="application/json",
        )
        assert duplicate.status_code == 202
        assert duplicate.json()["skipped"] == 1
        assert provider.call_count == 1

        cross_school = manager_a.post(
            SEND_URL,
            {"date": day.isoformat(), "student_ids": [student_b.id]},
            content_type="application/json",
        )
        assert cross_school.status_code == 409
        assert provider.call_count == 1
        assert not AbsenceSmsNotice.objects.filter(school=school_a, student=student_b).exists()


@pytest.mark.django_db
def test_vice_can_send_but_cannot_change_integration_and_teacher_cannot_view(
    role_client, make_school
):
    school = make_school()
    manager, _, _ = role_client(["SCHOOL_MANAGER"], school)
    vice, _, _ = role_client(["VICE_PRINCIPAL"], school)
    teacher, _, _ = role_client(["TEACHER"], school)
    student, _, day = _absence(school)
    assert _integration(manager).status_code == 200
    assert vice.get(INTEGRATION_URL).status_code == 403
    assert _integration(vice, key="different-key").status_code == 403
    assert vice.get(PREVIEW_URL, {"date": day.isoformat()}).status_code == 200
    assert teacher.get(PREVIEW_URL, {"date": day.isoformat()}).status_code == 403
    assert (
        teacher.post(
            SEND_URL,
            {"date": day.isoformat(), "student_ids": [student.id]},
            content_type="application/json",
        ).status_code
        == 403
    )
    with patch("school_sms.tasks.send_sms", return_value=SmsProviderResult()) as provider:
        response = vice.post(
            SEND_URL,
            {"date": day.isoformat(), "student_ids": [student.id]},
            content_type="application/json",
        )
    assert response.status_code == 202
    provider.assert_called_once()


@pytest.mark.django_db
def test_changed_absence_is_not_sent_and_uncertain_result_is_not_retried(role_client):
    manager, school, _ = role_client(["SCHOOL_MANAGER"])
    student, summary, day = _absence(school)
    assert _integration(manager).status_code == 200
    summary.completeness_status = DailyCompleteness.INCOMPLETE
    summary.save(update_fields=["completeness_status"])
    with patch("school_sms.tasks.send_sms") as provider:
        response = manager.post(
            SEND_URL,
            {"date": day.isoformat(), "student_ids": [student.id]},
            content_type="application/json",
        )
    assert response.status_code == 409
    provider.assert_not_called()
    summary.completeness_status = DailyCompleteness.COMPLETE
    summary.save(update_fields=["completeness_status"])

    with patch(
        "school_sms.tasks.send_sms",
        side_effect=SmsProviderError("TRANSPORT_UNCERTAIN", ambiguous=True),
    ) as provider:
        response = manager.post(
            SEND_URL,
            {"date": day.isoformat(), "student_ids": [student.id]},
            content_type="application/json",
        )
        assert response.status_code == 202
        assert AbsenceSmsNotice.objects.get(student=student).status == AbsenceSmsStatus.UNKNOWN
        uncertain = manager.get(PREVIEW_URL, {"date": day.isoformat()}).json()["students"][0]
        assert uncertain["send_status"] == "UNKNOWN"
        assert uncertain["send_error"] == "TRANSPORT_UNCERTAIN"
        repeat = manager.post(
            SEND_URL,
            {"date": day.isoformat(), "student_ids": [student.id]},
            content_type="application/json",
        )
        assert repeat.json()["skipped"] == 1
        assert provider.call_count == 1


@pytest.mark.django_db
def test_excused_absence_is_not_offered(role_client):
    manager, school, _ = role_client(["SCHOOL_MANAGER"])
    _, _, day = _absence(school, unexcused=0)
    assert manager.get(PREVIEW_URL, {"date": day.isoformat()}).json()["total"] == 0


@pytest.mark.django_db
def test_worker_rechecks_absence_before_calling_provider(role_client):
    manager, school, _ = role_client(["SCHOOL_MANAGER"])
    student, summary, day = _absence(school)
    assert _integration(manager).status_code == 200
    with patch("school_sms.tasks.send_absence_notice.delay") as enqueue:
        response = manager.post(
            SEND_URL,
            {"date": day.isoformat(), "student_ids": [student.id]},
            content_type="application/json",
        )
    assert response.status_code == 202
    enqueue.assert_called_once()
    summary.unexcused_absent_periods = 0
    summary.save(update_fields=["unexcused_absent_periods"])
    notice = AbsenceSmsNotice.objects.get(student=student)
    with patch("school_sms.tasks.send_sms") as provider:
        assert send_absence_notice(notice.id) == "failed"
    provider.assert_not_called()
    notice.refresh_from_db()
    assert notice.status == AbsenceSmsStatus.FAILED
    assert notice.failure_code == "PRE_SEND_STATE_CHANGED"


@pytest.mark.django_db(transaction=True)
def test_new_sms_tables_enforce_postgres_school_scope(make_school):
    school_a = make_school("مدرسة العزل أ")
    school_b = make_school("مدرسة العزل ب")
    for school in (school_a, school_b):
        SchoolSmsIntegration.objects.create(
            school=school,
            provider="DREAMS",
            username="account",
            secret_encrypted="encrypted",
            sender_name="School",
            is_active=False,
        )
    role_name = f"sms_rls_test_{uuid4().hex}"
    quoted_role = connection.ops.quote_name(role_name)
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"CREATE ROLE {quoted_role} NOSUPERUSER NOBYPASSRLS")
            cursor.execute(f"GRANT USAGE ON SCHEMA public TO {quoted_role}")
            cursor.execute(f"GRANT SELECT ON school_sms_schoolsmsintegration TO {quoted_role}")
            cursor.execute(f"GRANT SELECT ON school_sms_absencesmsnotice TO {quoted_role}")
            cursor.execute(f"SET ROLE {quoted_role}")
        clear_tenant_context()
        assert SchoolSmsIntegration.objects.count() == 0
        with tenant_context(school_id=school_a.id):
            assert list(SchoolSmsIntegration.objects.values_list("school_id", flat=True)) == [
                school_a.id
            ]
        with tenant_context(school_id=school_b.id):
            assert list(SchoolSmsIntegration.objects.values_list("school_id", flat=True)) == [
                school_b.id
            ]
    finally:
        with connection.cursor() as cursor:
            cursor.execute("RESET ROLE")
            cursor.execute(f"DROP OWNED BY {quoted_role}")
            cursor.execute(f"DROP ROLE IF EXISTS {quoted_role}")
        clear_tenant_context()


@pytest.mark.parametrize(
    ("provider", "response", "reference"),
    [
        ("DREAMS", "Result:123:966500000001", "123"),
        ("MSEGAT", '{"code":"M0000","id":"abc"}', "abc"),
    ],
)
def test_provider_accepts_documented_success(provider, response, reference):
    with patch("school_sms.providers._post", return_value=response):
        result = send_sms(
            provider=provider,
            username="user",
            secret="secret",
            sender="School",
            mobile="+966500000001",
            message="test",
        )
    assert result.reference == reference
