"""اختبارات م8.5 — الجسر والأجهزة والأحداث والوصول الصباحي (بلا بيانات بيومترية)."""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from academics.models import AcademicYear, AcademicYearStatus
from common.errors import ApiError
from devices.models import (
    AttendanceDevice,
    DeviceEvent,
    IdentityStatus,
    SchoolArrival,
    SchoolArrivalChange,
    StudentDeviceIdentity,
)
from devices.services.bridge import authenticate_bridge, create_bridge, rotate_bridge_credential
from devices.services.morning import compute_lateness
from schools.services.settings import get_or_create_settings
from students.models import Grade, Section
from tests.attendance_helpers import make_students

TZ = ZoneInfo("Asia/Riyadh")
# يوم أمس دائمًا — occurred_at لا يكون مستقبليًا مهما كانت ساعة تشغيل الاختبار
YESTERDAY = (datetime.now(TZ) - timedelta(days=1)).date()


def at(hour, minute, second=0, day=None):
    return datetime.combine(day or YESTERDAY, time(hour, minute, second), tzinfo=TZ)


@pytest.fixture
def env(make_school, make_user, make_membership):
    school = make_school()
    year = AcademicYear.objects.create(
        school=school, name="ع", start_date=date(2026, 8, 23),
        end_date=date(2027, 6, 25), status=AcademicYearStatus.ACTIVE,
    )
    grade = Grade.objects.create(school=school, name="الأول الثانوي", code="G1", sequence=1)
    section = Section.objects.create(school=school, grade=grade, code="1", name="1")
    students = make_students(school, section, year, 3, prefix="50100")
    settings_obj = get_or_create_settings(school=school)
    settings_obj.school_day_start_time = time(7, 0)
    settings_obj.morning_late_grace_minutes = 5
    settings_obj.save()

    bridge, token = create_bridge(school=school, name="جسر الاختبار", actor=None)
    device = AttendanceDevice.objects.create(school=school, name="بوابة رئيسية")
    return {
        "school": school, "year": year, "grade": grade, "section": section,
        "students": students, "settings": settings_obj,
        "bridge": bridge, "token": token, "device": device,
    }


def map_student(env, student, external_id="1001"):
    return StudentDeviceIdentity.objects.create(
        school=env["school"], device=env["device"], external_user_id=external_id,
        student=student, status=IdentityStatus.MATCHED,
    )


def post_batch(client, token, events, device=None):
    return client.post(
        "/api/v1/bridge/events/batch/",
        {"events": events},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )


def event(env, occurred, external_user_id="1001", external_event_id="", device_id=None):
    return {
        "device_id": device_id or env["device"].id,
        "external_event_id": external_event_id,
        "external_user_id": external_user_id,
        "occurred_at": occurred.isoformat(),
        "verification_method": "FINGERPRINT",
    }


# ---------- حساب التأخر (البنود 44-46، 118-119) ----------


@pytest.mark.django_db
def test_late_calculation_and_grace_boundary(env):
    s = env["settings"]

    def calc(h, m, sec=0):
        return compute_lateness(
            settings_obj=s, arrival_at=at(h, m, sec), attendance_date=YESTERDAY
        )

    late = calc(7, 18)
    assert late == {"raw_late_minutes": 18, "counted_late_minutes": 13, "status": "LATE"}
    # الحد الدقيق: 07:05:00 مع سماح 5 = في الوقت؛ 07:05:01 متأخر (raw=5, counted=0)
    assert calc(7, 5, 0)["status"] == "ON_TIME"
    assert calc(7, 5, 0)["counted_late_minutes"] == 0
    boundary = calc(7, 5, 1)
    assert boundary["status"] == "LATE"
    assert boundary["counted_late_minutes"] == 0  # متأخر أقل من دقيقة محتسبة
    assert calc(6, 50)["status"] == "ON_TIME"  # الوصول المبكر raw=0


# ---------- الاستقبال والتكرار (البنود 30-32، 39-40، 120-122) ----------


