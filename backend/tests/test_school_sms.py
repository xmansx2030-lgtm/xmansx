"""Regression coverage for school-owned absence SMS and uncertain delivery."""

from datetime import timedelta
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
from schools.settings_models import DEFAULT_ABSENCE_SMS_MESSAGE_TEMPLATE
from students.models import Section
from tests.attendance_helpers import make_students, setup_attendance_env

INTEGRATION_URL = "/api/v1/school/sms/integration/"
PREVIEW_URL = "/api/v1/school/sms/absences/preview/"
SEND_URL = "/api/v1/school/sms/absences/send/"
HISTORY_URL = "/api/v1/school/sms/students/{student_id}/history/"


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
def test_student_sms_history_shows_attempt_and_is_school_and_role_scoped(role_client, make_school):
    school_a = make_school("مدرسة أ")
    school_b = make_school("مدرسة ب")
    manager_a, _, _ = role_client(["SCHOOL_MANAGER"], school_a)
    vice_a, _, _ = role_client(["VICE_PRINCIPAL"], school_a)
    counselor_a, _, _ = role_client(["COUNSELOR"], school_a)
    manager_b, _, _ = role_client(["SCHOOL_MANAGER"], school_b)
    student, _, day = _absence(school_a)
    assert _integration(manager_a).status_code == 200

    with patch("school_sms.tasks.send_sms", return_value=SmsProviderResult(reference="42")):
        response = manager_a.post(
            SEND_URL,
            {"date": day.isoformat(), "student_ids": [student.id]},
            content_type="application/json",
        )
    assert response.status_code == 202
    url = HISTORY_URL.format(student_id=student.id)
    history = manager_a.get(url)
    assert history.status_code == 200
    assert history.json()["count"] == 1
    sent = history.json()["results"][0]
    assert sent["status"] == AbsenceSmsStatus.ACCEPTED
    assert sent["message_text"].startswith("ولي الأمر")
    assert sent["requested_at"]
    assert sent["attempted_at"]
    assert sent["accepted_at"]
    assert sent["recipient_masked"] != student.guardian_mobile
    assert vice_a.get(url).status_code == 200
    assert counselor_a.get(url).status_code == 403
    assert manager_b.get(url).status_code == 404

    old = AbsenceSmsNotice.objects.create(
        school=school_a, student=student, attendance_date=day - timedelta(days=1),
        absence_status=DailyAbsenceStatus.FULL, provider="DREAMS",
        recipient_masked=sent["recipient_masked"], recipient_hash="a" * 64,
        status=AbsenceSmsStatus.UNKNOWN,
    )
    old_history = manager_a.get(url).json()["results"]
    old_row = next(row for row in old_history if row["id"] == old.id)
    assert old_row["message_text"] == ""
    assert old_row["attempted_at"] is None
    assert old_row["accepted_at"] is None


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
    assert candidate["absence_status"] == DailyAbsenceStatus.FULL
    assert "message" not in candidate
    assert "«اسم الطالب»" in preview.json()["message_template"]
    assert preview.json()["message_template"] == DEFAULT_ABSENCE_SMS_MESSAGE_TEMPLATE
    assert preview.json()["default_message_template"] == DEFAULT_ABSENCE_SMS_MESSAGE_TEMPLATE
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
        assert provider.call_args.kwargs["message"] == (
            preview.json()["message_template"]
            .replace("«اسم الطالب»", student_a.full_name.split(maxsplit=1)[0])
            .replace("«التاريخ»", day.isoformat())
        )
        notice = AbsenceSmsNotice.objects.get(school=school_a, student=student_a)
        assert notice.status == AbsenceSmsStatus.ACCEPTED
        assert notice.provider_reference == "42"
        after_send = manager_a.get(PREVIEW_URL, {"date": day.isoformat()}).json()
        assert after_send["ready_total"] == 0
        assert after_send["selectable_student_ids"] == []

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
def test_manager_edits_one_school_template_and_worker_uses_first_name(role_client, make_school):
    school_a = make_school("مدرسة أ")
    school_b = make_school("مدرسة ب")
    manager_a, _, _ = role_client(["SCHOOL_MANAGER"], school_a)
    manager_b, _, _ = role_client(["SCHOOL_MANAGER"], school_b)
    vice_a, _, _ = role_client(["VICE_PRINCIPAL"], school_a)
    student, _, day = _absence(school_a)
    student.full_name = "أحمد محمد عبدالرحمن"
    student.save(update_fields=["full_name"])
    assert _integration(manager_a).status_code == 200

    settings_url = "/api/v1/school/settings/"
    invalid = manager_a.patch(
        settings_url, {"absence_sms_message_template": "غياب «اسم الطالب»"},
        content_type="application/json",
    )
    assert invalid.status_code == 400
    assert manager_a.get(PREVIEW_URL, {"date": day.isoformat()}).json()[
        "message_template"
    ] == DEFAULT_ABSENCE_SMS_MESSAGE_TEMPLATE

    custom = "تنبيه: الطالب «اسم الطالب» غائب في «التاريخ»."
    assert vice_a.patch(
        settings_url, {"absence_sms_message_template": custom},
        content_type="application/json",
    ).status_code == 403
    updated = manager_a.patch(
        settings_url, {"absence_sms_message_template": custom},
        content_type="application/json",
    )
    assert updated.status_code == 200
    assert updated.json()["absence_sms_message_template"] == custom
    assert vice_a.get(PREVIEW_URL, {"date": day.isoformat()}).json()[
        "message_template"
    ] == custom
    assert manager_b.get(PREVIEW_URL, {"date": day.isoformat()}).json()[
        "message_template"
    ] == DEFAULT_ABSENCE_SMS_MESSAGE_TEMPLATE

    with patch("school_sms.tasks.send_sms", return_value=SmsProviderResult()) as provider:
        response = manager_a.post(
            SEND_URL, {"date": day.isoformat(), "student_ids": [student.id]},
            content_type="application/json",
        )
    assert response.status_code == 202
    assert provider.call_args.kwargs["message"] == (
        f"تنبيه: الطالب أحمد غائب في {day.isoformat()}."
    )


