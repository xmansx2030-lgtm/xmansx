"""Real registration/account journeys, restricted live facts and negative authority."""

from datetime import timedelta
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import pytest
from django.test import Client
from django.utils import timezone

from accounts.models import User
from attendance.models import AttendanceMark, AttendanceSession, DailyAttendanceSummary
from audit.models import AuditLog
from common.security.identifiers import decrypt_national_id
from devices.models import SchoolArrival
from memberships.models import SchoolMembership
from parents.models import GuardianActivation, GuardianRegistrationRequest, GuardianStudentRelation
from school_sms.models import SchoolSmsIntegration
from school_sms.providers import SmsProviderError, SmsProviderResult
from school_sms.security import encrypt_secret
from tests.attendance_helpers import setup_attendance_env

pytestmark = pytest.mark.django_db
PASSWORD = "Safe-Parent-Pass-2026!"


def post(client, url, data):
    return client.post(url, data, content_type="application/json")


@pytest.fixture
def portal_env(role_client, make_school):
    school = make_school("مدرسة بوابة الأسرة")
    staff, _, actor = role_client(["SCHOOL_MANAGER"], school)
    env = setup_attendance_env(school, students_count=2)
    student = env["students"][0]
    student.guardian_mobile = "+966551900003"
    student.save(update_fields=["guardian_mobile"])
    student.refresh_from_db()
    response = staff.patch(
        "/api/v1/staff/parents/settings/", {"enabled": True}, content_type="application/json"
    )
    assert response.status_code == 200, response.content
    token = response.json()["registration_url"].rstrip("/").split("/")[-1]
    env.update(
        school=school,
        staff=staff,
        actor=actor,
        student=student,
        url=f"/api/v1/parent/registration/{token}/",
        parent=Client(),
    )
    return env


def register(env, *, mobile=None, identifier=None):
    response = post(
        env["parent"],
        env["url"],
        {
            "name": "ولي أمر موثق",
            "mobile": mobile or env["student"].guardian_mobile,
            "student_identifier": identifier
            or decrypt_national_id(env["student"].national_id_encrypted),
            "relationship_type": "أب",
        },
    )
    assert response.status_code == 202, response.content
    return GuardianRegistrationRequest.objects.order_by("-id").first(), response.json()


def approve(env, item, *, delivery="MANUAL", contact_bound=True):
    response = post(
        env["staff"],
        f"/api/v1/staff/parents/registrations/{item.id}/decision/",
        {
            "decision": "APPROVE",
            "student_id": env["student"].id,
            "verification_note": "تم التحقق حضورياً من الهوية وصلة القرابة والرقم",
            "contact_bound": contact_bound,
            "delivery": delivery,
        },
    )
    assert response.status_code == 200, response.content
    return response.json()


def activate(env):
    item, receipt = register(env)
    decision = approve(env, item)
    token = parse_qs(urlsplit(decision["activation_url"]).fragment)["token"][0]
    response = post(
        env["parent"],
        "/api/v1/parent/activation/",
        {
            "token": token,
            "new_password": PASSWORD,
            "confirm_password": PASSWORD,
        },
    )
    assert response.status_code == 200, response.content
    return GuardianStudentRelation.objects.get(student=env["student"]), token, receipt


def make_session(env, *, status="SUBMITTED", sequence=3, absent=True):
    membership = SchoolMembership.objects.get(user=env["actor"], school=env["school"])
    session = AttendanceSession.objects.create(
        school=env["school"],
        academic_year=env["year"],
        section=env["section"],
        attendance_date=env["local_now"].date(),
        bell_period=env["period"],
        period_sequence=sequence,
        bell_period_snapshot={
            "sequence": sequence,
            "name": "الحصة الفعلية",
            "start_time": "00:00",
            "end_time": "23:59",
        },
        status=status,
        roster_fingerprint="fixture",
        unprepared_alert_minutes_snapshot=25,
        started_by_membership=membership,
        submitted_by_membership=membership if status == "SUBMITTED" else None,
        submitted_at=timezone.now() if status == "SUBMITTED" else None,
    )
    if absent:
        AttendanceMark.objects.create(
            school=env["school"], session=session, student=env["student"], status="ABSENT"
        )
    return session


def test_registration_does_not_create_account_or_reveal_match_and_supports_arabic(portal_env):
    env = portal_env
    initial_count = User.objects.count()
    item, receipt = register(env, mobile="٠٥٥١٩٠٠٠٠٣")
    assert User.objects.count() == initial_count
    assert item.student_id is None
    assert item.mobile_encrypted != env["student"].guardian_mobile
    assert "national_id" not in str(receipt)
    assert env["student"].full_name not in str(receipt)
    _, unmatched = register(env, mobile="0551900004", identifier="P1234567")
    assert receipt["message"] == unmatched["message"]
    assert set(receipt) == set(unmatched)
    assert not SchoolMembership.objects.filter(user__mobile="+966551900003").exists()