@pytest.mark.django_db
def test_ingest_creates_single_arrival_from_first_event(env, client):
    map_student(env, env["students"][0])
    response = post_batch(
        client, env["token"],
        [
            event(env, at(7, 12), external_event_id="e1"),
            event(env, at(7, 14), external_event_id="e2"),
            event(env, at(9, 0), external_event_id="e3"),
        ],
    )
    assert response.status_code == 200
    assert [r["result"] for r in response.json()["results"]] == ["accepted"] * 3
    assert DeviceEvent.objects.count() == 3  # الأحداث كلها تحفظ
    arrival = SchoolArrival.objects.get()  # وصول واحد فقط — لا 3 تأخرات
    assert arrival.first_arrival_at == at(7, 12)
    assert arrival.raw_late_minutes == 12
    assert arrival.counted_late_minutes == 7
    assert arrival.status == "LATE"
    assert arrival.source == "BIOMETRIC"


@pytest.mark.django_db
def test_duplicate_events_stored_once(env, client):
    map_student(env, env["students"][0])
    batch = [event(env, at(7, 12), external_event_id="dup-1")]
    post_batch(client, env["token"], batch)
    response = post_batch(client, env["token"], batch + batch)
    results = [r["result"] for r in response.json()["results"]]
    assert results == ["duplicate", "duplicate"]
    assert DeviceEvent.objects.count() == 1
    # وبلا معرف حدث خارجي: البصمة الحتمية تمنع التكرار أيضًا
    no_id = [event(env, at(7, 30))]
    post_batch(client, env["token"], no_id)
    response = post_batch(client, env["token"], no_id)
    assert response.json()["results"][0]["result"] == "duplicate"
    assert DeviceEvent.objects.count() == 2


@pytest.mark.django_db
def test_older_event_arriving_later_corrects_first_arrival(env, client):
    """‏Sync متأخر يجلب حدثًا أقدم → first_arrival يتصحح ويعاد حساب التأخر (121)."""
    map_student(env, env["students"][0])
    post_batch(client, env["token"], [event(env, at(7, 14), external_event_id="a")])
    arrival = SchoolArrival.objects.get()
    assert arrival.counted_late_minutes == 9

    post_batch(client, env["token"], [event(env, at(7, 8), external_event_id="b")])
    arrival.refresh_from_db()
    assert arrival.first_arrival_at == at(7, 8)
    assert arrival.raw_late_minutes == 8
    assert arrival.counted_late_minutes == 3
    assert SchoolArrival.objects.count() == 1


@pytest.mark.django_db
def test_unmatched_event_kept_then_reprocessed_after_mapping(env, client, role_client):
    """حدث غير مربوط لا يحذف؛ وبعد المطابقة يعاد معالجته فيظهر الوصول (123-124)."""
    response = post_batch(
        client, env["token"], [event(env, at(7, 20), external_user_id="9999")]
    )
    assert response.json()["results"][0]["result"] == "unmatched"
    row = DeviceEvent.objects.get()
    assert row.processing_status == "UNMATCHED"
    assert not SchoolArrival.objects.exists()
    identity = StudentDeviceIdentity.objects.get(external_user_id="9999")
    assert identity.status == IdentityStatus.UNMATCHED

    manager, _, _ = role_client(["SCHOOL_MANAGER"], school=env["school"])
    map_response = manager.post(
        f"/api/v1/device-identities/{identity.id}/map/",
        {"student_id": env["students"][1].id},
        content_type="application/json",
    )
    assert map_response.status_code == 200
    row.refresh_from_db()
    assert row.processing_status == "PROCESSED"
    arrival = SchoolArrival.objects.get(student=env["students"][1])
    assert arrival.counted_late_minutes == 15


@pytest.mark.django_db
def test_future_timestamp_rejected(env, client):
    map_student(env, env["students"][0])
    future = datetime.now(TZ) + timedelta(hours=2)
    response = post_batch(client, env["token"], [event(env, future)])
    body = response.json()["results"][0]
    assert body["result"] == "invalid" and body["reason"] == "future_timestamp"
    assert not DeviceEvent.objects.exists()


# ---------- مصادقة الجسر والعزل (البنود 88-92، 128-129) ----------