@pytest.mark.django_db
def test_preview_exposes_all_day_ids_across_pages_and_only_sendable_ids(role_client):
    manager, school, _ = role_client(["SCHOOL_MANAGER"])
    env = setup_attendance_env(school, students_count=51)
    day = env["local_now"].date()
    summaries = []
    for student in env["students"]:
        student.guardian_mobile = "+966500000001"
        student.save(update_fields=["guardian_mobile"])
        summaries.append(DailyAttendanceSummary(
            school=school, student=student, academic_year=env["year"],
            section=env["section"], attendance_date=day,
            expected_periods=1, submitted_periods=1, absent_periods=1,
            present_periods=0, excused_absent_periods=0,
            unexcused_absent_periods=1, completeness_status=DailyCompleteness.COMPLETE,
            absence_status=DailyAbsenceStatus.FULL, calculated_at=timezone.now(),
        ))
    DailyAttendanceSummary.objects.bulk_create(summaries)
    env["students"][-1].guardian_mobile = ""
    env["students"][-1].save(update_fields=["guardian_mobile"])

    first = manager.get(PREVIEW_URL, {"date": day.isoformat(), "page": 1}).json()
    second = manager.get(PREVIEW_URL, {"date": day.isoformat(), "page": 2}).json()
    assert first["total"] == second["total"] == 51
    assert len(first["students"]) == 50
    assert len(second["students"]) == 1
    assert first["candidate_student_ids"] == second["candidate_student_ids"]
    assert set(first["candidate_student_ids"]) == {item.id for item in env["students"]}
    assert first["ready_total"] == len(first["selectable_student_ids"]) == 50
    assert env["students"][-1].id not in first["selectable_student_ids"]
    expected_issue = [{
        "student_id": env["students"][-1].id,
        "full_name": env["students"][-1].full_name,
        "grade_name": env["grade"].name,
        "section_name": env["section"].name,
        "reason": "MISSING_RECIPIENT",
    }]
    assert first["contact_issues"] == second["contact_issues"] == expected_issue


