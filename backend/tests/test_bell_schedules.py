"""اختبارات جداول الحصص وأيام الأسبوع: التداخل، التسلسل، العزل، الربط."""

import pytest

SCHEDULES_URL = "/api/v1/school/bell-schedules/"
WEEK_DAYS_URL = "/api/v1/school/week-days/"


def _period(seq, name, start, end, attendance=True):
    return {
        "sequence": seq, "name": name, "start_time": start, "end_time": end,
        "is_attendance_period": attendance,
    }


def _create_schedule(client, name="الجدول العادي"):
    return client.post(SCHEDULES_URL, {"name": name}, content_type="application/json")


def _put_periods(client, schedule_id, periods):
    return client.put(
        f"{SCHEDULES_URL}{schedule_id}/periods/",
        {"periods": periods},
        content_type="application/json",
    )


@pytest.mark.django_db
def test_create_schedule_with_valid_periods(role_client):
    client, _, _ = role_client(["SCHOOL_MANAGER"])
    schedule = _create_schedule(client).json()
    response = _put_periods(
        client,
        schedule["id"],
        [
            _period(1, "الحصة الأولى", "07:00", "07:45"),
            _period(2, "الحصة الثانية", "07:45", "08:30"),
            _period(3, "الفسحة", "08:30", "08:50", attendance=False),
            _period(4, "الحصة الثالثة", "08:50", "09:35"),
        ],
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["periods"]) == 4
    assert body["periods"][2]["is_attendance_period"] is False


@pytest.mark.django_db
def test_period_edit_refreshes_pristine_today_context_and_dashboard_cache(
    role_client, django_capture_on_commit_callbacks
):
    """تعديل التوقيت يصل فورًا لقراءات اليوم ما دام التحضير لم يبدأ."""
    from attendance.services.day_context import get_or_create_attendance_day_context
    from attendance.services.periods import _PY_TO_SCHOOL_WEEKDAY, school_now
    from school_dashboard.cache import build_key

    client, school, _ = role_client(["SCHOOL_MANAGER"])
    schedule = _create_schedule(client).json()
    _put_periods(
        client, schedule["id"], [_period(1, "الحصة الأولى", "07:00", "07:45")]
    )
    today = school_now(school).date()
    weekday = _PY_TO_SCHOOL_WEEKDAY[today.weekday()]
    client.put(
        WEEK_DAYS_URL,
        {
            "days": [
                {
                    "weekday": weekday,
                    "is_school_day": True,
                    "bell_schedule_id": schedule["id"],
                }
            ]
        },
        content_type="application/json",
    )
    context = get_or_create_attendance_day_context(
        school=school, attendance_date=today
    )
    assert context.attendance_periods[0]["start_time"] == "07:00"
    old_dashboard_key = build_key(
        school_id=school.id, section="today", parts={"roles": ["SCHOOL_MANAGER"]}
    )

    with django_capture_on_commit_callbacks(execute=True):
        response = _put_periods(
            client,
            schedule["id"],
            [_period(1, "الحصة الأولى", "08:10", "08:55")],
        )

    assert response.status_code == 200
    context.refresh_from_db()
    assert context.attendance_periods[0]["start_time"] == "08:10"
    assert context.attendance_periods[0]["end_time"] == "08:55"
    assert build_key(
        school_id=school.id, section="today", parts={"roles": ["SCHOOL_MANAGER"]}
    ) != old_dashboard_key


@pytest.mark.django_db
def test_period_end_before_start_rejected(role_client):
    client, _, _ = role_client(["SCHOOL_MANAGER"])
    schedule = _create_schedule(client).json()
    response = _put_periods(client, schedule["id"], [_period(1, "مقلوبة", "08:00", "07:00")])
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_BELL_PERIOD_TIME"


@pytest.mark.django_db
def test_period_overlap_rejected(role_client):
    client, _, _ = role_client(["SCHOOL_MANAGER"])
    schedule = _create_schedule(client).json()
    response = _put_periods(
        client,
        schedule["id"],
        [
            _period(1, "الأولى", "07:00", "07:45"),
            _period(2, "متداخلة", "07:30", "08:15"),
        ],
    )
    assert response.status_code == 400
    assert response.json()["code"] == "BELL_PERIOD_OVERLAP"


