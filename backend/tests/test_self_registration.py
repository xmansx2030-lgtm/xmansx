"""التسجيل الذاتي العام: باقات آمنة وإنشاء ذري وجلسة مدير جاهزة."""

import pytest
from django.test import Client, override_settings

from accounts.models import User
from audit.models import AuditAction, AuditLog
from memberships.models import SchoolMembership, SchoolRole
from schools.models import School
from subscriptions.models import (
    EntitlementKey,
    PlanEntitlement,
    SaaSPlan,
    SchoolSubscription,
    SubscriptionStatus,
)

PASSWORD = "Safe-School-2026!"


def make_plan(*, code="starter", public=True, active=True, trial_days=21, staff_limit=20):
    plan = SaaSPlan.objects.create(
        code=code,
        name_ar="باقة البداية",
        description="باقة تشغيل المدرسة",
        is_public=public,
        is_active=active,
        price_amount="990.00",
        trial_days_default=trial_days,
    )
    PlanEntitlement.objects.create(
        plan=plan,
        key=EntitlementKey.MAX_STAFF,
        numeric_value=staff_limit,
    )
    return plan


def payload(plan, *, mobile="0551234567"):
    return {
        "school_name": "ثانوية الإتقان التجريبية",
        "school_type": "GIRLS",
        "manager_name": "ريم القحطاني",
        "manager_mobile": mobile,
        "password": PASSWORD,
        "confirm_password": PASSWORD,
        "plan_id": plan.id,
        "terms_accepted": True,
    }


@pytest.mark.django_db
def test_public_plans_returns_only_active_public_trial_plans(client):
    visible = make_plan()
    make_plan(code="private", public=False)
    make_plan(code="inactive", active=False)
    make_plan(code="no-trial", trial_days=0)

    response = client.get("/api/v1/auth/registration/plans/")

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": visible.id,
            "name": "باقة البداية",
            "description": "باقة تشغيل المدرسة",
            "billing_period": "ANNUAL",
            "price_amount": "990.00",
            "currency": "SAR",
            "trial_days": 21,
            "entitlements": {"MAX_STAFF": 20},
        }
    ]


@pytest.mark.django_db
def test_self_registration_creates_school_manager_trial_and_session(client):
    plan = make_plan()

    response = client.post(
        "/api/v1/auth/register-school/",
        payload(plan),
        content_type="application/json",
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "ريم القحطاني"
    assert body["mobile"] == "+966551234567"
    assert body["roles"] == [SchoolRole.SCHOOL_MANAGER]
    assert body["must_change_password"] is False
    assert body["active_school"]["name"] == "ثانوية الإتقان التجريبية"

    user = User.objects.get(mobile="+966551234567")
    school = School.objects.get(name="ثانوية الإتقان التجريبية")
    membership = SchoolMembership.objects.get(user=user, school=school)
    assert user.check_password(PASSWORD)
    assert membership.role_codes() == [SchoolRole.SCHOOL_MANAGER]
    subscription = SchoolSubscription.objects.get(school=school)
    assert subscription.status == SubscriptionStatus.TRIAL
    assert subscription.plan == plan
    assert client.get("/api/v1/auth/me/").status_code == 200

    event = AuditLog.objects.get(action=AuditAction.PLATFORM_SCHOOL_CREATED)
    assert event.metadata["source"] == "self_registration"
    assert "password" not in str(event.metadata).lower()
    assert PASSWORD not in str(event.metadata)


@pytest.mark.django_db
def test_self_registration_requires_csrf():
    plan = make_plan()
    strict_client = Client(enforce_csrf_checks=True)

    rejected = strict_client.post(
        "/api/v1/auth/register-school/",
        payload(plan),
        content_type="application/json",
    )
    assert rejected.status_code == 403
    assert School.objects.count() == 0

    strict_client.get("/api/v1/auth/csrf/")
    token = strict_client.cookies["csrftoken"].value
    accepted = strict_client.post(
        "/api/v1/auth/register-school/",
        payload(plan),
        content_type="application/json",
        headers={"X-CSRFToken": token},
    )
    assert accepted.status_code == 201


@pytest.mark.django_db
def test_self_registration_rejects_private_plan_without_creating_tenant(client):
    plan = make_plan(public=False)

    response = client.post(
        "/api/v1/auth/register-school/",
        payload(plan),
        content_type="application/json",
    )

    assert response.status_code == 409
    assert response.json()["code"] == "REGISTRATION_PLAN_UNAVAILABLE"
    assert School.objects.count() == 0
    assert User.objects.count() == 0


@pytest.mark.django_db
def test_self_registration_never_attaches_school_to_existing_account(client, make_user):
    plan = make_plan()
    existing = make_user("0551234567")

    response = client.post(
        "/api/v1/auth/register-school/",
        payload(plan),
        content_type="application/json",
    )

    assert response.status_code == 409
    assert response.json()["code"] == "SELF_REGISTRATION_CONFLICT"
    assert User.objects.get() == existing
    assert School.objects.count() == 0
    assert SchoolMembership.objects.count() == 0


@pytest.mark.django_db
def test_self_registration_rolls_back_everything_when_plan_has_no_manager_capacity(client):
    plan = make_plan(staff_limit=0)

    response = client.post(
        "/api/v1/auth/register-school/",
        payload(plan),
        content_type="application/json",
    )

    assert response.status_code == 409
    assert response.json()["code"] == "STAFF_LIMIT_EXCEEDED"
    assert School.objects.count() == 0
    assert User.objects.count() == 0
    assert SchoolMembership.objects.count() == 0
    assert SchoolSubscription.objects.count() == 0


@pytest.mark.django_db
def test_self_registration_validates_password_confirmation(client):
    plan = make_plan()
    data = payload(plan)
    data["confirm_password"] = "Different-Password-2026!"

    response = client.post("/api/v1/auth/register-school/", data, content_type="application/json")

    assert response.status_code == 400
    assert "confirm_password" in response.json()["details"]
    assert School.objects.count() == 0


@pytest.mark.django_db
@override_settings(
    SELF_REGISTRATION_RATE_LIMIT_IP=(1, 3600),
    SELF_REGISTRATION_RATE_LIMIT_MOBILE=(10, 3600),
)
def test_self_registration_rate_limits_repeated_attempts(client):
    private_plan = make_plan(public=False)
    first = client.post(
        "/api/v1/auth/register-school/",
        payload(private_plan),
        content_type="application/json",
    )
    second = client.post(
        "/api/v1/auth/register-school/",
        payload(private_plan),
        content_type="application/json",
    )

    assert first.status_code == 409
    assert second.status_code == 429
    assert second.json()["code"] == "SELF_REGISTRATION_RATE_LIMITED"


@pytest.mark.django_db
@override_settings(SELF_REGISTRATION_ENABLED=False)
def test_self_registration_can_be_disabled_operationally(client):
    plan = make_plan()

    response = client.post(
        "/api/v1/auth/register-school/",
        payload(plan),
        content_type="application/json",
    )

    assert response.status_code == 503
    assert response.json()["code"] == "SELF_REGISTRATION_UNAVAILABLE"
    assert School.objects.count() == 0