@pytest.mark.django_db
def test_invalid_guardian_number_is_listed_and_cannot_be_sent(role_client):
    manager, school, _ = role_client(["SCHOOL_MANAGER"])
    student, _, day = _absence(school)
    assert _integration(manager).status_code == 200
    student.guardian_mobile = "0555000001"  # Legacy noncanonical value.
    student.save(update_fields=["guardian_mobile"])

    preview = manager.get(PREVIEW_URL, {"date": day.isoformat()}).json()
    assert preview["ready_total"] == 0
    assert preview["selectable_student_ids"] == []
    assert preview["contact_issues"][0]["student_id"] == student.id
    assert preview["contact_issues"][0]["reason"] == "INVALID_RECIPIENT"
    assert preview["students"][0]["eligibility_reason"] == "INVALID_RECIPIENT"

    with patch("school_sms.tasks.send_sms") as provider:
        response = manager.post(
            SEND_URL, {"date": day.isoformat(), "student_ids": [student.id]},
            content_type="application/json",
        )
    assert response.status_code == 400
    assert response.json()["code"] == "SMS_RECIPIENT_INVALID"
    provider.assert_not_called()
    assert not AbsenceSmsNotice.objects.filter(student=student).exists()


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
    summary.submitted_periods = 0
    summary.save(update_fields=["submitted_periods"])
    with patch("school_sms.tasks.send_sms") as provider:
        response = manager.post(
            SEND_URL,
            {"date": day.isoformat(), "student_ids": [student.id]},
            content_type="application/json",
        )
    assert response.status_code == 409
    provider.assert_not_called()
    summary.submitted_periods = 1
    summary.save(update_fields=["submitted_periods"])

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
def test_excused_absence_is_visible_but_cannot_be_sent(role_client):
    manager, school, _ = role_client(["SCHOOL_MANAGER"])
    student, _, day = _absence(school, unexcused=0)
    preview = manager.get(PREVIEW_URL, {"date": day.isoformat()}).json()
    assert preview["total"] == 1
    assert preview["ready_total"] == 0
    assert preview["students"][0]["eligibility_reason"] == "EXCUSED_ABSENCE"
    assert _integration(manager).status_code == 200
    assert manager.post(SEND_URL, {"date": day.isoformat(), "student_ids": [student.id]},
                        content_type="application/json").status_code == 409


@pytest.mark.django_db
def test_partial_absence_is_neither_listed_nor_sent(role_client):
    manager, school, _ = role_client(["SCHOOL_MANAGER"])
    student, summary, day = _absence(school, status=DailyAbsenceStatus.PARTIAL)
    summary.expected_periods = 2
    summary.submitted_periods = 2
    summary.present_periods = 1
    summary.save(update_fields=["expected_periods", "submitted_periods", "present_periods"])
    assert _integration(manager).status_code == 200
    preview = manager.get(PREVIEW_URL, {"date": day.isoformat()}).json()
    assert preview["total"] == preview["ready_total"] == 0
    assert preview["students"] == []
    assert "«اسم الطالب»" in preview["message_template"]
    with patch("school_sms.tasks.send_sms") as provider:
        response = manager.post(
            SEND_URL, {"date": day.isoformat(), "student_ids": [student.id]},
            content_type="application/json",
        )
    assert response.status_code == 409
    provider.assert_not_called()