def test_duplicate_registration_public_response_is_generic(portal_env):
    env = portal_env
    _, first = register(env)
    _, second = register(env)
    assert first["message"] == second["message"]
    assert GuardianRegistrationRequest.objects.count() == 1


def test_full_journey_secure_receipt_activation_and_replay(portal_env):
    env = portal_env
    relation, token, receipt = activate(env)
    assert relation.status == "ACTIVE"
    assert relation.user.check_password(PASSWORD)
    assert not SchoolMembership.objects.filter(user=relation.user).exists()
    assert env["parent"].get("/api/v1/auth/me/").json()["has_parent_portal"]
    assert (
        post(env["parent"], "/api/v1/parent/registration/status/", receipt).json()["status"]
        == "ACTIVATED"
    )
    replay = post(env["parent"], "/api/v1/parent/activation/", {"token": token})
    assert replay.status_code == 409
    assert GuardianStudentRelation.objects.count() == 1
    assert not AuditLog.objects.filter(metadata__icontains=token).exists()


@pytest.mark.parametrize("state", ["expired", "revoked", "used", "contact_changed"])
def test_invalid_activation_cannot_create_account(portal_env, state):
    env = portal_env
    item, _ = register(env)
    result = approve(env, item)
    token = parse_qs(urlsplit(result["activation_url"]).fragment)["token"][0]
    activation = GuardianActivation.objects.get(request=item)
    if state == "expired":
        activation.expires_at = timezone.now() - timedelta(seconds=1)
        activation.save()
    elif state in {"revoked", "used"}:
        setattr(activation, f"{state}_at", timezone.now())
        activation.save()
    else:
        type(env["student"]).objects.filter(pk=env["student"].pk).update(
            guardian_mobile="+966551900004"
        )
    initial_count = User.objects.count()
    response = post(
        env["parent"],
        "/api/v1/parent/activation/",
        {
            "token": token,
            "new_password": PASSWORD,
            "confirm_password": PASSWORD,
        },
    )
    assert response.status_code == 409
    assert User.objects.count() == initial_count
    assert not GuardianStudentRelation.objects.exists()


def test_inspection_never_consumes_token_and_reissue_invalidates_old(portal_env):
    env = portal_env
    item, _ = register(env)
    result = approve(env, item)
    old = parse_qs(urlsplit(result["activation_url"]).fragment)["token"][0]
    assert env["parent"].get("/api/v1/parent/activation/").status_code == 405
    assert (
        post(env["parent"], "/api/v1/parent/activation/check/", {"token": old}).status_code == 200
    )
    assert GuardianActivation.objects.get(request=item).used_at is None
    replacement = post(
        env["staff"],
        f"/api/v1/staff/parents/registrations/{item.id}/activation/",
        {
            "delivery": "MANUAL",
            "verification_note": "تم التحقق مجدداً من الهوية حضورياً",
        },
    )
    assert replacement.status_code == 200
    assert (
        post(env["parent"], "/api/v1/parent/activation/check/", {"token": old}).status_code == 409
    )


def test_existing_employee_account_requires_owner_authentication_and_keeps_password(
    portal_env, role_client
):
    env = portal_env
    employee, _, user = role_client(["TEACHER"], env["school"])
    old_hash = user.password
    env["student"].guardian_mobile = user.mobile
    env["student"].save(update_fields=["guardian_mobile"])
    item, _ = register(env, mobile=user.mobile)
    result = approve(env, item)
    token = parse_qs(urlsplit(result["activation_url"]).fragment)["token"][0]
    denied = post(
        env["parent"],
        "/api/v1/parent/activation/",
        {
            "token": token,
            "new_password": PASSWORD,
            "confirm_password": PASSWORD,
        },
    )
    assert denied.status_code == 403
    assert post(employee, "/api/v1/parent/activation/", {"token": token}).status_code == 200
    user.refresh_from_db()
    assert user.password == old_hash
    assert User.objects.filter(mobile=user.mobile).count() == 1
    assert SchoolMembership.objects.get(user=user).role_codes() == ["TEACHER"]


