"""اختبارات Multi-Tenancy — أهم اختبارات المرحلة: العزل، الأدوار، التبديل، IDOR."""

import pytest
from django.db import IntegrityError, transaction

from memberships.middleware import ACTIVE_SCHOOL_SESSION_KEY
from memberships.models import MembershipStatus, SchoolMembership
from schools.models import SchoolStatus


def _switch(client, school_id):
    return client.post(
        "/api/v1/session/active-school/",
        {"school_id": school_id},
        content_type="application/json",
    )


# ---------- Multi-School User ----------


@pytest.mark.django_db
def test_one_user_two_schools_same_identity(make_user, make_school, make_membership):
    user = make_user("0550000300")
    a, b = make_school("مدرسة أ"), make_school("مدرسة ب")
    m1 = make_membership(user, a, ["TEACHER"])
    m2 = make_membership(user, b, ["TEACHER"])
    assert m1.user_id == m2.user_id == user.id
    assert user.memberships.count() == 2


@pytest.mark.django_db
def test_single_school_auto_selected_on_login(
    make_user, make_school, make_membership, login_client
):
    user = make_user("0550000301")
    school = make_school("الوحيدة")
    make_membership(user, school, ["TEACHER"])
    _, response = login_client("0550000301")
    body = response.json()
    assert body["active_school"]["id"] == school.id
    assert body["roles"] == ["TEACHER"]


@pytest.mark.django_db
def test_multi_school_requires_selection(make_user, make_school, make_membership, login_client):
    user = make_user("0550000302")
    make_membership(user, make_school(), ["TEACHER"])
    make_membership(user, make_school(), ["TEACHER"])
    _, response = login_client("0550000302")
    body = response.json()
    assert body["active_school"] is None
    assert len(body["memberships"]) == 2


@pytest.mark.django_db
def test_switch_school_persists_in_session(make_user, make_school, make_membership, login_client):
    user = make_user("0550000303")
    a, b = make_school("أ"), make_school("ب")
    make_membership(user, a, ["TEACHER"])
    make_membership(user, b, ["COUNSELOR"])
    client, _ = login_client("0550000303")

    response = _switch(client, a.id)
    assert response.status_code == 200
    assert response.json()["active_school"]["id"] == a.id
    # يبقى في الجلسة عبر الطلبات التالية
    me = client.get("/api/v1/auth/me/").json()
    assert me["active_school"]["id"] == a.id

    response = _switch(client, b.id)
    assert response.json()["active_school"]["id"] == b.id
    assert client.get("/api/v1/auth/me/").json()["roles"] == ["COUNSELOR"]


# ---------- Multi-Role & Role Scoping ----------


@pytest.mark.django_db
def test_roles_are_scoped_to_school(make_user, make_school, make_membership, login_client):
    """أدوار مدرسة B لا تظهر ولا تنطبق في مدرسة A — اختبار إلزامي."""
    user = make_user("0550000304")
    a, b = make_school("أ"), make_school("ب")
    make_membership(user, a, ["TEACHER"])
    make_membership(user, b, ["TEACHER", "COUNSELOR"])
    client, _ = login_client("0550000304")

    _switch(client, a.id)
    assert client.get("/api/v1/auth/me/").json()["roles"] == ["TEACHER"]

    _switch(client, b.id)
    assert sorted(client.get("/api/v1/auth/me/").json()["roles"]) == ["COUNSELOR", "TEACHER"]


@pytest.mark.django_db
def test_duplicate_membership_blocked_by_database(make_user, make_school, make_membership):
    """UNIQUE(user, school) في قاعدة البيانات — وليس Validation فقط."""
    user = make_user("0550000305")
    school = make_school()
    make_membership(user, school)
    with pytest.raises(IntegrityError), transaction.atomic():
        SchoolMembership.objects.create(user=user, school=school)


@pytest.mark.django_db
def test_duplicate_role_blocked_by_database(make_user, make_school, make_membership):
    from memberships.models import SchoolMembershipRole

    membership = make_membership(make_user("0550000306"), make_school(), ["TEACHER"])
    with pytest.raises(IntegrityError), transaction.atomic():
        SchoolMembershipRole.objects.create(membership=membership, role="TEACHER")


# ---------- Tenant Isolation / IDOR ----------


@pytest.mark.django_db
def test_cannot_select_school_without_membership(
    make_user, make_school, make_membership, login_client
):
    """IDOR الأساسي: تمرير school_id لمدرسة أجنبية يرفض ولا يكشف وجودها."""
    attacker = make_user("0550000307")
    make_membership(attacker, make_school("مدرسته"), ["TEACHER"])
    foreign = make_school("مدرسة أجنبية")

    client, _ = login_client("0550000307")
    response = _switch(client, foreign.id)
    assert response.status_code == 403
    assert response.json()["code"] == "INVALID_SCHOOL_MEMBERSHIP"
    # لم تتغير المدرسة النشطة
    assert client.get("/api/v1/auth/me/").json()["active_school"]["name"] == "مدرسته"