@pytest.mark.django_db
def test_full_absence_in_sections_with_different_approved_periods_is_sendable(role_client):
    manager, school, _ = role_client(["SCHOOL_MANAGER"])
    student, summary, day = _absence(school)
    summary.expected_periods = 7
    summary.completeness_status = DailyCompleteness.INCOMPLETE
    summary.save(update_fields=["expected_periods", "completeness_status"])
    section = Section.objects.create(
        school=school, grade=summary.section.grade, code="2", name="2",
    )
    second_student = make_students(school, section, summary.academic_year, 1, prefix="10661")[0]
    second_student.guardian_mobile = "+966500000002"
    second_student.save(update_fields=["guardian_mobile"])
    DailyAttendanceSummary.objects.create(
        school=school, student=second_student, academic_year=summary.academic_year,
        section=section, attendance_date=day, expected_periods=7,
        submitted_periods=2, absent_periods=2, present_periods=0,
        excused_absent_periods=0, unexcused_absent_periods=2,
        completeness_status=DailyCompleteness.INCOMPLETE,
        absence_status=DailyAbsenceStatus.FULL, calculated_at=timezone.now(),
    )
    assert _integration(manager).status_code == 200
    # A stored school threshold may remain, but it no longer gates sending.
    assert manager.patch(
        "/api/v1/school/settings/", {"absence_sms_min_approved_periods": 7},
        content_type="application/json",
    ).status_code == 200

    preview = manager.get(PREVIEW_URL, {"date": day.isoformat()}).json()
    assert preview["total"] == preview["ready_total"] == 2
    assert set(preview["selectable_student_ids"]) == {student.id, second_student.id}
    assert {row["submitted_periods"] for row in preview["students"]} == {1, 2}
    assert all(row["eligibility_reason"] is None for row in preview["students"])
    with patch("school_sms.tasks.send_sms", return_value=SmsProviderResult()) as provider:
        sent = manager.post(
            SEND_URL,
            {"date": day.isoformat(), "student_ids": [student.id, second_student.id]},
            content_type="application/json",
        )
    assert sent.status_code == 202
    assert sent.json()["queued"] == 2
    assert provider.call_count == 2
    assert {call.kwargs["mobile"] for call in provider.call_args_list} == {
        student.guardian_mobile, second_student.guardian_mobile,
    }
    summary.submitted_periods = 2
    summary.absent_periods = 2
    summary.unexcused_absent_periods = 2
    summary.save(update_fields=["submitted_periods", "absent_periods", "unexcused_absent_periods"])
    with patch("school_sms.tasks.send_sms") as repeat_provider:
        repeated = manager.post(
            SEND_URL, {"date": day.isoformat(), "student_ids": [student.id]},
            content_type="application/json",
        )
    assert repeated.status_code == 202
    assert repeated.json()["skipped"] == 1
    repeat_provider.assert_not_called()


@pytest.mark.django_db
@pytest.mark.parametrize("change", ["excused", "later_present"])
def test_worker_rechecks_absence_before_calling_provider(role_client, change):
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
    if change == "excused":
        summary.unexcused_absent_periods = 0
        summary.save(update_fields=["unexcused_absent_periods"])
    else:
        summary.expected_periods = 7
        summary.submitted_periods = 2
        summary.present_periods = 1
        summary.absence_status = DailyAbsenceStatus.PARTIAL
        summary.save(update_fields=[
            "expected_periods", "submitted_periods", "present_periods", "absence_status",
        ])
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
        ("DREAMS", "Result: Success", ""),
        ("DREAMS", "Success", ""),
        ("DREAMS", "success", ""),
        ("DREAMS", "RESULT : SUCCESS", ""),
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


@pytest.mark.parametrize("response", ["Result: unexpected", "Success pending", "Not Success"])
def test_dreams_unrecognized_response_stays_uncertain(response):
    with patch("school_sms.providers._post", return_value=response):
        with pytest.raises(SmsProviderError) as error:
            send_sms(
                provider="DREAMS",
                username="user",
                secret="secret",
                sender="School",
                mobile="+966500000001",
                message="test",
            )
    assert error.value.code == "DREAMS_RESPONSE_UNKNOWN"
    assert error.value.ambiguous is True
