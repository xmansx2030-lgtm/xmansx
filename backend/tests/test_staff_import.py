"""اختبارات استيراد المعلمين: جديد/موجود/دعوات/idempotency/stale/أمان كلمة المرور."""

import pytest
from django.test import Client

from accounts.models import User
from memberships.models import (
    MembershipStatus,
    SchoolMembership,
)
from staff.models import StaffProfile
from tests.xlsx_helper import build_xlsx_upload

IMPORTS_URL = "/api/v1/staff-imports/"
STAFF_HEADERS = ["اسم المعلم", "رقم الجوال", "الرقم الوظيفي", "المسمى الوظيفي"]


def staff_row(name: str, mobile: str, number: str = "", title: str = "") -> list:
    return [name, mobile, number, title]


def upload(client, rows, headers=None):
    return client.post(
        IMPORTS_URL,
        {"file": build_xlsx_upload(rows, headers or STAFF_HEADERS, filename="staff.xlsx")},
    )


def process(client, job_id):
    return client.post(f"{IMPORTS_URL}{job_id}/process/", {}, content_type="application/json")


def run_import(client, rows):
    job = upload(client, rows).json()
    process(client, job["id"])
    return client.post(f"{IMPORTS_URL}{job['id']}/commit/")


@pytest.mark.django_db
def test_new_teacher_full_chain(role_client):
    """جديد: User + عضوية + دور TEACHER + Profile + كلمة مؤقتة تعمل + إجبار التغيير."""
    client, school, _ = role_client(["SCHOOL_MANAGER"])
    response = run_import(client, [staff_row("أحمد الغامدي", "0559990001", "T-1", "معلم رياضيات")])
    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["created"] == 1
    credentials = body["new_credentials"]
    assert len(credentials) == 1
    temp_password = credentials[0]["temporary_password"]
    assert len(temp_password) >= 10
    assert "0559990001" not in str(credentials)  # الجوال مقنع في النتيجة

    user = User.objects.get(mobile="+966559990001")
    assert user.must_change_password is True
    assert user.check_password(temp_password)
    membership = SchoolMembership.objects.get(user=user, school=school)
    assert membership.status == MembershipStatus.ACTIVE
    assert membership.role_codes() == ["TEACHER"]
    profile = StaffProfile.objects.get(membership=membership)
    assert profile.display_name == "أحمد الغامدي"
    assert profile.employee_number == "T-1"

    # الدخول بالكلمة المؤقتة يعمل
    login = Client().post(
        "/api/v1/auth/login/",
        {"mobile": "0559990001", "password": temp_password},
        content_type="application/json",
    )
    assert login.status_code == 200
    assert login.json()["must_change_password"] is True


@pytest.mark.django_db
def test_temp_password_never_stored_plaintext(role_client):
    """بحث شامل: DB (job/rows/audit/user) لا تحتوي الكلمة المؤقتة plaintext."""
    from audit.models import AuditLog
    from staff.models import StaffImportJob, StaffImportRow

    client, school, _ = role_client(["SCHOOL_MANAGER"])
    body = run_import(client, [staff_row("سري تمامًا", "0559990002")]).json()
    temp_password = body["new_credentials"][0]["temporary_password"]

    job = StaffImportJob.objects.get(school=school)
    assert temp_password not in str(job.summary)
    assert temp_password not in str(job.column_mapping)
    assert not StaffImportRow.objects.filter(job=job).exists()  # staging حذف
    for log in AuditLog.objects.all():
        assert temp_password not in str(log.metadata)
    user = User.objects.get(mobile="+966559990002")
    assert temp_password not in user.password  # hash فقط


