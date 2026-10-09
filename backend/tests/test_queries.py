"""حراسة عدد الاستعلامات — /me يجب ألا يتضخم مع تعدد المدارس (منع N+1)."""

import pytest


@pytest.mark.django_db
@pytest.mark.parametrize("school_count", [1, 4, 20])
@pytest.mark.parametrize("has_active_school", [False, True])
def test_me_query_count_constant_regardless_of_schools(
    make_user,
    make_school,
    make_membership,
    login_client,
    django_assert_max_num_queries,
    school_count,
    has_active_school,
):
    user = make_user("0550000400")
    schools = [make_school() for _ in range(school_count)]
    for school in schools:
        make_membership(user, school, ["TEACHER", "COUNSELOR"])
    client, _ = login_client("0550000400")
    # Login selects a sole school automatically. Compare like-for-like contexts
    # explicitly so that this test detects N+1 rather than the school-picker policy.
    session = client.session
    if has_active_school:
        session["active_school_id"] = schools[0].id
    else:
        session.pop("active_school_id", None)
    session.save()

    # Session/user, platform access, memberships/select_related and prefetches,
    # plus the one owned guardian-relation existence lookup for the parent space.
    # The count remains constant regardless of the number of schools.
    # An active school also costs the existing three membership-context queries.
    with django_assert_max_num_queries(11 if has_active_school else 8):
        response = client.get("/api/v1/auth/me/")
    assert response.status_code == 200
    assert len(response.json()["memberships"]) == school_count