@pytest.mark.django_db
def test_duplicate_sequence_rejected(role_client):
    client, _, _ = role_client(["SCHOOL_MANAGER"])
    schedule = _create_schedule(client).json()
    response = _put_periods(
        client,
        schedule["id"],
        [
            _period(1, "الأولى", "07:00", "07:45"),
            _period(1, "مكررة", "07:45", "08:30"),
        ],
    )
    assert response.status_code == 400
    assert response.json()["code"] == "DUPLICATE_PERIOD_SEQUENCE"


@pytest.mark.django_db
def test_cross_school_schedule_access_rejected(role_client):
    """IDOR: جدول مدرسة أخرى — تعديل/حصص/أرشفة كلها 404."""
    manager_a, _, _ = role_client(["SCHOOL_MANAGER"])
    manager_b, _, _ = role_client(["SCHOOL_MANAGER"])
    foreign = _create_schedule(manager_b).json()

    assert manager_a.patch(
        f"{SCHEDULES_URL}{foreign['id']}/", {"name": "اختراق"},
        content_type="application/json",
    ).status_code == 404
    assert _put_periods(
        manager_a, foreign["id"], [_period(1, "x", "07:00", "07:45")]
    ).status_code == 404
    assert manager_a.post(f"{SCHEDULES_URL}{foreign['id']}/archive/").status_code == 404


@pytest.mark.django_db
def test_week_days_bootstrap_defaults(role_client):
    client, _, _ = role_client(["SCHOOL_MANAGER"])
    body = client.get(WEEK_DAYS_URL).json()
    assert len(body["days"]) == 7
    by_day = {d["weekday"]: d["is_school_day"] for d in body["days"]}
    assert by_day[0] and by_day[4]      # الأحد والخميس دراسة
    assert not by_day[5] and not by_day[6]  # الجمعة والسبت لا


@pytest.mark.django_db
def test_same_schedule_serves_multiple_weekdays(role_client):
    client, _, _ = role_client(["SCHOOL_MANAGER"])
    schedule = _create_schedule(client).json()
    response = client.put(
        WEEK_DAYS_URL,
        {"days": [
            {"weekday": d, "is_school_day": True, "bell_schedule_id": schedule["id"]}
            for d in range(5)
        ]},
        content_type="application/json",
    )
    assert response.status_code == 200
    days = response.json()["days"]
    assert all(d["bell_schedule_id"] == schedule["id"] for d in days if d["weekday"] < 5)


@pytest.mark.django_db
def test_foreign_schedule_cannot_attach_to_weekday(role_client):
    """جدول مدرسة B لا يربط بيوم مدرسة A — cross-school FK (البند 56)."""
    manager_a, _, _ = role_client(["SCHOOL_MANAGER"])
    manager_b, _, _ = role_client(["SCHOOL_MANAGER"])
    foreign = _create_schedule(manager_b).json()

    response = manager_a.put(
        WEEK_DAYS_URL,
        {"days": [{"weekday": 0, "is_school_day": True, "bell_schedule_id": foreign["id"]}]},
        content_type="application/json",
    )
    assert response.status_code == 400
    # ولم يرتبط شيء
    days = manager_a.get(WEEK_DAYS_URL).json()["days"]
    assert days[0]["bell_schedule_id"] is None


@pytest.mark.django_db
def test_archive_schedule_detaches_from_weekdays(role_client):
    client, _, _ = role_client(["SCHOOL_MANAGER"])
    schedule = _create_schedule(client).json()
    client.put(
        WEEK_DAYS_URL,
        {"days": [{"weekday": 0, "is_school_day": True, "bell_schedule_id": schedule["id"]}]},
        content_type="application/json",
    )
    assert client.post(f"{SCHEDULES_URL}{schedule['id']}/archive/").status_code == 200
    days = client.get(WEEK_DAYS_URL).json()["days"]
    assert days[0]["bell_schedule_id"] is None
    # الجدول المؤرشف لا يظهر في القائمة
    assert all(s["id"] != schedule["id"] for s in client.get(SCHEDULES_URL).json())


@pytest.mark.django_db
def test_teacher_denied_schedules(role_client):
    client, _, _ = role_client(["TEACHER"])
    assert client.get(SCHEDULES_URL).status_code == 403
    assert _create_schedule(client).status_code == 403
    assert client.get(WEEK_DAYS_URL).status_code == 403