def test_one_account_multiple_schools_and_revocation_is_local(portal_env, role_client, make_school):
    env = portal_env
    first, _, _ = activate(env)
    other_school = make_school("مدرسة ثانية")
    staff, _, actor = role_client(["SCHOOL_MANAGER"], other_school)
    other = setup_attendance_env(other_school, students_count=1)
    student = other["students"][0]
    student.guardian_mobile = first.user.mobile
    student.save(update_fields=["guardian_mobile"])
    config = staff.patch(
        "/api/v1/staff/parents/settings/", {"enabled": True}, content_type="application/json"
    ).json()
    second_env = {
        **other,
        "school": other_school,
        "staff": staff,
        "actor": actor,
        "student": student,
        "parent": env["parent"],
        "url": "/api/v1/parent/registration/" + config["registration_url"].split("/")[-1] + "/",
    }
    item, _ = register(second_env)
    result = approve(second_env, item)
    token = parse_qs(urlsplit(result["activation_url"]).fragment)["token"][0]
    assert post(env["parent"], "/api/v1/parent/activation/", {"token": token}).status_code == 200
    children = env["parent"].get("/api/v1/parent/children/").json()["results"]
    assert len(children) == 2
    assert {c["school"]["id"] for c in children} == {env["school"].id, other_school.id}
    assert (
        post(
            env["staff"],
            f"/api/v1/staff/parents/relations/{first.id}/decision/",
            {
                "status": "REVOKED",
                "reason": "انتهت الصفة الموثقة",
            },
        ).status_code
        == 200
    )
    assert env["parent"].get(f"/api/v1/parent/children/{first.id}/").status_code == 404
    second = GuardianStudentRelation.objects.get(student=student)
    assert env["parent"].get(f"/api/v1/parent/children/{second.id}/").status_code == 200
    assert env["staff"].get(f"/api/v1/staff/parents/registrations/{item.id}/").status_code == 404


@pytest.mark.parametrize(
    "state,absent,expected",
    [
        ("SUBMITTED", True, "ABSENT"),
        ("SUBMITTED", False, "PRESENT"),
        ("IN_PROGRESS", True, "IN_PROGRESS"),
    ],
)
def test_live_attendance_only_confirms_submitted_facts(portal_env, state, absent, expected):
    env = portal_env
    relation, _, _ = activate(env)
    make_session(env, status=state, absent=absent)
    result = env["parent"].get(f"/api/v1/parent/children/{relation.id}/").json()
    assert result["periods"][0]["status"] == expected
    assert result["today"]["absent_periods"] == (1 if expected == "ABSENT" else 0)
    assert result["morning"]["status"] == "NOT_RECORDED"
    assert "guardian_mobile" not in str(result)
    assert "national_id" not in str(result)


def test_future_period_and_incomplete_full_history_are_explained(portal_env):
    env = portal_env
    relation, _, _ = activate(env)
    tomorrow = env["local_now"].date() + timedelta(days=1)
    from attendance.models import AttendanceDayContext

    AttendanceDayContext.objects.create(
        school=env["school"],
        attendance_date=tomorrow,
        timezone_snapshot="Asia/Riyadh",
        schedule_snapshot={
            "periods": [
                {"sequence": 1, "name": "الحصة الأولى", "start_time": "07:00", "end_time": "07:45"}
            ]
        },
    )
    assert (
        env["parent"]
        .get(f"/api/v1/parent/children/{relation.id}/?date={tomorrow}")
        .json()["periods"][0]["status"]
        == "NOT_STARTED"
    )
    DailyAttendanceSummary.objects.create(
        school=env["school"],
        student=env["student"],
        academic_year=env["year"],
        section=env["section"],
        attendance_date=env["local_now"].date(),
        expected_periods=7,
        submitted_periods=1,
        present_periods=0,
        absent_periods=1,
        unexcused_absent_periods=1,
        absence_status="FULL",
        completeness_status="INCOMPLETE",
        calculated_at=timezone.now(),
    )
    history = env["parent"].get(f"/api/v1/parent/children/{relation.id}/history/").json()
    assert history["summary"]["full_absence_days"] == 0
    assert history["results"][0]["completeness_status"] == "INCOMPLETE"
    assert "غير مكتمل" in history["results"][0]["absence_status_label"]


def test_morning_uses_counted_minutes_only(portal_env):
    env = portal_env
    relation, _, _ = activate(env)
    SchoolArrival.objects.create(
        school=env["school"],
        student=env["student"],
        attendance_date=env["local_now"].date(),
        first_arrival_at=timezone.now(),
        raw_late_minutes=15,
        counted_late_minutes=10,
        status="LATE",
        source="MANUAL",
    )
    response = env["parent"].get(f"/api/v1/parent/children/{relation.id}/").json()
    assert response["morning"]["counted_late_minutes"] == 10
    assert response["today"]["absent_periods"] == 0