@pytest.mark.django_db
def test_existing_global_user_invited_not_duplicated(role_client, make_user, make_membership,
                                                     make_school):
    """موجود عالميًا في مدرسة أخرى: نفس User، دعوة، كلمة المرور لم تمس، لا تسريب."""
    school_b = make_school("مدرسة أخرى")
    existing = make_user("0559990003")
    make_membership(existing, school_b, ["TEACHER"])
    password_hash_before = existing.password

    client, school_a, _ = role_client(["SCHOOL_MANAGER"])
    job = upload(client, [staff_row("أ. المعلم المشترك", "0559990003")]).json()
    process(client, job["id"])
    preview = client.get(f"{IMPORTS_URL}{job['id']}/").json()
    assert preview["summary"]["invite"] == 1
    # لا تسريب لمدارس المستخدم الأخرى في بيانات المعاينة
    rows = client.get(
        f"{IMPORTS_URL}{job['id']}/preview/?category=EXISTING_USER_INVITE"
    ).json()["results"]
    assert "مدرسة أخرى" not in str(rows)

    commit = client.post(f"{IMPORTS_URL}{job['id']}/commit/")
    assert commit.json()["new_credentials"] == []  # لا كلمات مرور لحسابات موجودة

    assert User.objects.filter(mobile="+966559990003").count() == 1
    existing.refresh_from_db()
    assert existing.password == password_hash_before  # لم تتغير
    assert existing.must_change_password is False
    invited = SchoolMembership.objects.get(user=existing, school=school_a)
    assert invited.status == MembershipStatus.INVITED
    assert "TEACHER" in invited.role_codes()
    # الملف الوظيفي باسم العرض الخاص بالمدرسة — الاسم العالمي لم يتغير
    assert StaffProfile.objects.get(membership=invited).display_name == "أ. المعلم المشترك"
    assert existing.first_name != "أ. المعلم المشترك"


@pytest.mark.django_db
def test_same_school_reimport_idempotent(role_client):
    client, school, _ = role_client(["SCHOOL_MANAGER"])
    run_import(client, [staff_row("معلم مكرر", "0559990004")])
    counts_before = (
        User.objects.filter(mobile="+966559990004").count(),
        SchoolMembership.objects.filter(school=school).count(),
        StaffProfile.objects.filter(school=school).count(),
    )
    second = run_import(client, [staff_row("معلم مكرر", "0559990004")])
    assert second.json()["summary"]["unchanged"] == 1
    counts_after = (
        User.objects.filter(mobile="+966559990004").count(),
        SchoolMembership.objects.filter(school=school).count(),
        StaffProfile.objects.filter(school=school).count(),
    )
    assert counts_before == counts_after
    membership = SchoolMembership.objects.get(user__mobile="+966559990004", school=school)
    assert membership.roles.count() == 1  # دور واحد لا أكثر


@pytest.mark.django_db
def test_counselor_gains_teacher_role_keeps_counselor(role_client, make_user, make_membership):
    client, school, _ = role_client(["SCHOOL_MANAGER"])
    counselor = make_user("0559990005", first_name="فهد")
    make_membership(counselor, school, ["COUNSELOR"])

    job = upload(client, [staff_row("فهد المرشد", "0559990005")]).json()
    process(client, job["id"])
    assert client.get(f"{IMPORTS_URL}{job['id']}/").json()["summary"]["add_role"] == 1
    client.post(f"{IMPORTS_URL}{job['id']}/commit/")

    membership = SchoolMembership.objects.get(user=counselor, school=school)
    assert sorted(membership.role_codes()) == ["COUNSELOR", "TEACHER"]


@pytest.mark.django_db
def test_pending_invitation_not_duplicated(role_client, make_user):
    client, school, _ = role_client(["SCHOOL_MANAGER"])
    invitee = make_user("0559990006")
    SchoolMembership.objects.create(
        user=invitee, school=school, status=MembershipStatus.INVITED
    )
    job = upload(client, [staff_row("مدعو قائم", "0559990006")]).json()
    process(client, job["id"])
    assert client.get(f"{IMPORTS_URL}{job['id']}/").json()["summary"]["invitation_pending"] == 1
    client.post(f"{IMPORTS_URL}{job['id']}/commit/")
    assert SchoolMembership.objects.filter(user=invitee, school=school).count() == 1


@pytest.mark.django_db
def test_declined_membership_not_reinvited_silently(role_client, make_user):
    client, school, _ = role_client(["SCHOOL_MANAGER"])
    decliner = make_user("0559990007")
    SchoolMembership.objects.create(
        user=decliner, school=school, status=MembershipStatus.DECLINED
    )
    job = upload(client, [staff_row("رافض سابق", "0559990007")]).json()
    process(client, job["id"])
    assert client.get(f"{IMPORTS_URL}{job['id']}/").json()["summary"]["manual"] == 1
    client.post(f"{IMPORTS_URL}{job['id']}/commit/")
    membership = SchoolMembership.objects.get(user=decliner, school=school)
    assert membership.status == MembershipStatus.DECLINED  # لم تتغير بصمت


