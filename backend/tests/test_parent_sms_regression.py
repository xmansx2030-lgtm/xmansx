"""Parent access never becomes absence SMS eligibility; explicit recipient proof is narrow."""

from unittest.mock import patch

import pytest
from django.utils import timezone

from attendance.models import DailyAbsenceStatus, DailyAttendanceSummary, DailyCompleteness
from parents.models import GuardianStudentRelation, RecipientContactBlock
from parents.security import contact_hash
from school_sms.models import AbsenceSmsNotice, AbsenceSmsStatus
from school_sms.providers import SmsProviderResult
from school_sms.security import recipient_hash
from school_sms.tasks import send_absence_notice
from tests.attendance_helpers import make_students
from tests.test_school_sms import PREVIEW_URL, SEND_URL, _absence, _integration


@pytest.mark.django_db
@pytest.mark.parametrize("provider", ["DREAMS", "MSEGAT"])
def test_absence_sms_continues_without_parent_account_or_relation(role_client, provider):
    client, school, _ = role_client(["SCHOOL_MANAGER"])
    student, _, day = _absence(school, completeness=DailyCompleteness.INCOMPLETE)
    assert GuardianStudentRelation.objects.filter(student=student).count() == 0
    assert _integration(client, provider=provider).status_code == 200
    with patch("school_sms.tasks.send_sms", return_value=SmsProviderResult()) as send:
        response = client.post(
            SEND_URL,
            {"date": day.isoformat(), "student_ids": [student.id]},
            content_type="application/json",
        )
    assert response.status_code == 202
    assert response.json()["queued"] == 1
    assert send.call_args.kwargs["mobile"] == student.guardian_mobile


@pytest.mark.django_db
def test_suspended_parent_relation_does_not_block_sms_to_school_contact(role_client, make_user):
    client, school, approver = role_client(["SCHOOL_MANAGER"])
    student, _, day = _absence(school)
    student.refresh_from_db()
    parent = make_user("0550099999")
    relation = GuardianStudentRelation.objects.create(
        school=school,
        student=student,
        user=parent,
        status="ACTIVE",
        approved_by=approver,
        approved_at=timezone.now(),
        contact_revision=student.guardian_contact_revision,
    )
    student.guardian_mobile = "+966500000003"
    student.save(update_fields=["guardian_mobile"])
    relation.refresh_from_db()
    assert relation.status == "SUSPENDED_CONTACT_REVIEW"
    assert _integration(client).status_code == 200
    with patch("school_sms.tasks.send_sms", return_value=SmsProviderResult()) as send:
        response = client.post(
            SEND_URL,
            {"date": day.isoformat(), "student_ids": [student.id]},
            content_type="application/json",
        )
    assert response.status_code == 202
    assert response.json()["queued"] == 1
    assert send.call_args.kwargs["mobile"] == "+966500000003"


@pytest.mark.django_db
def test_proven_bad_student_number_is_skipped_while_other_students_still_send(role_client):
    client, school, approver = role_client(["SCHOOL_MANAGER"])
    student, summary, day = _absence(school)
    second = make_students(school, summary.section, summary.academic_year, 1, prefix="10661")[0]
    second.guardian_mobile = student.guardian_mobile
    second.save(update_fields=["guardian_mobile"])
    DailyAttendanceSummary.objects.create(
        school=school,
        student=second,
        academic_year=summary.academic_year,
        section=summary.section,
        attendance_date=day,
        expected_periods=7,
        submitted_periods=1,
        absent_periods=1,
        present_periods=0,
        unexcused_absent_periods=1,
        excused_absent_periods=0,
        completeness_status=DailyCompleteness.INCOMPLETE,
        absence_status=DailyAbsenceStatus.FULL,
        calculated_at=timezone.now(),
    )
    RecipientContactBlock.objects.create(
        school=school,
        student=student,
        mobile_hash=contact_hash(student.guardian_mobile),
        reason="ثبت أن صاحب الرقم ليس مخولاً لهذا الطالب",
        verification_note="تحقق حضوري موثق",
        created_by=approver,
    )
    assert _integration(client).status_code == 200
    preview = client.get(PREVIEW_URL, {"date": day.isoformat()}).json()
    assert preview["total"] == 2
    assert preview["selectable_student_ids"] == [second.id]
    with patch("school_sms.tasks.send_sms", return_value=SmsProviderResult()) as send:
        response = client.post(
            SEND_URL,
            {"date": day.isoformat(), "student_ids": [student.id, second.id]},
            content_type="application/json",
        )
    assert response.status_code == 202
    assert response.json()["blocked"] == response.json()["queued"] == 1
    send.assert_called_once()
    assert not AbsenceSmsNotice.objects.filter(student=student).exists()


@pytest.mark.django_db
def test_worker_rechecks_explicit_recipient_block_before_provider(role_client):
    client, school, approver = role_client(["SCHOOL_MANAGER"])
    student, summary, day = _absence(school)
    assert _integration(client).status_code == 200
    notice = AbsenceSmsNotice.objects.create(
        school=school,
        student=student,
        attendance_date=day,
        absence_status=summary.absence_status,
        provider="DREAMS",
        recipient_masked="+9665****0001",
        recipient_hash=recipient_hash(student.guardian_mobile),
        requested_by=approver,
    )
    RecipientContactBlock.objects.create(
        school=school,
        student=student,
        mobile_hash=contact_hash(student.guardian_mobile),
        reason="ثبت عدم أحقيته",
        verification_note="تحقق حضوري موثق",
        created_by=approver,
    )
    with patch("school_sms.tasks.send_sms") as send:
        assert send_absence_notice(notice.id) == "failed"
    send.assert_not_called()
    notice.refresh_from_db()
    assert notice.status == AbsenceSmsStatus.FAILED
    assert notice.failure_code == "PRE_SEND_STATE_CHANGED"