@pytest.mark.django_db
def test_nonexistent_school_id_same_error_as_foreign(
    make_user, make_membership, make_school, login_client
):
    """لا فرق بين مدرسة غير موجودة ومدرسة ليست له — لا معلومات تسرب."""
    user = make_user("0550000308")
    make_membership(user, make_school(), ["TEACHER"])
    client, _ = login_client("0550000308")
    foreign = make_school("أجنبية")
    r_foreign = _switch(client, foreign.id)
    r_missing = _switch(client, 999999)
    assert r_foreign.status_code == r_missing.status_code == 403
    assert r_foreign.json()["code"] == r_missing.json()["code"]


@pytest.mark.django_db
def test_my_schools_returns_only_own_memberships(
    make_user, make_school, make_membership, login_client
):
    me_user = make_user("0550000309")
    other = make_user("0550000310")
    mine = make_school("لي")
    theirs = make_school("لغيري")
    make_membership(me_user, mine, ["TEACHER"])
    make_membership(other, theirs, ["TEACHER"])

    client, _ = login_client("0550000309")
    body = client.get("/api/v1/auth/schools/").json()
    school_names = [m["school"]["name"] for m in body["memberships"]]
    assert school_names == ["لي"]


# ---------- Suspended / Stale states ----------


@pytest.mark.django_db
def test_suspended_membership_cannot_switch(make_user, make_school, make_membership, login_client):
    user = make_user("0550000311")
    school = make_school()
    make_membership(user, school, ["TEACHER"], status=MembershipStatus.SUSPENDED)
    make_membership(user, make_school(), ["TEACHER"])  # الثانية حتى لا يختار تلقائيًا
    client, _ = login_client("0550000311")
    response = _switch(client, school.id)
    assert response.status_code == 403
    assert response.json()["code"] == "MEMBERSHIP_SUSPENDED"


@pytest.mark.django_db
def test_left_membership_treated_as_no_membership(
    make_user, make_school, make_membership, login_client
):
    user = make_user("0550000312")
    school = make_school()
    make_membership(user, school, ["TEACHER"], status=MembershipStatus.LEFT)
    make_membership(user, make_school(), ["TEACHER"])
    client, _ = login_client("0550000312")
    response = _switch(client, school.id)
    assert response.json()["code"] == "INVALID_SCHOOL_MEMBERSHIP"


@pytest.mark.django_db
def test_suspended_school_blocked(make_user, make_school, make_membership, login_client):
    user = make_user("0550000313")
    school = make_school("موقوفة", status=SchoolStatus.SUSPENDED)
    make_membership(user, school, ["TEACHER"])
    make_membership(user, make_school(), ["TEACHER"])
    client, _ = login_client("0550000313")
    response = _switch(client, school.id)
    assert response.status_code == 403
    assert response.json()["code"] == "SCHOOL_SUSPENDED"


@pytest.mark.django_db
def test_stale_session_cleared_when_membership_suspended(
    make_user, make_school, make_membership, login_client
):
    """الجلسة القديمة ليست مصدر ثقة: إيقاف العضوية يسقط السياق في الطلب التالي."""
    user = make_user("0550000314")
    school = make_school()
    membership = make_membership(user, school, ["TEACHER"])
    client, response = login_client("0550000314")
    assert response.json()["active_school"]["id"] == school.id  # اختيرت تلقائيًا

    membership.status = MembershipStatus.SUSPENDED
    membership.save(update_fields=["status"])

    me = client.get("/api/v1/auth/me/").json()
    assert me["active_school"] is None
    assert me["roles"] == []
    # المفتاح أزيل من الجلسة فعلاً
    assert ACTIVE_SCHOOL_SESSION_KEY not in client.session


@pytest.mark.django_db
def test_stale_session_when_school_suspended(make_user, make_school, make_membership, login_client):
    user = make_user("0550000315")
    school = make_school()
    make_membership(user, school, ["TEACHER"])
    client, _ = login_client("0550000315")

    school.status = SchoolStatus.SUSPENDED
    school.save(update_fields=["status"])

    me = client.get("/api/v1/auth/me/").json()
    assert me["active_school"] is None


@pytest.mark.django_db
def test_switching_school_never_grants_foreign_roles(
    make_user, make_school, make_membership, login_client
):
    """Invariant: تبديل المدرسة لا يمنح صلاحيات جديدة خارج عضوية المدرسة الهدف."""
    user = make_user("0550000316")
    a = make_school("أ")
    b = make_school("ب")
    make_membership(user, a, ["SCHOOL_MANAGER"])
    make_membership(user, b, ["TEACHER"])
    client, _ = login_client("0550000316")

    _switch(client, b.id)
    roles_in_b = client.get("/api/v1/auth/me/").json()["roles"]
    assert "SCHOOL_MANAGER" not in roles_in_b