@pytest.mark.parametrize(
    "outcome,status",
    [
        (SmsProviderResult(reference="mock"), "SENT"),
        (SmsProviderError("MOCK_FAILED"), "FAILED"),
        (SmsProviderError("MOCK_UNKNOWN", ambiguous=True), "UNKNOWN"),
    ],
)
def test_activation_reuses_mocked_provider_without_absence_sms(portal_env, outcome, status):
    env = portal_env
    SchoolSmsIntegration.objects.create(
        school=env["school"],
        provider="DREAMS",
        username="mock-school",
        sender_name="School",
        secret_encrypted=encrypt_secret("test-secret"),
        is_active=True,
    )
    item, _ = register(env)
    kwargs = (
        {"side_effect": outcome} if isinstance(outcome, Exception) else {"return_value": outcome}
    )
    with patch("school_sms.providers.send_sms", **kwargs) as mock:
        result = approve(env, item, delivery="SMS")
    assert result["delivery_status"] == status
    assert mock.call_count == 1
    assert "activation_url" not in result
    from school_sms.models import AbsenceSmsNotice

    assert not AbsenceSmsNotice.objects.exists()


def test_registration_rate_limit_and_csrf_are_enforced(portal_env, settings):
    env = portal_env
    settings.PARENT_REGISTRATION_IP_LIMIT = 1
    register(env)
    assert post(env["parent"], env["url"], {}).status_code == 429
    assert (
        post(
            Client(enforce_csrf_checks=True),
            "/api/v1/parent/activation/",
            {
                "token": "x" * 43,
            },
        ).status_code
        == 403
    )


def test_parent_history_bounded_and_foreign_relation_indistinguishable(portal_env, make_user):
    env = portal_env
    relation, _, _ = activate(env)
    stranger = Client()
    stranger.force_login(make_user("0551900088"))
    assert stranger.get(f"/api/v1/parent/children/{relation.id}/").status_code == 404
    assert stranger.get("/api/v1/parent/children/9999999/").status_code == 404
    assert (
        env["parent"]
        .get(
            f"/api/v1/parent/children/{relation.id}/history/?from_date=2024-01-01&to_date=2026-10-08"
        )
        .status_code
        == 400
    )


def test_equivalent_imported_mobile_format_allows_verified_approval_without_rewriting_contact(
    portal_env,
):
    env = portal_env
    type(env["student"]).objects.filter(pk=env["student"].pk).update(guardian_mobile="0551900003")
    env["student"].refresh_from_db()
    relation, _, _ = activate(env)
    assert relation.status == "ACTIVE"
    env["student"].refresh_from_db()
    assert env["student"].guardian_mobile == "0551900003"


def test_self_password_change_rotates_current_session_and_invalidates_other_sessions(portal_env):
    env = portal_env
    relation, _, _ = activate(env)
    other = Client()
    other.force_login(relation.user)
    old_key = env["parent"].session.session_key
    response = post(
        env["parent"],
        "/api/v1/parent/account/password/",
        {
            "current_password": PASSWORD,
            "new_password": "Another-Safe-Parent-Pass-2026!",
            "confirm_password": "Another-Safe-Parent-Pass-2026!",
        },
    )
    assert response.status_code == 200, response.content
    relation.user.refresh_from_db()
    assert relation.user.check_password("Another-Safe-Parent-Pass-2026!")
    assert env["parent"].session.session_key != old_key
    assert env["parent"].get("/api/v1/parent/children/").status_code == 200
    assert other.get("/api/v1/parent/children/").status_code == 403
    assert AuditLog.objects.filter(action="PARENT_PASSWORD_CHANGED", actor=relation.user).exists()


@pytest.mark.parametrize(
    "current,new,confirm",
    [
        ("Wrong-Password!", "Another-Safe-Parent-Pass-2026!", "Another-Safe-Parent-Pass-2026!"),
        (PASSWORD, "Another-Safe-Parent-Pass-2026!", "Different-Password!"),
        (PASSWORD, "123", "123"),
    ],
)
def test_self_password_change_rejects_invalid_credentials_and_weak_or_mismatched_passwords(
    portal_env, current, new, confirm
):
    env = portal_env
    relation, _, _ = activate(env)
    old_hash = relation.user.password
    response = post(
        env["parent"],
        "/api/v1/parent/account/password/",
        {
            "current_password": current,
            "new_password": new,
            "confirm_password": confirm,
        },
    )
    assert response.status_code == 400
    relation.user.refresh_from_db()
    assert relation.user.password == old_hash