@pytest.mark.django_db
def test_bridge_credentials(env, client, make_school):
    # رمز تالف
    bad = post_batch(client, "brg_xxx_yyy", [])
    assert bad.status_code == 403
    # جهاز مدرسة أخرى عبر credential مدرسة A → invalid لا كتابة
    other = make_school("أخرى")
    foreign_device = AttendanceDevice.objects.create(school=other, name="أجنبي")
    response = post_batch(
        client, env["token"], [event(env, at(7, 10), device_id=foreign_device.id)]
    )
    assert response.json()["results"][0]["result"] == "invalid"
    assert not DeviceEvent.objects.exists()
    # التدوير: القديم يبطل والجديد يعمل
    old_token = env["token"]
    new_token = rotate_bridge_credential(installation=env["bridge"], actor=None)
    assert post_batch(client, old_token, []).status_code == 403
    assert post_batch(client, new_token, []).status_code == 200
    # الإيقاف يمنع
    env["bridge"].status = "DISABLED"
    env["bridge"].save(update_fields=["status"])
    assert post_batch(client, new_token, []).status_code == 403
    with pytest.raises(ApiError):
        authenticate_bridge(new_token)


# ---------- اليدوي والتصحيح (البنود 51-56، 125-126) ----------


@pytest.mark.django_db
def test_manual_arrival_and_duplicate_guard(env, role_client):
    vice, _, _ = role_client(["VICE_PRINCIPAL"], school=env["school"])
    payload = {
        "student_id": env["students"][0].id,
        "date": str(YESTERDAY),
        "arrival_time": "07:10",
        "reason": "دخل من البوابة الخلفية",
    }
    response = vice.post(
        "/api/v1/morning/arrivals/", payload, content_type="application/json"
    )
    assert response.status_code == 201
    body = response.json()
    assert body["source"] == "MANUAL"
    assert body["status"] == "LATE" and body["counted_late_minutes"] == 5
    duplicate = vice.post(
        "/api/v1/morning/arrivals/", payload, content_type="application/json"
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "ARRIVAL_ALREADY_EXISTS"


@pytest.mark.django_db
def test_correction_updates_current_and_keeps_history(env, client, role_client):
    map_student(env, env["students"][0])
    post_batch(client, env["token"], [event(env, at(7, 22), external_event_id="x")])
    arrival = SchoolArrival.objects.get()
    assert arrival.counted_late_minutes == 17

    vice, _, _ = role_client(["VICE_PRINCIPAL"], school=env["school"])
    response = vice.post(
        f"/api/v1/morning/arrivals/{arrival.id}/correct/",
        {"arrival_time": "07:05", "reason": "البصمة سجلت متأخرة"},
        content_type="application/json",
    )
    assert response.status_code == 200
    arrival.refresh_from_db()
    assert arrival.status == "ON_TIME" and arrival.counted_late_minutes == 0
    change = SchoolArrivalChange.objects.get()
    assert change.previous_counted_late_minutes == 17
    assert change.new_counted_late_minutes == 0
    assert change.previous_arrival_time == at(7, 22)


# ---------- التقارير (البنود 60-66، 105-109) ----------


@pytest.mark.django_db
def test_late_list_and_student_history(env, client, role_client):
    map_student(env, env["students"][0], "1001")
    map_student(env, env["students"][1], "1002")
    day_before = YESTERDAY - timedelta(days=1)
    post_batch(
        client, env["token"],
        [
            event(env, at(7, 16), "1001", "h1"),
            event(env, at(7, 3), "1002", "h2"),  # في الوقت
            event(env, at(7, 30, day=day_before), "1001", "h3"),
        ],
    )
    vice, _, _ = role_client(["VICE_PRINCIPAL"], school=env["school"])
    late = vice.get(f"/api/v1/morning/late/?date={YESTERDAY}").json()
    assert late["total_late"] == 1
    row = late["students"][0]
    assert row["full_name"] == env["students"][0].full_name
    assert row["counted_late_minutes"] == 11
    assert row["grade_name"] == "الأول الثانوي"  # الفصل من القيد التاريخي

    history = vice.get(
        f"/api/v1/morning/students/{env['students'][0].id}/history/"
        f"?from={day_before}&to={YESTERDAY}"
    ).json()
    assert history["late_count"] == 2
    assert history["total_late_minutes"] == 11 + 25
    assert len(history["entries"]) == 2

    too_long = vice.get(
        f"/api/v1/morning/students/{env['students'][0].id}/history/"
        f"?from=2020-01-01&to={YESTERDAY}"
    )
    assert too_long.status_code == 400

    summary = vice.get(f"/api/v1/morning/summary/?date={YESTERDAY}").json()
    assert summary["arrived_total"] == 2
    assert summary["on_time"] == 1 and summary["late"] == 1


# ---------- الأدوار والعزل (البنود 91-93، 127-128) ----------


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("roles", "devices_status", "morning_status"),
    [
        (["SCHOOL_MANAGER"], 200, 200),
        (["VICE_PRINCIPAL"], 403, 200),
        (["TEACHER"], 403, 403),
        (["COUNSELOR"], 403, 403),
    ],
)
def test_roles_matrix(role_client, roles, devices_status, morning_status):
    client, school, _ = role_client(roles)
    assert client.get("/api/v1/devices/").status_code == devices_status
    assert client.get("/api/v1/morning/summary/").status_code == morning_status


