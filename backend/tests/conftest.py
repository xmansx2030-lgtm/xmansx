import pytest

from accounts.models import User
from memberships.models import MembershipStatus, SchoolMembership, SchoolMembershipRole
from schools.models import School, SchoolStatus

PASSWORD = "Str0ng-Pass-2026"


@pytest.fixture(autouse=True)
def _isolated_cache():
    """عدادات rate limit تعيش في Redis (db الاختبارات) — تنظف قبل كل اختبار
    حتى لا تتراكم محاولات الدخول من نفس IP عبر الاختبارات."""
    from django.core.cache import cache, caches

    cache.clear()
    caches["security"].clear()
    yield


@pytest.fixture
def make_user(db):
    def _make(mobile: str, **kwargs) -> User:
        return User.objects.create_user(mobile=mobile, password=PASSWORD, **kwargs)

    return _make


@pytest.fixture
def make_school(db):
    counter = iter(range(1, 100))

    def _make(name: str = "", status: str = SchoolStatus.ACTIVE) -> School:
        n = next(counter)
        return School.objects.create(
            name=name or f"مدرسة {n}", slug=f"school-{n}", status=status
        )

    return _make


@pytest.fixture
def make_membership(db):
    def _make(
        user: User,
        school: School,
        roles: list[str] | None = None,
        status: str = MembershipStatus.ACTIVE,
    ) -> SchoolMembership:
        membership = SchoolMembership.objects.create(user=user, school=school, status=status)
        for role in roles or []:
            SchoolMembershipRole.objects.create(membership=membership, role=role)
        return membership

    return _make


@pytest.fixture
def role_client(make_user, make_school, make_membership):
    """عميل مسجل الدخول بأدوار محددة في مدرسة (تُنشأ إن لم تمرر) — مدرسة واحدة = اختيار تلقائي."""
    from django.test import Client

    counter = iter(range(100, 200))

    def _make(roles: list[str], school=None):
        school = school or make_school()
        mobile = f"0550009{next(counter):03d}"
        user = make_user(mobile)
        make_membership(user, school, roles)
        client = Client()
        response = client.post(
            "/api/v1/auth/login/",
            {"mobile": mobile, "password": PASSWORD},
            content_type="application/json",
        )
        assert response.status_code == 200
        return client, school, user

    return _make


@pytest.fixture
def login_client(client):
    """عميل مسجل الدخول بجوال معين."""

    def _login(mobile: str, password: str = PASSWORD):
        response = client.post(
            "/api/v1/auth/login/",
            {"mobile": mobile, "password": password},
            content_type="application/json",
        )
        return client, response

    return _login
