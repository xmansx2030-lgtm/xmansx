"""اختبارات تدفق التحضير: البدء، الاعتماد، الاستثناء فقط، التأخر، التعديل، العزل، Purge."""

from datetime import time, timedelta

import pytest
from django.utils import timezone as dj_timezone

from attendance.models import (
    AttendanceChange,
    AttendanceMark,
    AttendanceSession,
)
from tests.attendance_helpers import setup_attendance_env

START_URL = "/api/v1/attendance/sessions/start/"


def _start(client, section_id):
    return client.post(
        START_URL, {"section_id": section_id}, content_type="application/json"
    )


def _submit(client, session_id, marks):
    return client.post(
        f"/api/v1/attendance/sessions/{session_id}/submit/",
        {"marks": marks},
        content_type="application/json",
    )


def _edit(client, session_id, marks, reason=""):
    return client.patch(
        f"/api/v1/attendance/sessions/{session_id}/",
        {"marks": marks, "reason": reason},
        content_type="application/json",
    )


@pytest.fixture
def teacher_env(role_client):
    client, school, user = role_client(["TEACHER"])
    env = setup_attendance_env(school)
    env.update({"client": client, "school": school, "user": user})
    return env


@pytest.mark.django_db
def test_start_creates_in_progress_with_snapshot(teacher_env):
    response = _start(teacher_env["client"], teacher_env["section"].id)
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "IN_PROGRESS"
    assert body["period"]["sequence"] == 3
    assert len(body["roster"]) == 5
    session = AttendanceSession.objects.get(id=body["id"])
    snapshot = session.bell_period_snapshot
    assert snapshot["name"] == "الحصة الثالثة"
    assert snapshot["timezone"] == "Asia/Riyadh"
    assert session.period_sequence == 3
    assert session.started_by_membership.user_id == teacher_env["user"].id


@pytest.mark.django_db
def test_no_current_period_error(role_client):
    """بلا جدول لليوم → لا حصة حالية."""
    client, school, _ = role_client(["TEACHER"])
    env = setup_attendance_env(school)
    from academics.models import SchoolWeekDay

    SchoolWeekDay.objects.filter(school=school).update(is_school_day=False)
    response = _start(client, env["section"].id)
    assert response.status_code == 409
    assert response.json()["code"] == "NO_CURRENT_ATTENDANCE_PERIOD"


@pytest.mark.django_db
def test_duplicate_session_single_row(teacher_env, role_client):
    """معلمان لنفس (الفصل/التاريخ/الحصة) → جلسة واحدة (قيد DB) والثاني يستأنف."""
    first = _start(teacher_env["client"], teacher_env["section"].id)
    assert first.status_code == 201
    other_teacher, _, _ = role_client(["TEACHER"], school=teacher_env["school"])
    second = _start(other_teacher, teacher_env["section"].id)
    assert second.status_code == 200  # استئناف — لا إنشاء
    assert first.json()["id"] == second.json()["id"]
    assert AttendanceSession.objects.filter(school=teacher_env["school"]).count() == 1