@pytest.mark.django_db
def test_duplicate_mobile_in_file_and_invalid_rows(role_client):
    client, _, _ = role_client(["SCHOOL_MANAGER"])
    job = upload(
        client,
        [
            staff_row("صالح", "0559990008"),
            staff_row("مكرر أول", "0559990009"),
            staff_row("مكرر ثاني", "٠٥٥٩٩٩٠٠٠٩"),  # نفس الرقم بأرقام عربية
            staff_row("جوال خاطئ", "12345"),
            staff_row("", "0559990010"),
        ],
    ).json()
    process(client, job["id"])
    summary = client.get(f"{IMPORTS_URL}{job['id']}/").json()["summary"]
    assert summary["new"] == 1
    assert summary["duplicates"] == 2
    assert summary["errors"] == 2


@pytest.mark.django_db
def test_commit_twice_idempotent(role_client):
    client, school, _ = role_client(["SCHOOL_MANAGER"])
    job = upload(client, [staff_row("مرة واحدة", "0559990011")]).json()
    process(client, job["id"])
    assert client.post(f"{IMPORTS_URL}{job['id']}/commit/").status_code == 200
    second = client.post(f"{IMPORTS_URL}{job['id']}/commit/")
    assert second.status_code == 409
    assert second.json()["code"] == "STAFF_IMPORT_ALREADY_COMMITTED"
    assert User.objects.filter(mobile="+966559990011").count() == 1


@pytest.mark.django_db
def test_stale_preview_detected(role_client, make_user, make_membership):
    """يضاف الموظف يدويًا بين المعاينة والاعتماد → STALE ومعاينة محدثة."""
    client, school, _ = role_client(["SCHOOL_MANAGER"])
    job = upload(client, [staff_row("سباق", "0559990012")]).json()
    process(client, job["id"])
    assert client.get(f"{IMPORTS_URL}{job['id']}/").json()["summary"]["new"] == 1

    # الواقع يتغير: المستخدم أنشئ وانضم للمدرسة عبر مسار آخر
    racer = make_user("0559990012")
    make_membership(racer, school, ["TEACHER"])

    commit = client.post(f"{IMPORTS_URL}{job['id']}/commit/")
    assert commit.status_code == 409
    assert commit.json()["code"] == "STAFF_IMPORT_PREVIEW_STALE"
    refreshed = client.get(f"{IMPORTS_URL}{job['id']}/").json()
    assert refreshed["status"] == "READY_FOR_REVIEW"
    assert refreshed["summary"]["new"] == 0

    # الاعتماد بعد المراجعة يمر بلا تكرار
    assert client.post(f"{IMPORTS_URL}{job['id']}/commit/").status_code == 200
    assert User.objects.filter(mobile="+966559990012").count() == 1


@pytest.mark.django_db
def test_user_creation_race_unique_constraint(role_client, make_user):
    """قيد UNIQUE(mobile) في DB + التقاط IntegrityError → لا User مكرر."""
    client, school, _ = role_client(["SCHOOL_MANAGER"])
    job = upload(client, [staff_row("متسابق", "0559990013")]).json()
    process(client, job["id"])

    # يحاكي السباق: مستخدم آخر ينشئ الحساب قبل commit مباشرة
    make_user("0559990013")
    commit = client.post(f"{IMPORTS_URL}{job['id']}/commit/")
    # stale protection يلتقطها أولًا (تصنيف تغير من NEW إلى INVITE)
    assert commit.status_code == 409
    client.post(f"{IMPORTS_URL}{job['id']}/commit/")
    assert User.objects.filter(mobile="+966559990013").count() == 1
    assert SchoolMembership.objects.filter(
        user__mobile="+966559990013", school=school
    ).count() == 1


@pytest.mark.django_db
def test_import_permissions(role_client, make_school):
    school = make_school()
    vice, _, _ = role_client(["VICE_PRINCIPAL"], school=school)
    teacher, _, _ = role_client(["TEACHER"], school=school)
    rows = [staff_row("ممنوع", "0559990014")]
    assert upload(vice, rows).status_code == 403
    assert upload(teacher, rows).status_code == 403


@pytest.mark.django_db
def test_tenant_isolation_staff_imports(role_client):
    manager_a, _, _ = role_client(["SCHOOL_MANAGER"])
    manager_b, _, _ = role_client(["SCHOOL_MANAGER"])
    foreign_job = upload(manager_b, [staff_row("أجنبي", "0559990015")]).json()
    assert manager_a.get(f"{IMPORTS_URL}{foreign_job['id']}/").status_code == 404
    assert manager_a.post(f"{IMPORTS_URL}{foreign_job['id']}/commit/").status_code == 404
