"""حراسة عدد الاستعلامات — /me يجب ألا يتضخم مع تعدد المدارس (منع N+1)."""

import pytest


@pytest.mark.django_db
def test_me_query_count_constant_regardless_of_schools(
    make_user, make_school, make_membership, login_client, django_assert_max_num_queries
):
    user = make_user("0550000400")
    for _ in range(4):  # 4 مدارس بأدوار متعددة
        make_membership(user, make_school(), ["TEACHER", "COUNSELOR"])
    client, _ = login_client("0550000400")

    # session + user + platform access + memberships/select_related + two prefetches.
    # The count remains constant regardless of the number of schools.
    with django_assert_max_num_queries(7):
        response = client.get("/api/v1/auth/me/")
    assert response.status_code == 200
    assert len(response.json()["memberships"]) == 4