@pytest.mark.django_db
def test_submit_exception_only_storage(teacher_env):
    """30 طالبًا: غائبان ومتأخر → 3 Marks فقط والبقية حاضرون استنتاجًا."""
    from tests.attendance_helpers import make_students

    make_students(
        teacher_env["school"], teacher_env["section"], teacher_env["year"],
        25, prefix="10770",
    )
    students = teacher_env["students"]
    session = _start(teacher_env["client"], teacher_env["section"].id).json()
    assert len(session["roster"]) == 30

    from datetime import date as date_cls
    from datetime import datetime, timedelta

    # +17 دقيقة بعد البداية (الجمع الفعلي — replace(minute) هش حسب ساعة التشغيل)
    arrival = (
        datetime.combine(date_cls(2026, 1, 1), teacher_env["period"].start_time)
        + timedelta(minutes=17)
    ).time()
    response = _submit(
        teacher_env["client"], session["id"],
        [
            {"student_id": students[0].id, "status": "ABSENT"},
            {"student_id": students[1].id, "status": "ABSENT"},
            {"student_id": students[2].id, "status": "LATE",
             "arrival_time": arrival.strftime("%H:%M")},
        ],
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "SUBMITTED"
    assert len(body["marks"]) == 3  # لا سجلات للحاضرين الـ 27
    assert AttendanceMark.objects.filter(session_id=session["id"]).count() == 3


@pytest.mark.django_db
def test_no_session_means_nothing(teacher_env):
    """غياب الجلسة لا يعني حضورًا: لا جلسات ولا علامات — ولا API يستنتج حضورًا."""
    assert AttendanceSession.objects.count() == 0
    assert AttendanceMark.objects.count() == 0
    # الاستنتاج «حاضر» مشروط بجلسة SUBMITTED فقط — لا endpoint يعيد حالة حضور
    # لفصل بلا جلسة (سيبنى التحليل في المرحلة 8 على هذا الثابت)


@pytest.mark.django_db
def test_late_minutes_server_calculated_ignores_client(teacher_env):
    """البداية بالـ snapshot + 17 دقيقة — أي late_minutes من العميل يتجاهل."""
    students = teacher_env["students"]
    session = _start(teacher_env["client"], teacher_env["section"].id).json()
    start_str = session["period"]["start_time"]
    hour, minute = map(int, start_str.split(":"))
    arrival = time(hour, minute + 17) if minute + 17 < 60 else time(hour + 1, minute + 17 - 60)

    response = _submit(
        teacher_env["client"], session["id"],
        [{"student_id": students[0].id, "status": "LATE",
          "arrival_time": arrival.strftime("%H:%M"), "late_minutes": 1}],  # قيمة خبيثة
    )
    assert response.status_code == 200
    mark = AttendanceMark.objects.get(session_id=session["id"])
    assert mark.late_minutes == 17


@pytest.mark.django_db
def test_arrival_before_start_rejected(teacher_env):
    students = teacher_env["students"]
    session = _start(teacher_env["client"], teacher_env["section"].id).json()
    start_str = session["period"]["start_time"]
    hour, minute = map(int, start_str.split(":"))
    early = time(hour - 1 if hour > 0 else 0, minute)
    response = _submit(
        teacher_env["client"], session["id"],
        [{"student_id": students[0].id, "status": "LATE",
          "arrival_time": early.strftime("%H:%M")}],
    )
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_ARRIVAL_TIME"


@pytest.mark.django_db
def test_snapshot_immune_to_schedule_change(teacher_env):
    """تعديل الجدول بعد الاعتماد لا يغير snapshot ولا دقائق التأخر (البند 59)."""
    students = teacher_env["students"]
    session_body = _start(teacher_env["client"], teacher_env["section"].id).json()
    original_start = session_body["period"]["start_time"]
    hour, minute = map(int, original_start.split(":"))
    arrival = time(hour, minute + 10) if minute + 10 < 60 else time(hour + 1, (minute + 10) % 60)
    _submit(
        teacher_env["client"], session_body["id"],
        [{"student_id": students[0].id, "status": "LATE",
          "arrival_time": arrival.strftime("%H:%M")}],
    )

    # المدرسة تعدل وقت الحصة لاحقًا (بداية ونهاية صالحتين)
    period = teacher_env["period"]
    period.start_time = time(9, 0)
    period.end_time = time(9, 45)
    period.save(update_fields=["start_time", "end_time"])

    session = AttendanceSession.objects.get(id=session_body["id"])
    assert session.bell_period_snapshot["start_time"] == original_start  # لم يتغير
    assert AttendanceMark.objects.get(session=session).late_minutes == 10


@pytest.mark.django_db
def test_submit_already_submitted_conflict(teacher_env):
    """double-click الاعتماد آمن — والرسالة تحمل اسم المعتمد ووقته."""
    students = teacher_env["students"]
    session = _start(teacher_env["client"], teacher_env["section"].id).json()
    assert _submit(teacher_env["client"], session["id"], []).status_code == 200
    second = _submit(
        teacher_env["client"], session["id"],
        [{"student_id": students[0].id, "status": "ABSENT"}],
    )
    assert second.status_code == 409
    body = second.json()
    assert body["code"] == "ATTENDANCE_SESSION_ALREADY_SUBMITTED"
    assert body["details"]["submitted_at"] is not None
    assert AttendanceMark.objects.filter(session_id=session["id"]).count() == 0  # لم تتضاعف


@pytest.mark.django_db
def test_start_after_submitted_returns_view(teacher_env, role_client):
    """فتح جلسة مرسلة يعرضها (المرسل/الوقت) بلا صف جديد — ومعلم آخر لا يمكنه التعديل."""
    session = _start(teacher_env["client"], teacher_env["section"].id).json()
    _submit(teacher_env["client"], session["id"], [])
    other, _, _ = role_client(["TEACHER"], school=teacher_env["school"])
    response = _start(other, teacher_env["section"].id)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "SUBMITTED"
    assert body["submitted_by"] is not None
    assert body["submitted_at"] is not None
    assert body["can_edit"] is False  # ليست جلسته — التعديل للمرسل أو الإدارة
    assert AttendanceSession.objects.count() == 1


@pytest.mark.django_db
def test_roster_excludes_non_active_students(teacher_env):
    """المتحول/المنسحب لا يظهر في الـ roster."""
    from students.services.lifecycle import set_student_status

    leaver = teacher_env["students"][0]
    set_student_status(
        student=leaver, new_status="TRANSFERRED", actor=teacher_env["user"]
    )
    session = _start(teacher_env["client"], teacher_env["section"].id).json()
    roster_ids = [r["student_id"] for r in session["roster"]]
    assert leaver.id not in roster_ids
    assert len(roster_ids) == 4


@pytest.mark.django_db
def test_roster_changed_between_start_and_submit(teacher_env):
    """طالب انتقل بعد البدء → ATTENDANCE_ROSTER_CHANGED ولا يسجل له غياب."""
    from students.services.lifecycle import set_student_status

    students = teacher_env["students"]
    session = _start(teacher_env["client"], teacher_env["section"].id).json()

    set_student_status(
        student=students[0], new_status="TRANSFERRED", actor=teacher_env["user"]
    )
    response = _submit(
        teacher_env["client"], session["id"],
        [{"student_id": students[1].id, "status": "ABSENT"}],
    )
    assert response.status_code == 409
    assert response.json()["code"] == "ATTENDANCE_ROSTER_CHANGED"

    # بعد التحديث: الاعتماد يمر، ومحاولة تعليم المنتقل ترفض
    retry = _submit(
        teacher_env["client"], session["id"],
        [{"student_id": students[0].id, "status": "ABSENT"}],
    )
    assert retry.json()["code"] == "INVALID_ATTENDANCE_STUDENT"
    final = _submit(
        teacher_env["client"], session["id"],
        [{"student_id": students[1].id, "status": "ABSENT"}],
    )
    assert final.status_code == 200


# ---------- التعديل ----------


@pytest.mark.django_db
def test_teacher_edit_within_window_and_history(teacher_env):
    """تعديل داخل النافذة + سجل التغيير يشمل ABSENT→PRESENT وPRESENT→LATE."""
    students = teacher_env["students"]
    session = _start(teacher_env["client"], teacher_env["section"].id).json()
    _submit(
        teacher_env["client"], session["id"],
        [{"student_id": students[0].id, "status": "ABSENT"}],
    )

    start_str = session["period"]["start_time"]
    hour, minute = map(int, start_str.split(":"))
    arrival = time(hour, minute + 5) if minute + 5 < 60 else time(hour + 1, (minute + 5) % 60)
    response = _edit(
        teacher_env["client"], session["id"],
        [{"student_id": students[1].id, "status": "LATE",
          "arrival_time": arrival.strftime("%H:%M")}],
        reason="تصحيح خطأ",
    )
    assert response.status_code == 200
    marks = AttendanceMark.objects.filter(session_id=session["id"])
    assert marks.count() == 1
    assert marks.first().student_id == students[1].id

    changes = {
        (c.previous_status, c.new_status)
        for c in AttendanceChange.objects.filter(session_id=session["id"])
    }
    assert ("ABSENT", "PRESENT") in changes  # الطالب 0 عاد حاضرًا
    assert ("PRESENT", "LATE") in changes  # الطالب 1 صار متأخرًا
    change = AttendanceChange.objects.get(previous_status="PRESENT", new_status="LATE")
    assert change.new_late_minutes == 5
    assert change.reason == "تصحيح خطأ"


@pytest.mark.django_db
def test_edit_window_expired_for_teacher_but_admin_allowed(teacher_env, role_client):
    students = teacher_env["students"]
    session = _start(teacher_env["client"], teacher_env["section"].id).json()
    _submit(teacher_env["client"], session["id"],
            [{"student_id": students[0].id, "status": "ABSENT"}])

    # تجاوز النافذة (15 دقيقة افتراضيًا)
    AttendanceSession.objects.filter(id=session["id"]).update(
        submitted_at=dj_timezone.now() - timedelta(minutes=30)
    )
    expired = _edit(teacher_env["client"], session["id"], [])
    assert expired.status_code == 403
    assert expired.json()["code"] == "ATTENDANCE_EDIT_WINDOW_EXPIRED"

    # الوكيل: تصحيح إداري بلا نافذة
    vice, _, _ = role_client(["VICE_PRINCIPAL"], school=teacher_env["school"])
    admin_edit = _edit(vice, session["id"], [], reason="تصحيح إداري")
    assert admin_edit.status_code == 200
    assert AttendanceMark.objects.filter(session_id=session["id"]).count() == 0
    assert AttendanceChange.objects.filter(
        session_id=session["id"], previous_status="ABSENT", new_status="PRESENT"
    ).exists()


@pytest.mark.django_db
def test_other_teacher_cannot_edit(teacher_env, role_client):
    session = _start(teacher_env["client"], teacher_env["section"].id).json()
    _submit(teacher_env["client"], session["id"], [])
    other, _, _ = role_client(["TEACHER"], school=teacher_env["school"])
    response = _edit(other, session["id"], [])
    assert response.status_code == 403
    assert response.json()["code"] == "ATTENDANCE_PERMISSION_DENIED"


# ---------- العزل والأدوار ----------


@pytest.mark.django_db
def test_counselor_only_cannot_take_attendance(role_client):
    client, school, _ = role_client(["COUNSELOR"])
    env = setup_attendance_env(school)
    response = _start(client, env["section"].id)
    assert response.status_code == 403


@pytest.mark.django_db
def test_teacher_counselor_can_take_attendance(role_client):
    client, school, _ = role_client(["TEACHER", "COUNSELOR"])
    env = setup_attendance_env(school)
    assert _start(client, env["section"].id).status_code == 201


@pytest.mark.django_db
def test_tenant_isolation_sessions_and_sections(teacher_env, role_client):
    """معلم مدرسة أخرى: لا roster ولا submit ولا edit — 404."""
    session = _start(teacher_env["client"], teacher_env["section"].id).json()
    foreign_teacher, foreign_school, _ = role_client(["TEACHER"])
    setup_attendance_env(foreign_school, students_count=1)

    assert _start(foreign_teacher, teacher_env["section"].id).status_code == 404
    assert foreign_teacher.get(
        f"/api/v1/attendance/sessions/{session['id']}/"
    ).status_code == 404
    assert _submit(foreign_teacher, session["id"], []).status_code == 404
    assert _edit(foreign_teacher, session["id"], []).status_code == 404
    # قائمة فصوله لا تتضمن فصل المدرسة الأخرى
    sections = foreign_teacher.get("/api/v1/attendance/sections/").json()
    assert all(s["id"] != teacher_env["section"].id for s in sections)


@pytest.mark.django_db
def test_multi_school_teacher_sessions_attributed_correctly(
    make_user, make_membership, make_school, login_client
):
    """نفس المستخدم بمدرستين: كل جلسة بعضوية مدرستها."""
    from memberships.models import SchoolMembership

    user = make_user("0553330001")
    school_a, school_b = make_school("أ"), make_school("ب")
    make_membership(user, school_a, ["TEACHER"])
    make_membership(user, school_b, ["TEACHER"])
    env_a = setup_attendance_env(school_a, students_count=2)
    env_b = setup_attendance_env(school_b, students_count=2)

    client, _ = login_client("0553330001")
    client.post("/api/v1/session/active-school/", {"school_id": school_a.id},
                content_type="application/json")
    session_a = _start(client, env_a["section"].id).json()
    _submit(client, session_a["id"], [])

    client.post("/api/v1/session/active-school/", {"school_id": school_b.id},
                content_type="application/json")
    session_b = _start(client, env_b["section"].id).json()
    _submit(client, session_b["id"], [])

    a = AttendanceSession.objects.get(id=session_a["id"])
    b = AttendanceSession.objects.get(id=session_b["id"])
    membership_a = SchoolMembership.objects.get(user=user, school=school_a)
    membership_b = SchoolMembership.objects.get(user=user, school=school_b)
    assert a.school_id == school_a.id
    assert a.submitted_by_membership_id == membership_a.id
    assert b.school_id == school_b.id
    assert b.submitted_by_membership_id == membership_b.id


# ---------- Purge ----------


@pytest.mark.django_db
def test_purge_deletes_marks_and_changes_keeps_session(teacher_env, role_client):
    from students.services.lifecycle import set_student_status
    from students.services.purge import purge_student

    students = teacher_env["students"]
    session = _start(teacher_env["client"], teacher_env["section"].id).json()
    _submit(teacher_env["client"], session["id"],
            [{"student_id": students[0].id, "status": "ABSENT"}])
    _edit(teacher_env["client"], session["id"], [])  # ينشئ AttendanceChange

    target = students[0]
    set_student_status(student=target, new_status="WITHDRAWN", actor=teacher_env["user"])
    assert AttendanceChange.objects.filter(student=target).exists()

    purge_student(target)

    assert not AttendanceMark.objects.filter(student_id=target.id).exists()
    assert not AttendanceChange.objects.filter(student_id=target.id).exists()
    # الجلسة باقية — تخص الفصل والمعلم والحصة
    assert AttendanceSession.objects.filter(id=session["id"]).exists()


@pytest.mark.django_db
def test_unregistered_purge_fails_loudly(teacher_env, monkeypatch):
    """نسيان تسجيل خطوات الحضور في Purge → ProtectedError (البند 47)."""
    from django.db.models.deletion import ProtectedError

    from students.services import purge as purge_service
    from students.services.lifecycle import set_student_status
    from students.services.purge import purge_student

    students = teacher_env["students"]
    session = _start(teacher_env["client"], teacher_env["section"].id).json()
    _submit(teacher_env["client"], session["id"],
            [{"student_id": students[0].id, "status": "ABSENT"}])
    set_student_status(
        student=students[0], new_status="WITHDRAWN", actor=teacher_env["user"]
    )

    stripped = [
        step for step in purge_service.PURGE_STEPS
        if step[0] not in ("علامات الحضور", "تعديلات الحضور")
    ]
    monkeypatch.setattr(purge_service, "PURGE_STEPS", stripped)
    with pytest.raises(ProtectedError):
        purge_student(students[0])


@pytest.mark.django_db
def test_roster_query_count(teacher_env, django_assert_max_num_queries):
    from tests.attendance_helpers import make_students

    make_students(
        teacher_env["school"], teacher_env["section"], teacher_env["year"],
        45, prefix="10880",
    )
    client = teacher_env["client"]
    session = _start(client, teacher_env["section"].id).json()
    with django_assert_max_num_queries(12):
        response = client.get(f"/api/v1/attendance/sessions/{session['id']}/")
    assert response.status_code == 200
    assert len(response.json()["roster"]) == 50
