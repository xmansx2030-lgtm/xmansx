"""اختبارات واجهات الإجراءات والمستندات (م12) — الأدوار، التنزيل، العزل، mass assignment."""

import pytest
from django.utils import timezone as dj_timezone

from documents.models import DocumentStatus, GeneratedDocument
from documents.pdf import pdf_engine_available
from student_actions.models import StudentAction, StudentActionStatus
from student_warnings.models import StudentWarning, WarningLevel, WarningRuleType, WarningStatus
from tests.excuse_env import DAY, DAY2, build_env

pytestmark = pytest.mark.django_db

requires_pdf = pytest.mark.skipif(
    not pdf_engine_available(), reason="محرك PDF غير متوفر خارج الحاوية"
)

ACTIONS_URL = "/api/v1/student-actions/"
DOCUMENTS_URL = "/api/v1/documents/"
GENERATE_URL = "/api/v1/documents/generate/"
PREVIEW_URL = "/api/v1/documents/preview/"


@pytest.fixture
def env(make_school, make_user, make_membership):
    school = make_school()
    environment = build_env(
        school=school,
        teacher_membership=make_membership(make_user("0550001400"), school, ["TEACHER"]),
        vice_membership=make_membership(make_user("0550001401"), school, ["VICE_PRINCIPAL"]),
        prefix="30600",
    )
    from schools.models import SchoolSettings

    SchoolSettings.objects.create(
        school=school, ministry_school_number="55", city="الرياض",
        official_principal_name="مدير المدرسة الرسمي",
    )
    return environment


def login(role_client, env, roles):
    client, _, _ = role_client(roles, school=env["school"])
    return client


def make_warning(env, student, *, level=WarningLevel.LEVEL_2) -> StudentWarning:
    return StudentWarning.objects.create(
        school=env["school"], student=student, academic_year=env["year"],
        warning_type=WarningRuleType.UNEXCUSED_FULL_DAY_ABSENCE, level=level,
        status=WarningStatus.ISSUED, threshold_at_issue=5, metric_value_at_issue=5,
        student_name_snapshot=student.full_name, grade_name_snapshot="الأول الثانوي",
        section_name_snapshot="1", national_id_masked_snapshot=student.national_id_masked,
        unexcused_full_absence_days_at_issue=5,
        issued_by_membership=env["vice"], issued_at=dj_timezone.now(),
    )


def json_post(client, url, payload):
    return client.post(url, payload, content_type="application/json")


# ---------------------------------------------------------------- الإجراءات


def test_action_roles(role_client, env):
    student = env["students"][0]
    payload = {"student_id": student.id, "action_type": "PARENT_CONTACT", "notes": "اتصال"}

    manager = login(role_client, env, ["SCHOOL_MANAGER"])
    vice = login(role_client, env, ["VICE_PRINCIPAL"])
    counselor = login(role_client, env, ["COUNSELOR"])
    teacher = login(role_client, env, ["TEACHER"])

    assert json_post(vice, ACTIONS_URL, payload).status_code == 201
    assert json_post(manager, ACTIONS_URL, payload).status_code == 201
    # المرشد يقرأ ولا يكتب، والمعلم محجوب تمامًا (البندان 85-86)
    assert json_post(counselor, ACTIONS_URL, payload).status_code == 403
    assert counselor.get(f"{ACTIONS_URL}?student={student.id}").status_code == 200
    assert json_post(teacher, ACTIONS_URL, payload).status_code == 403
    assert teacher.get(ACTIONS_URL).status_code == 403