def test_history_keeps_unsubmitted_days_and_missing_summary_facts_without_guessing_complete(
    portal_env,
):
    from attendance.models import AttendanceDayContext

    env = portal_env
    relation, _, _ = activate(env)
    submitted = make_session(env)
    submitted.attendance_date = env["local_now"].date() - timedelta(days=1)
    submitted.save(update_fields=["attendance_date"])
    draft = make_session(env, status="IN_PROGRESS", sequence=4)
    AttendanceDayContext.objects.create(
        school=env["school"],
        attendance_date=draft.attendance_date,
        timezone_snapshot="Asia/Riyadh",
        schedule_snapshot={
            "periods": [
                {"sequence": 4, "name": "حصة مسودة", "is_attendance_period": True},
            ]
        },
    )
    history = env["parent"].get(f"/api/v1/parent/children/{relation.id}/history/").json()
    by_date = {r["date"]: r for r in history["results"]}
    assert by_date[draft.attendance_date.isoformat()]["absence_status"] == "UNDETERMINED"
    assert by_date[draft.attendance_date.isoformat()]["submitted_periods"] == 0
    assert by_date[submitted.attendance_date.isoformat()]["absent_periods"] == 1
    assert by_date[submitted.attendance_date.isoformat()]["completeness_status"] == "INCOMPLETE"
    assert history["summary"]["full_absence_days"] == 0
    detail = (
        env["parent"]
        .get(f"/api/v1/parent/children/{relation.id}/?date={submitted.attendance_date}")
        .json()
    )
    assert detail["today"]["completeness_status"] == "INCOMPLETE"
    assert detail["periods"][0]["status"] == "ABSENT"


def test_historical_detail_uses_saved_expected_count_without_context(portal_env):
    env = portal_env
    relation, _, _ = activate(env)
    session = make_session(env)
    day = env["local_now"].date() - timedelta(days=1)
    session.attendance_date = day
    session.save(update_fields=["attendance_date"])
    DailyAttendanceSummary.objects.create(
        school=env["school"],
        student=env["student"],
        academic_year=env["year"],
        section=env["section"],
        attendance_date=day,
        expected_periods=7,
        submitted_periods=1,
        present_periods=0,
        absent_periods=1,
        unexcused_absent_periods=1,
        absence_status="FULL",
        completeness_status="INCOMPLETE",
        calculated_at=timezone.now(),
    )
    detail = env["parent"].get(f"/api/v1/parent/children/{relation.id}/?date={day}").json()
    assert detail["today"]["expected_periods"] == 7
    assert detail["today"]["completeness_status"] == "INCOMPLETE"


def test_rate_limit_expiry_race_counts_the_competing_request():
    from unittest.mock import Mock

    from common.errors import ApiError
    from parents.rate_limit import consume

    cache = Mock()
    cache.add.return_value = False
    cache.incr.side_effect = [ValueError("expired"), 2]
    with patch("parents.rate_limit.caches", {"security": cache}), pytest.raises(ApiError) as error:
        consume(kind="test-expiry", value="opaque-value", limit=1)
    assert error.value.status_code == 429


def test_rate_limit_fails_closed_on_counter_failure():
    from unittest.mock import Mock

    from common.errors import ApiError
    from parents.rate_limit import consume

    cache = Mock()
    cache.add.side_effect = ConnectionError("unavailable")
    with patch("parents.rate_limit.caches", {"security": cache}), pytest.raises(ApiError) as error:
        consume(kind="test-failure", value="opaque-value", limit=1)
    assert error.value.status_code == 503


def test_child_cards_show_owned_notification_and_action_counts_without_private_contents(portal_env):
    from parents.models import ParentNotification

    env = portal_env
    relation, _, _ = activate(env)
    ParentNotification.objects.create(
        school=relation.school,
        relation=relation,
        user=relation.user,
        kind="EXCUSE",
        dedup_key="test:needed-info",
        title="استكمال مطلوب",
        body="نص خاص لا يعرض في بطاقة الأبناء",
        requires_action=True,
    )
    rows = env["parent"].get("/api/v1/parent/children/").json()["results"]
    assert rows[0]["new_notifications"] == 1
    assert rows[0]["required_actions"] == 1
    assert "نص خاص" not in str(rows)
    type(env["student"]).objects.filter(pk=env["student"].pk).update(
        guardian_mobile="+966551900009"
    )
    hidden = env["parent"].get("/api/v1/parent/children/").json()["results"][0]
    assert hidden["student"] is None
    assert hidden["new_notifications"] == hidden["required_actions"] == 0