@pytest.mark.django_db
def test_tenant_isolation_foreign_ids(env, role_client):
    foreign, _, _ = role_client(["SCHOOL_MANAGER"])  # مدرسة أخرى
    identity = map_student(env, env["students"][0])
    arrival = SchoolArrival.objects.create(
        school=env["school"], student=env["students"][0], attendance_date=YESTERDAY,
        first_arrival_at=at(7, 30), raw_late_minutes=30, counted_late_minutes=25,
        status="LATE", source="MANUAL",
    )
    assert foreign.get("/api/v1/devices/").json() == []
    assert foreign.patch(
        f"/api/v1/devices/{env['device'].id}/", {}, content_type="application/json"
    ).status_code == 404
    assert foreign.post(
        f"/api/v1/device-identities/{identity.id}/map/",
        {"student_id": 1}, content_type="application/json",
    ).status_code == 404
    assert foreign.post(
        f"/api/v1/morning/arrivals/{arrival.id}/correct/",
        {"arrival_time": "07:00", "reason": "x"}, content_type="application/json",
    ).status_code == 404
    assert foreign.get(
        f"/api/v1/morning/students/{env['students'][0].id}/history/"
        f"?from={YESTERDAY}&to={YESTERDAY}"
    ).status_code == 404
    assert foreign.get(f"/api/v1/morning/late/?date={YESTERDAY}").json()["total_late"] == 0


# ---------- الأسرار (البنود 17-18) ----------


@pytest.mark.django_db
def test_device_secret_never_exposed_to_browser(env, client, role_client):
    manager, _, _ = role_client(["SCHOOL_MANAGER"], school=env["school"])
    created = manager.post(
        "/api/v1/devices/",
        {"name": "جهاز بسر", "local_ip": "192.168.1.50", "connection_secret": "comm-key-77"},
        content_type="application/json",
    )
    assert created.status_code == 201
    assert "comm-key-77" not in created.content.decode()
    listing = manager.get("/api/v1/devices/")
    assert "comm-key-77" not in listing.content.decode()
    # الجسر الموثق وحده يستلمه (يحتاجه للاتصال المحلي) — مشفر At-Rest في DB
    device = AttendanceDevice.objects.get(name="جهاز بسر")
    assert "comm-key-77" not in device.connection_secret_encrypted
    configs = client.get(
        "/api/v1/bridge/devices/", HTTP_AUTHORIZATION=f"Bearer {env['token']}"
    ).json()
    secret = next(c for c in configs if c["name"] == "جهاز بسر")["connection_secret"]
    assert secret == "comm-key-77"


# ---------- الحذف النهائي (البنود 94-95، 130) ----------