def test_action_list_and_cancel_flow(role_client, env):
    student = env["students"][0]
    vice = login(role_client, env, ["VICE_PRINCIPAL"])
    created = json_post(
        vice, ACTIONS_URL, {"student_id": student.id, "action_type": "STUDENT_MEETING"}
    ).json()

    listing = vice.get(f"{ACTIONS_URL}?student={student.id}").json()
    assert listing["count"] == 1
    assert listing["results"][0]["action_type_label"] == "مقابلة الطالب"
    assert listing["results"][0]["performed_by_name"]

    cancelled = json_post(
        vice, f"{ACTIONS_URL}{created['id']}/cancel/", {"reason": "سجل بالخطأ"}
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == StudentActionStatus.CANCELLED
    # الصف باقٍ لا محذوف
    assert StudentAction.objects.filter(id=created["id"]).count() == 1
    assert json_post(
        vice, f"{ACTIONS_URL}{created['id']}/cancel/", {"reason": "مرة أخرى"}
    ).status_code == 409


def test_action_tenant_isolation(role_client, env, make_school, make_user, make_membership):
    other_school = make_school()
    other = build_env(
        school=other_school,
        teacher_membership=make_membership(make_user("0550001410"), other_school, ["TEACHER"]),
        vice_membership=make_membership(
            make_user("0550001411"), other_school, ["VICE_PRINCIPAL"]
        ),
        prefix="30700",
    )
    vice = login(role_client, env, ["VICE_PRINCIPAL"])
    # طالب مدرسة أخرى غير موجود من منظور هذه الجلسة
    assert json_post(
        vice, ACTIONS_URL,
        {"student_id": other["students"][0].id, "action_type": "PARENT_CONTACT"},
    ).status_code == 404

    other_vice = login(role_client, other, ["VICE_PRINCIPAL"])
    foreign_action = json_post(
        other_vice, ACTIONS_URL,
        {"student_id": other["students"][0].id, "action_type": "PARENT_CONTACT"},
    ).json()
    assert vice.get(f"{ACTIONS_URL}{foreign_action['id']}/").status_code == 404
    assert json_post(
        vice, f"{ACTIONS_URL}{foreign_action['id']}/cancel/", {"reason": "x"}
    ).status_code == 404


# ---------------------------------------------------------------- المستندات


@requires_pdf
def test_preview_then_generate_warning_document(role_client, env):
    student = env["students"][0]
    warning = make_warning(env, student)
    vice = login(role_client, env, ["VICE_PRINCIPAL"])

    preview = json_post(
        vice, PREVIEW_URL,
        {"student_id": student.id, "document_type": "WARNING_LEVEL_2", "warning_id": warning.id},
    )
    assert preview.status_code == 200
    body = preview.json()
    assert body["already_exists"] is False
    assert body["snapshot"]["warning"]["metric_value_at_issue"] == 5
    assert body["template"] == "warning_level_2:v2"

    created = json_post(
        vice, GENERATE_URL,
        {"student_id": student.id, "document_type": "WARNING_LEVEL_2", "warning_id": warning.id},
    )
    assert created.status_code == 201
    assert created.json()["status"] == DocumentStatus.READY
    assert created.json()["can_download"] is True

    # المعاينة بعدها تخبر أن نسخة أصلية موجودة (البند 76)
    assert json_post(
        vice, PREVIEW_URL,
        {"student_id": student.id, "document_type": "WARNING_LEVEL_2", "warning_id": warning.id},
    ).json()["already_exists"] is True


@requires_pdf
def test_client_snapshot_values_are_ignored(role_client, env):
    """البند 92: قيم اللقطة المرسلة من العميل لا تصل إلى المستند."""
    student = env["students"][0]
    warning = make_warning(env, student)
    vice = login(role_client, env, ["VICE_PRINCIPAL"])
    response = json_post(
        vice, GENERATE_URL,
        {
            "student_id": student.id,
            "document_type": "WARNING_LEVEL_2",
            "warning_id": warning.id,
            "metric_value_at_issue": 99,
            "snapshot_data": {"student": {"name": "مزور"}},
            "template_version": "v9",
            "status": "READY",
        },
    )
    assert response.status_code == 201
    document = GeneratedDocument.objects.get(id=response.json()["id"])
    assert document.snapshot_data["warning"]["metric_value_at_issue"] == 5
    assert document.snapshot_data["student"]["name"] == student.full_name
    assert document.template_version == "v2"


@requires_pdf
def test_double_click_generates_one_document(role_client, env):
    student = env["students"][0]
    warning = make_warning(env, student)
    vice = login(role_client, env, ["VICE_PRINCIPAL"])
    payload = {
        "student_id": student.id, "document_type": "WARNING_LEVEL_2", "warning_id": warning.id
    }
    first = json_post(vice, GENERATE_URL, payload)
    second = json_post(vice, GENERATE_URL, payload)
    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["code"] == "DOCUMENT_ALREADY_EXISTS"
    assert GeneratedDocument.objects.filter(warning=warning).count() == 1


@requires_pdf
def test_download_permissions(role_client, env):
    student = env["students"][0]
    vice = login(role_client, env, ["VICE_PRINCIPAL"])
    document = json_post(
        vice, GENERATE_URL,
        {
            "student_id": student.id,
            "document_type": "ATTENDANCE_COMMITMENT",
            "from_date": DAY.isoformat(),
            "to_date": DAY2.isoformat(),
        },
    ).json()
    url = f"{DOCUMENTS_URL}{document['id']}/download/"

    response = vice.get(url)
    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"
    assert response["Content-Disposition"].startswith("attachment;")
    assert b"".join(response.streaming_content)[:5] == b"%PDF-"

    inline = vice.get(f"{url}?inline=1")
    assert inline.status_code == 200
    assert inline["Content-Disposition"].startswith("inline;")
    assert b"".join(inline.streaming_content)[:5] == b"%PDF-"

    manager = login(role_client, env, ["SCHOOL_MANAGER"])
    assert manager.get(url).status_code == 200
    # المرشد يرى البيانات الوصفية ولا ينزّل (البند 85)
    counselor = login(role_client, env, ["COUNSELOR"])
    assert counselor.get(url).status_code == 403
    listing = counselor.get(f"{DOCUMENTS_URL}?student={student.id}").json()
    assert listing["count"] == 1
    assert listing["results"][0]["can_download"] is False
    # المعلم محجوب تمامًا (البند 122)
    teacher = login(role_client, env, ["TEACHER"])
    assert teacher.get(url).status_code == 403
    assert teacher.get(DOCUMENTS_URL).status_code == 403


@requires_pdf
def test_counselor_detail_hides_snapshot(role_client, env):
    student = env["students"][0]
    vice = login(role_client, env, ["VICE_PRINCIPAL"])
    document = json_post(
        vice, GENERATE_URL,
        {
            "student_id": student.id, "document_type": "ATTENDANCE_COMMITMENT",
            "from_date": DAY.isoformat(), "to_date": DAY2.isoformat(),
        },
    ).json()
    counselor = login(role_client, env, ["COUNSELOR"])
    body = counselor.get(f"{DOCUMENTS_URL}{document['id']}/").json()
    assert "snapshot" not in body
    assert body["document_type_label"] == "تعهد الالتزام بالحضور"
    assert vice.get(f"{DOCUMENTS_URL}{document['id']}/").json()["snapshot"]


@requires_pdf
def test_commitment_can_create_linked_action(role_client, env):
    """البند 68: تعهد ← مستند جاهز ثم إجراء «أخذ تعهد» مرتبط به."""
    student = env["students"][0]
    vice = login(role_client, env, ["VICE_PRINCIPAL"])
    response = json_post(
        vice, GENERATE_URL,
        {
            "student_id": student.id,
            "document_type": "ATTENDANCE_COMMITMENT",
            "from_date": DAY.isoformat(),
            "to_date": DAY2.isoformat(),
            "create_action": True,
            "notes": "وقع التعهد بحضور ولي الأمر",
        },
    )
    assert response.status_code == 201
    action_id = response.json()["action_id"]
    assert action_id is not None
    action = StudentAction.objects.get(id=action_id)
    assert action.action_type == "COMMITMENT_TAKEN"
    assert action.notes.startswith("وقع التعهد")


@requires_pdf
def test_document_tenant_isolation(role_client, env, make_school, make_user, make_membership):
    """البند 123: مدير مدرسة أخرى لا يصل لمستند هذه المدرسة بأي مسار."""
    other_school = make_school()
    other = build_env(
        school=other_school,
        teacher_membership=make_membership(make_user("0550001420"), other_school, ["TEACHER"]),
        vice_membership=make_membership(
            make_user("0550001421"), other_school, ["VICE_PRINCIPAL"]
        ),
        prefix="30800",
    )
    student = env["students"][0]
    vice = login(role_client, env, ["VICE_PRINCIPAL"])
    document = json_post(
        vice, GENERATE_URL,
        {
            "student_id": student.id, "document_type": "ATTENDANCE_COMMITMENT",
            "from_date": DAY.isoformat(), "to_date": DAY2.isoformat(),
        },
    ).json()

    foreign_manager = login(role_client, other, ["SCHOOL_MANAGER"])
    assert foreign_manager.get(f"{DOCUMENTS_URL}{document['id']}/").status_code == 404
    assert foreign_manager.get(f"{DOCUMENTS_URL}{document['id']}/download/").status_code == 404
    assert json_post(
        foreign_manager, f"{DOCUMENTS_URL}{document['id']}/void/", {"reason": "x"}
    ).status_code == 404
    assert foreign_manager.get(DOCUMENTS_URL).json()["count"] == 0


@requires_pdf
def test_void_is_manager_only(role_client, env):
    student = env["students"][0]
    vice = login(role_client, env, ["VICE_PRINCIPAL"])
    document = json_post(
        vice, GENERATE_URL,
        {
            "student_id": student.id, "document_type": "ATTENDANCE_COMMITMENT",
            "from_date": DAY.isoformat(), "to_date": DAY2.isoformat(),
        },
    ).json()
    url = f"{DOCUMENTS_URL}{document['id']}/void/"
    assert json_post(vice, url, {"reason": "خطأ"}).status_code == 403
    manager = login(role_client, env, ["SCHOOL_MANAGER"])
    response = json_post(manager, url, {"reason": "أُصدر بالخطأ"})
    assert response.status_code == 200
    assert response.json()["status"] == DocumentStatus.VOIDED
    # الملغى لا ينزل
    assert manager.get(f"{DOCUMENTS_URL}{document['id']}/download/").status_code == 409


def test_invalid_report_range_rejected(role_client, env):
    student = env["students"][0]
    vice = login(role_client, env, ["VICE_PRINCIPAL"])
    response = json_post(
        vice, GENERATE_URL,
        {
            "student_id": student.id,
            "document_type": "ABSENCE_DETAIL_REPORT",
            "from_date": "2026-09-01",
            "to_date": "2026-08-01",
        },
    )
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_REPORT_DATE_RANGE"


def test_warning_document_requires_matching_warning(role_client, env):
    student = env["students"][0]
    vice = login(role_client, env, ["VICE_PRINCIPAL"])
    response = json_post(
        vice, GENERATE_URL, {"student_id": student.id, "document_type": "WARNING_LEVEL_1"}
    )
    assert response.status_code == 400


@requires_pdf
def test_document_list_filters(role_client, env):
    student = env["students"][0]
    vice = login(role_client, env, ["VICE_PRINCIPAL"])
    for document_type in ("ATTENDANCE_COMMITMENT", "ABSENCE_DETAIL_REPORT"):
        json_post(
            vice, GENERATE_URL,
            {
                "student_id": student.id, "document_type": document_type,
                "from_date": DAY.isoformat(), "to_date": DAY2.isoformat(),
            },
        )
    listing = vice.get(f"{DOCUMENTS_URL}?document_type=ABSENCE_DETAIL_REPORT").json()
    assert listing["count"] == 1
    assert listing["results"][0]["document_type"] == "ABSENCE_DETAIL_REPORT"
    assert vice.get(f"{DOCUMENTS_URL}?student={student.id}").json()["count"] == 2
    # لا رقم هوية كامل في أي صف
    assert "national_id" not in listing["results"][0]


@requires_pdf
def test_reprint_returns_identical_bytes(role_client, env):
    """السيناريو 132: تنزيلان متتاليان بعد تغير البيانات = نفس المحتوى والبصمة."""
    student = env["students"][0]
    warning = make_warning(env, student)
    vice = login(role_client, env, ["VICE_PRINCIPAL"])
    document = json_post(
        vice, GENERATE_URL,
        {"student_id": student.id, "document_type": "WARNING_LEVEL_2", "warning_id": warning.id},
    ).json()
    url = f"{DOCUMENTS_URL}{document['id']}/download/"
    first = b"".join(vice.get(url).streaming_content)

    student.full_name = "اسم مختلف بعد النقل"
    student.save(update_fields=["full_name"])
    warning.metric_value_at_issue = 99  # حتى لو زُوّر السجل الحي
    warning.save(update_fields=["metric_value_at_issue"])

    second = b"".join(vice.get(url).streaming_content)
    assert first == second
    assert vice.get(f"{DOCUMENTS_URL}{document['id']}/").json()["checksum"] == document["checksum"]