@pytest.mark.django_db
def test_purge_removes_student_owned_device_data(env, client, role_client):
    from students.services.purge import purge_student

    student = env["students"][0]
    map_student(env, student)
    post_batch(client, env["token"], [event(env, at(7, 22), external_event_id="p1")])
    arrival = SchoolArrival.objects.get()
    vice, _, _ = role_client(["VICE_PRINCIPAL"], school=env["school"])
    vice.post(
        f"/api/v1/morning/arrivals/{arrival.id}/correct/",
        {"arrival_time": "07:10", "reason": "تصحيح"},
        content_type="application/json",
    )
    student.status = "WITHDRAWN"
    student.save(update_fields=["status"])
    purge_student(student=student)

    assert not StudentDeviceIdentity.objects.filter(student_id=student.id).exists()
    assert not SchoolArrival.objects.filter(student_id=student.id).exists()
    assert not SchoolArrivalChange.objects.exists()
    assert not DeviceEvent.objects.filter(student_id=student.id).exists()
    assert AttendanceDevice.objects.filter(id=env["device"].id).exists()  # الجهاز يبقى


@pytest.mark.django_db
def test_unregistered_device_purge_fails_loudly(env, monkeypatch):
    from django.db.models import ProtectedError

    from students.services import purge as purge_service

    student = env["students"][0]
    map_student(env, student)
    student.status = "WITHDRAWN"
    student.save(update_fields=["status"])
    stripped = [
        step for step in purge_service.PURGE_STEPS
        if step[0] != "هويات أجهزة الطالب"
    ]
    monkeypatch.setattr(purge_service, "PURGE_STEPS", stripped)
    with pytest.raises(ProtectedError):
        purge_service.purge_student(student=student)


# ---------- تكامل ALL_ABSENT (البنود 72-74، 131) ----------


@pytest.mark.django_db
def test_all_absent_shows_arrival_indicator_without_changing_result(
    env, client, make_membership, make_user
):
    from academics.models import BellPeriod, BellSchedule, SchoolWeekDay
    from attendance.models import AttendanceMark, AttendanceSession
    from attendance.selectors.analytics import get_multi_period_report
    from attendance.services.periods import _PY_TO_SCHOOL_WEEKDAY, build_period_snapshot

    schedule = BellSchedule.objects.create(school=env["school"], name="ع")
    periods = [
        BellPeriod.objects.create(
            school=env["school"], bell_schedule=schedule, sequence=i,
            name=f"حصة {i}", start_time=time(6 + i, 0), end_time=time(6 + i, 45),
        )
        for i in (1, 2)
    ]
    SchoolWeekDay.objects.update_or_create(
        school=env["school"],
        weekday=_PY_TO_SCHOOL_WEEKDAY[YESTERDAY.weekday()],
        defaults={"is_school_day": True, "bell_schedule": schedule},
    )
    membership = make_membership(make_user("0550000900"), env["school"], ["TEACHER"])
    with_arrival, without_arrival = env["students"][0], env["students"][1]
    for period in periods:
        session = AttendanceSession.objects.create(
            school=env["school"], academic_year=env["year"], section=env["section"],
            attendance_date=YESTERDAY, period_sequence=period.sequence,
            bell_period_snapshot=build_period_snapshot(period, YESTERDAY, "Asia/Riyadh"),
            status="SUBMITTED", roster_fingerprint="fp",
            unprepared_alert_minutes_snapshot=25,
            started_by_membership=membership, submitted_by_membership=membership,
            submitted_at=at(8, 0),
        )
        for student in (with_arrival, without_arrival):
            AttendanceMark.objects.create(
                school=env["school"], session=session, student=student, status="ABSENT"
            )
    map_student(env, with_arrival)
    post_batch(client, env["token"], [event(env, at(7, 4), external_event_id="m1")])

    report = get_multi_period_report(
        school=env["school"], attendance_date=YESTERDAY,
        sequences=[1, 2], match="ALL_ABSENT",
    )
    rows = {s["student_id"]: s for s in report["students"]}
    # النتيجة لا تتغير بسبب البصمة — كلاهما يبقى ALL_ABSENT (يحتاج مراجعة فقط)
    assert set(rows) == {with_arrival.id, without_arrival.id}
    assert rows[with_arrival.id]["morning_arrival"] == "07:04"
    assert rows[without_arrival.id]["morning_arrival"] is None
