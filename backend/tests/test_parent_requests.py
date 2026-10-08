"""Family review, protected files, isolation, and existing business contracts."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event

import pytest
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import close_old_connections, connection, connections
from django.test import Client
from django.utils import timezone

from attendance.models import AttendanceChange, AttendanceMark
from audit.models import AuditLog
from common.errors import ApiError
from common.tenant_rls import tenant_context
from documents.models import GeneratedDocument
from excuses.models import AbsenceExcuse, AbsenceExcuseCoverage
from parents import request_services
from parents.models import (
    FamilyPublication,
    FamilyPublicationAcknowledgement,
    GuardianStudentRelation,
    ParentExcuseRequest,
    ParentNotification,
    WarningAcknowledgement,
)
from student_warnings.models import StudentWarning
from subscriptions.usage import count_active_staff, storage_used_bytes
from tests.excuse_env import DAY, build_env, make_session, mark

pytestmark = pytest.mark.django_db
VALID_PDF = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n%%EOF\n"


@pytest.fixture
def family_env(make_school, make_user, make_membership, settings, tmp_path):
    settings.GENERATED_DOCUMENTS_ROOT = str(tmp_path / "private")
    school = make_school()
    teacher = make_membership(make_user("0551700001"), school, ["TEACHER"])
    vice = make_membership(make_user("0551700002"), school, ["VICE_PRINCIPAL"])
    env = build_env(school=school, teacher_membership=teacher, vice_membership=vice, prefix="37100")
    user = make_user("0551700003", first_name="ولي الأمر")
    relation = GuardianStudentRelation.objects.create(
        school=school,
        student=env["students"][0],
        user=user,
        status="ACTIVE",
        contact_bound=False,
        approved_by=vice.user,
        approved_at=timezone.now(),
    )
    parent_client = Client()
    parent_client.force_login(user)
    staff_client = Client()
    staff_client.force_login(vice.user)
    session_state = staff_client.session
    session_state["active_school_id"] = school.id
    session_state.save()
    session = make_session(env, 1)
    mark(env, session, relation.student, "ABSENT")
    env.update(
        user=user,
        relation=relation,
        client=parent_client,
        staff_client=staff_client,
        session=session,
        prefix=f"/api/v1/parent/children/{relation.id}",
    )
    return env


def post(client, url, payload=None):
    return client.post(url, payload or {}, content_type="application/json")


def submit(env):
    return post(
        env["client"],
        f"{env['prefix']}/excuses/",
        {
            "reason_type": "MEDICAL_REPORT",
            "notes": "تقرير مرفق للمراجعة",
            "targets": [{"attendance_date": DAY.isoformat(), "period_sequence": 1}],
        },
    )


def approve(env, request_id, decision="APPROVED", note="تم التحقق"):
    return post(
        env["staff_client"],
        f"/api/v1/staff/parents/excuses/{request_id}/decision/",
        {"decision": decision, "note": note},
    )


def test_parent_excuse_is_pending_and_school_approval_reuses_existing_service(family_env):
    env = family_env
    response = submit(env)
    assert response.status_code == 201
    request_id = response.json()["id"]
    assert response.json()["status"] == "PENDING"
    assert not AbsenceExcuse.objects.exists()
    assert approve(env, request_id).status_code == 200
    obj = ParentExcuseRequest.objects.get(id=request_id)
    assert obj.status == "APPROVED"
    assert obj.administrative_excuse.status == "APPROVED"
    assert AbsenceExcuseCoverage.objects.filter(
        excuse=obj.administrative_excuse, status="ACTIVE"
    ).exists()
    assert (
        AttendanceMark.objects.get(session=env["session"], student=env["relation"].student).status
        == "ABSENT"
    )
    assert approve(env, request_id).status_code == 409
    assert AbsenceExcuse.objects.count() == 1


def test_duplicate_parent_request_is_rejected(family_env):
    assert submit(family_env).status_code == 201
    response = submit(family_env)
    assert response.status_code == 409
    assert response.json()["code"] == "PARENT_REQUEST_DUPLICATE"


def test_parent_needs_info_resubmit_then_reject_has_no_attendance_effect(family_env):
    env = family_env
    request_id = submit(env).json()["id"]
    assert approve(env, request_id, "NEEDS_INFO", "أرفق التقرير").status_code == 200
    response = post(
        env["client"],
        f"{env['prefix']}/excuses/{request_id}/resubmit/",
        {"notes": "استكملت البيانات"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "PENDING"
    assert approve(env, request_id, "REJECTED", "لم يثبت العذر").status_code == 200
    assert not AbsenceExcuse.objects.exists()
    assert AttendanceMark.objects.filter(session=env["session"], status="ABSENT").exists()


def test_parent_attachment_private_counted_and_blocked_after_suspension(family_env):
    env = family_env
    request_id = submit(env).json()["id"]
    response = env["client"].post(
        f"{env['prefix']}/excuses/{request_id}/attachments/",
        {
            "file": SimpleUploadedFile("تقرير.pdf", VALID_PDF, content_type="application/pdf"),
        },
    )
    assert response.status_code == 201
    attachment_id = response.json()["id"]
    attachment = ParentExcuseRequest.objects.get(id=request_id).attachments.get(id=attachment_id)
    assert storage_used_bytes(env["school"]) == len(VALID_PDF)
    with pytest.raises(ValueError):
        _ = attachment.file.url
    url = f"{env['prefix']}/excuses/{request_id}/attachments/{attachment_id}/download/"
    response = env["client"].get(url)
    assert response.status_code == 200
    assert b"".join(response.streaming_content) == VALID_PDF
    assert "no-store" in response["Cache-Control"] and "private" in response["Cache-Control"]
    env["relation"].status = "SUSPENDED_CONTACT_REVIEW"
    env["relation"].save(update_fields=["status"])
    assert env["client"].get(url).status_code == 404
    assert env["client"].get(f"{env['prefix']}/excuses/").status_code == 404


def test_parent_attachment_validates_real_content(family_env):
    env = family_env
    request_id = submit(env).json()["id"]
    response = env["client"].post(
        f"{env['prefix']}/excuses/{request_id}/attachments/",
        {
            "file": SimpleUploadedFile(
                "fake.pdf", b"<html>bad</html>", content_type="application/pdf"
            ),
        },
    )
    assert response.status_code == 400
    assert response.json()["code"] == "EXCUSE_ATTACHMENT_INVALID"


def test_correction_reuses_authoritative_history_and_rejects_double_decision(family_env):
    env = family_env
    response = post(
        env["client"],
        f"{env['prefix']}/corrections/",
        {
            "session_id": env["session"].id,
            "reason": "كان ابني حاضراً",
        },
    )
    assert response.status_code == 201
    request_id = response.json()["id"]
    assert AttendanceMark.objects.filter(
        session=env["session"], student=env["relation"].student
    ).exists()
    url = f"/api/v1/staff/parents/corrections/{request_id}/decision/"
    response = post(
        env["staff_client"], url, {"decision": "APPROVED", "note": "تم التحقق من الحضور"}
    )
    assert response.status_code == 200
    assert not AttendanceMark.objects.filter(
        session=env["session"], student=env["relation"].student
    ).exists()
    change = AttendanceChange.objects.get(session=env["session"], student=env["relation"].student)
    assert change.previous_status == "ABSENT" and change.new_status == "PRESENT"
    assert change.actor_membership == env["vice"]
    assert AuditLog.objects.filter(action="ATTENDANCE_EDITED").exists()
    assert post(env["staff_client"], url, {"decision": "APPROVED"}).status_code == 409


def test_correction_cannot_target_draft_or_present_student(family_env):
    env = family_env
    draft = make_session(env, 2, status="IN_PROGRESS")
    mark(env, draft, env["relation"].student, "ABSENT")
    assert (
        post(
            env["client"],
            f"{env['prefix']}/corrections/",
            {"session_id": draft.id, "reason": "مراجعة"},
        ).status_code
        == 404
    )
    present = make_session(env, 3)
    assert (
        post(
            env["client"],
            f"{env['prefix']}/corrections/",
            {"session_id": present.id, "reason": "مراجعة"},
        ).status_code
        == 404
    )


def test_other_parent_cannot_list_or_submit_or_download(family_env, make_user):
    env = family_env
    other = Client()
    other.force_login(make_user("0551700099"))
    request_id = submit(env).json()["id"]
    assert other.get(f"{env['prefix']}/excuses/").status_code == 404
    assert (
        post(
            other, f"{env['prefix']}/excuses/{request_id}/resubmit/", {"notes": "سرقة"}
        ).status_code
        == 404
    )
    assert other.get(f"{env['prefix']}/publications/").status_code == 404
    assert other.get(f"{env['prefix']}/warnings/").status_code == 404


def test_parent_cannot_review_excuse_or_modify_attendance_or_create_leave(family_env):
    env = family_env
    request_id = submit(env).json()["id"]
    assert (
        post(
            env["client"],
            f"/api/v1/staff/parents/excuses/{request_id}/decision/",
            {"decision": "APPROVED"},
        ).status_code
        == 403
    )
    assert (
        post(
            env["client"], "/api/v1/excuses/", {"student_id": env["relation"].student_id}
        ).status_code
        == 403
    )
    assert (
        post(
            env["client"], "/api/v1/student-leaves/", {"student_id": env["relation"].student_id}
        ).status_code
        == 403
    )
    assert env["client"].get("/api/v1/gate/student-leaves/").status_code == 403
    assert count_active_staff(env["school"]) == 2


def make_warning(env):
    return StudentWarning.objects.create(
        school=env["school"],
        student=env["relation"].student,
        academic_year=env["year"],
        warning_type="UNEXCUSED_FULL_DAY_ABSENCE",
        level="LEVEL_1",
        status="ISSUED",
        threshold_at_issue=3,
        metric_value_at_issue=3,
        student_name_snapshot=env["relation"].student.full_name,
        issued_by_membership=env["vice"],
        issued_at=timezone.now(),
    )


def test_warning_acknowledgement_is_explicit_and_idempotent(family_env):
    env = family_env
    warning = make_warning(env)
    assert env["client"].get(f"{env['prefix']}/warnings/").status_code == 200
    assert not WarningAcknowledgement.objects.exists()
    url = f"{env['prefix']}/warnings/{warning.id}/acknowledge/"
    assert post(env["client"], url).status_code == 200
    assert post(env["client"], url).status_code == 200
    assert WarningAcknowledgement.objects.count() == 1
    warning.status = "VOIDED"
    warning.save(update_fields=["status"])
    assert post(env["client"], url).status_code == 404


def test_warning_acknowledgement_completes_notice_and_catchup_respects_it(family_env):
    env = family_env
    warning = make_warning(env)
    notices = env["client"].get("/api/v1/parent/notifications/").json()["items"]
    notice = next(item for item in notices if item["kind"] == "WARNING")
    assert notice["action_completed_at"] is None
    assert (
        post(env["client"], f"/api/v1/parent/notifications/{notice['id']}/read/").status_code == 200
    )
    assert not WarningAcknowledgement.objects.exists()
    response = post(env["client"], f"{env['prefix']}/warnings/{warning.id}/acknowledge/")
    assert response.status_code == 200
    obj = ParentNotification.objects.get(id=notice["id"])
    assert obj.action_completed_at is not None
    assert obj.action_completed_at.isoformat() == response.json()["acknowledged_at"]
    obj.delete()
    catchup = env["client"].get("/api/v1/parent/notifications/").json()["items"]
    notice = next(item for item in catchup if item["kind"] == "WARNING")
    assert notice["state"] == "ACTION_COMPLETED"
    assert notice["action_completed_at"] == response.json()["acknowledged_at"]
    assert WarningAcknowledgement.objects.count() == 1


def test_publication_explicit_safe_text_and_revocation(family_env):
    env = family_env
    response = post(
        env["staff_client"],
        "/api/v1/staff/parents/publications/",
        {
            "student_id": env["relation"].student_id,
            "title": "توصيات للأسرة",
            "body": "ساعدوا الطالب على تنظيم النوم",
            "required_action": "الاطلاع والمتابعة",
        },
    )
    assert response.status_code == 201
    publication_id = response.json()["id"]
    notice = ParentNotification.objects.get(
        relation=env["relation"], dedup_key=f"publication:{publication_id}"
    )
    complete_url = f"/api/v1/parent/notifications/{notice.id}/complete-action/"
    assert post(env["client"], complete_url).status_code == 409
    assert not FamilyPublicationAcknowledgement.objects.exists()
    response = env["client"].get(f"{env['prefix']}/publications/")
    assert response.json()["items"][0]["body"] == "ساعدوا الطالب على تنظيم النوم"
    assert not FamilyPublicationAcknowledgement.objects.exists()
    assert (
        post(
            env["client"], f"{env['prefix']}/publications/{publication_id}/acknowledge/"
        ).status_code
        == 200
    )
    assert FamilyPublicationAcknowledgement.objects.count() == 1
    staff_publication = (
        env["staff_client"].get("/api/v1/staff/parents/publications/").json()["items"][0]
    )
    assert staff_publication["ack_count"] == 1
    assert staff_publication["acknowledgements"][0]["relation_id"] == env["relation"].id
    assert env["user"].mobile not in str(staff_publication["acknowledgements"])
    assert (
        "acknowledgements"
        not in env["client"].get(f"{env['prefix']}/publications/").json()["items"][0]
    )
    assert post(env["client"], complete_url).status_code == 200
    response = post(
        env["staff_client"],
        f"/api/v1/staff/parents/publications/{publication_id}/revoke/",
        {"reason": "تم تحديث التوصيات"},
    )
    assert response.status_code == 200
    notice.refresh_from_db()
    assert not notice.requires_action
    assert notice.body == ""
    assert notice.action_completed_at is not None
    assert post(env["client"], complete_url).status_code == 404
    notice_read = post(env["client"], f"/api/v1/parent/notifications/{notice.id}/read/")
    assert notice_read.status_code == 200
    assert notice_read.json()["body"] == ""
    assert notice_read.json()["requires_action"] is False
    assert env["client"].get(f"{env['prefix']}/publications/").json()["items"] == []
    assert (
        post(
            env["client"], f"{env['prefix']}/publications/{publication_id}/acknowledge/"
        ).status_code
        == 404
    )


def test_document_requires_explicit_publication_and_blocks_voided_warning(family_env):
    env = family_env
    warning = make_warning(env)
    document = GeneratedDocument.objects.create(
        school=env["school"],
        student=env["relation"].student,
        warning=warning,
        document_type="WARNING_LEVEL_1",
        template_key="warning",
        template_version="v3",
        generated_by_membership=env["vice"],
    )
    document.file.save("document.pdf", ContentFile(VALID_PDF))
    document.status = "READY"
    document.save()
    assert env["client"].get(f"{env['prefix']}/warnings/").json()["items"][0]["documents"] == []
    publication = post(
        env["staff_client"],
        "/api/v1/staff/parents/publications/",
        {
            "student_id": env["relation"].student_id,
            "title": "نسخة الإنذار",
            "document_id": document.id,
        },
    ).json()
    url = f"{env['prefix']}/publications/{publication['id']}/download/"
    response = env["client"].get(url)
    assert response.status_code == 200
    assert b"".join(response.streaming_content) == VALID_PDF
    warning.status = "VOIDED"
    warning.save(update_fields=["status"])
    assert env["client"].get(url).status_code == 404
    with tenant_context(school_id=env["school"].id, user_id=env["vice"].user_id):
        with pytest.raises(ApiError) as error:
            request_services.publish_family(
                school=env["school"],
                membership=env["vice"],
                student=env["relation"].student,
                title="نسخة قديمة",
                body="",
                document=document,
            )
    assert error.value.code == "DOCUMENT_NOT_READY"
    assert FamilyPublication.objects.count() == 1
    warning.status = "ISSUED"
    warning.save(update_fields=["status"])
    GeneratedDocument.objects.filter(id=document.id).update(status="VOIDED")
    assert document.status == "READY"
    with tenant_context(school_id=env["school"].id, user_id=env["vice"].user_id):
        with pytest.raises(ApiError) as error:
            request_services.publish_family(
                school=env["school"],
                membership=env["vice"],
                student=env["relation"].student,
                title="نسخة ملغاة",
                body="",
                document=document,
            )
    assert error.value.code == "DOCUMENT_NOT_READY"
    assert FamilyPublication.objects.count() == 1


def test_notifications_are_separate_from_acknowledgement_and_generic_after_suspend(family_env):
    env = family_env
    warning = make_warning(env)
    response = env["client"].get("/api/v1/parent/notifications/")
    assert response.status_code == 200
    row = next(row for row in response.json()["items"] if row["kind"] == "WARNING")
    assert post(env["client"], f"/api/v1/parent/notifications/{row['id']}/read/").status_code == 200
    assert not WarningAcknowledgement.objects.filter(warning=warning).exists()
    assert (
        post(
            env["client"], f"/api/v1/parent/notifications/{row['id']}/complete-action/"
        ).status_code
        == 409
    )
    assert not WarningAcknowledgement.objects.exists()
    assert (
        post(env["client"], f"{env['prefix']}/warnings/{warning.id}/acknowledge/").status_code
        == 200
    )
    assert (
        post(
            env["client"], f"/api/v1/parent/notifications/{row['id']}/complete-action/"
        ).status_code
        == 200
    )
    count = ParentNotification.objects.count()
    env["client"].get("/api/v1/parent/notifications/")
    assert ParentNotification.objects.count() == count
    warning.status = "VOIDED"
    warning.save(update_fields=["status"])
    warning_notice = next(
        item
        for item in env["client"]
        .get(
            "/api/v1/parent/notifications/",
        )
        .json()["items"]
        if item["kind"] == "WARNING"
    )
    assert warning_notice["requires_action"] is False
    assert warning_notice["state"] == "ACTION_COMPLETED"
    assert (
        post(
            env["client"], f"/api/v1/parent/notifications/{row['id']}/complete-action/"
        ).status_code
        == 404
    )
    env["relation"].status = "SUSPENDED_CONTACT_REVIEW"
    env["relation"].save(update_fields=["status"])
    ParentNotification.objects.create(
        school=env["school"],
        relation=env["relation"],
        user=env["user"],
        kind="RELATION_STATUS",
        dedup_key="contact:2",
        title="تحتاج العلاقة إلى مراجعة",
    )
    items = env["client"].get("/api/v1/parent/notifications/").json()["items"]
    assert len(items) == 1 and items[0]["kind"] == "RELATION_STATUS"
    assert env["client"].get("/api/v1/parent/requests/").json()["items"] == []


def test_parent_attachments_are_in_backup_inventory_and_purge(family_env):
    from operations.storage_integrity import _records
    from students.services.purge import purge_student

    env = family_env
    request_id = submit(env).json()["id"]
    response = env["client"].post(
        f"{env['prefix']}/excuses/{request_id}/attachments/",
        {
            "file": SimpleUploadedFile("proof.pdf", VALID_PDF, content_type="application/pdf"),
        },
    )
    assert response.status_code == 201
    attachment = ParentExcuseRequest.objects.get(id=request_id).attachments.first()
    storage, name = attachment.file.storage, attachment.file.name
    assert "parent_excuse_attachment" in {kind for kind, _, _ in _records()}
    assert storage.exists(name)
    student = env["relation"].student
    student.status = "INACTIVE"
    student.save(update_fields=["status"])
    deleted, objects_deleted, failures = purge_student(student)
    assert deleted > 0 and objects_deleted == 1 and failures == 0
    assert not storage.exists(name)
    assert not GuardianStudentRelation.objects.filter(id=env["relation"].id).exists()
    assert not FamilyPublication.objects.exists()


def test_counselor_publication_uses_own_case_and_never_exposes_internal_summary(
    family_env,
    make_user,
    make_membership,
):
    from counseling.models import CounselorCase
    from referrals.models import StudentReferral

    env = family_env
    counselor = make_membership(make_user("0551700061"), env["school"], ["COUNSELOR"])
    colleague = make_membership(make_user("0551700062"), env["school"], ["COUNSELOR"])
    referral = StudentReferral.objects.create(
        school=env["school"],
        student=env["relation"].student,
        source_type="VICE_PRINCIPAL",
        category="ATTENDANCE",
        reason_code="REPEATED_ABSENCE",
        created_by_membership=env["vice"],
        assigned_vice_membership=env["vice"],
        assigned_counselor_membership=counselor,
        status="REFERRED",
    )
    case = CounselorCase.objects.create(
        school=env["school"],
        student=env["relation"].student,
        primary_referral=referral,
        assigned_counselor_membership=counselor,
        opened_by_membership=counselor,
        opened_at=timezone.now(),
        last_activity_at=timezone.now(),
        summary="INTERNAL_PRIVATE_SUMMARY",
    )
    clients = []
    for member in (counselor, colleague):
        client = Client()
        client.force_login(member.user)
        session = client.session
        session["active_school_id"] = env["school"].id
        session.save()
        clients.append(client)
    payload = {
        "student_id": env["relation"].student_id,
        "case_id": case.id,
        "title": "توصية للأسرة",
        "body": "النص المعتمد للنشر فقط",
    }
    assert post(clients[1], "/api/v1/staff/parents/publications/", payload).status_code == 403
    response = post(clients[0], "/api/v1/staff/parents/publications/", payload)
    assert response.status_code == 201
    publication_id = response.json()["id"]
    parent_payload = env["client"].get(f"{env['prefix']}/publications/").json()
    assert "INTERNAL_PRIVATE_SUMMARY" not in str(parent_payload)
    assert parent_payload["items"][0]["body"] == "النص المعتمد للنشر فقط"
    assert clients[1].get("/api/v1/staff/parents/publications/").json()["items"] == []
    stale_case = CounselorCase.objects.get(id=case.id)
    stale_publication = FamilyPublication.objects.select_related("case").get(id=publication_id)
    case.assigned_counselor_membership = colleague
    case.save(update_fields=["assigned_counselor_membership"])
    with tenant_context(school_id=env["school"].id, user_id=counselor.user_id):
        with pytest.raises(ApiError) as error:
            request_services.publish_family(
                school=env["school"],
                membership=counselor,
                student=env["relation"].student,
                title="تعليمات قديمة",
                body="",
                case=stale_case,
            )
        assert error.value.status_code == 403
        with pytest.raises(ApiError) as error:
            request_services.revoke_publication(
                publication=stale_publication,
                membership=counselor,
                reason="صلاحية سابقة",
            )
        assert error.value.status_code == 404
    assert FamilyPublication.objects.count() == 1
    assert (
        post(
            clients[0],
            f"/api/v1/staff/parents/publications/{publication_id}/revoke/",
            {"reason": "نقل مسؤولية الحالة"},
        ).status_code
        == 404
    )


def test_direct_parent_services_recheck_suspended_relation(family_env):
    env = family_env
    stale_relation = env["relation"]
    GuardianStudentRelation.objects.filter(id=stale_relation.id).update(status="REVOKED")
    assert stale_relation.status == "ACTIVE"
    with pytest.raises(ApiError) as error:
        request_services.submit_excuse(
            relation=stale_relation,
            user=env["user"],
            reason_type="MEDICAL_REPORT",
            notes="",
            targets=[{"attendance_date": DAY, "period_sequence": 1}],
        )
    assert error.value.status_code == 404
    with pytest.raises(ApiError) as error:
        request_services.submit_correction(
            relation=stale_relation,
            user=env["user"],
            session_id=env["session"].id,
            reason="مراجعة",
        )
    assert error.value.status_code == 404
    assert not ParentExcuseRequest.objects.exists()
    assert not stale_relation.correction_requests.exists()


def test_correction_review_rejects_absence_already_corrected(family_env):
    env = family_env
    response = post(
        env["client"],
        f"{env['prefix']}/corrections/",
        {"session_id": env["session"].id, "reason": "تحقق من الحضور"},
    )
    assert response.status_code == 201
    AttendanceMark.objects.filter(session=env["session"], student=env["relation"].student).delete()
    response = post(
        env["staff_client"],
        f"/api/v1/staff/parents/corrections/{response.json()['id']}/decision/",
        {"decision": "APPROVED", "note": "تحقق"},
    )
    assert response.status_code == 409
    assert response.json()["code"] == "PARENT_CORRECTION_NO_ABSENCE"
    assert not AttendanceChange.objects.exists()


def test_excuse_review_revalidates_stored_targets_after_absence_correction(family_env):
    env = family_env
    request_id = submit(env).json()["id"]
    AttendanceMark.objects.filter(session=env["session"], student=env["relation"].student).delete()
    response = approve(env, request_id)
    assert response.status_code == 400
    assert response.json()["code"] == "PARENT_EXCUSE_NO_ABSENCE"
    assert ParentExcuseRequest.objects.get(id=request_id).status == "PENDING"
    assert not AbsenceExcuse.objects.exists()
    assert not AbsenceExcuseCoverage.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_concurrent_parent_warning_acknowledgement_and_document_generation(family_env, monkeypatch):
    from documents.services import generation
    from parents import access

    env = family_env
    warning = make_warning(env)
    document = GeneratedDocument.objects.create(
        school=env["school"],
        student=env["relation"].student,
        warning=warning,
        document_type="WARNING_LEVEL_1",
        template_key="warning_level_1",
        template_version="v3",
        generated_by_membership=env["vice"],
    )
    monkeypatch.setattr(generation, "_render", lambda **kwargs: VALID_PDF)
    first_document_lock = Event()
    parent_school_lock = Event()
    school_lock = access.lock_parent_school

    def announce_parent_school(school_id):
        school_lock(school_id)
        parent_school_lock.set()

    monkeypatch.setattr(access, "lock_parent_school", announce_parent_school)

    def produce():
        close_old_connections()
        try:

            def after_first_lock(execute, sql, params, many, context):
                result = execute(sql, params, many, context)
                if "FOR UPDATE" in sql.upper() and not first_document_lock.is_set():
                    first_document_lock.set()
                    # With school-first ordering the parent correctly waits for
                    # this transaction. Warning-first ordering creates a cycle.
                    parent_school_lock.wait(timeout=0.5)
                return result

            with tenant_context(school_id=env["school"].id, user_id=env["vice"].user_id):
                with connection.execute_wrapper(after_first_lock):
                    return generation._produce_file(
                        document=document, membership=env["vice"]
                    ).status
        finally:
            connections.close_all()

    def acknowledge():
        close_old_connections()
        try:
            client = Client()
            client.force_login(env["user"])
            assert first_document_lock.wait(timeout=10)
            return post(client, f"{env['prefix']}/warnings/{warning.id}/acknowledge/").status_code
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        produced = pool.submit(produce)
        acknowledged = pool.submit(acknowledge)
        assert produced.result(timeout=20) == "READY"
        assert acknowledged.result(timeout=20) == 200
    document.refresh_from_db()
    assert document.file.storage.exists(document.file.name)
    assert document.status == "READY"
    assert WarningAcknowledgement.objects.filter(warning=warning).count() == 1


@pytest.mark.django_db(transaction=True)
def test_concurrent_attachments_for_two_children_serialize_storage_capacity(
    family_env, monkeypatch
):
    from parents import access
    from subscriptions import entitlements
    from subscriptions.usage import BYTES_PER_GB

    env = family_env
    first_request = ParentExcuseRequest.objects.get(id=submit(env).json()["id"])
    second_student = env["students"][1]
    mark(env, env["session"], second_student, "ABSENT")
    second_relation = GuardianStudentRelation.objects.create(
        school=env["school"],
        student=second_student,
        user=env["user"],
        status="ACTIVE",
        contact_bound=False,
        approved_by=env["vice"].user,
        approved_at=timezone.now(),
    )
    second_request = request_services.submit_excuse(
        relation=second_relation,
        user=env["user"],
        reason_type="MEDICAL_REPORT",
        notes="",
        targets=[{"attendance_date": DAY, "period_sequence": 1}],
    )
    original_limit = entitlements.get_limit
    monkeypatch.setattr(
        entitlements,
        "get_limit",
        lambda school, key: (
            len(VALID_PDF) / BYTES_PER_GB
            if key == "MAX_STORAGE_GB"
            else original_limit(school, key)
        ),
    )
    shared_locks = Barrier(2)
    original_school_lock = access.lock_parent_school

    def simultaneous_shared_lock(school_id):
        original_school_lock(school_id)
        shared_locks.wait(timeout=10)

    monkeypatch.setattr(access, "lock_parent_school", simultaneous_shared_lock)

    def upload(obj, relation):
        close_old_connections()
        try:
            try:
                request_services.upload_attachment(
                    obj=obj,
                    relation=relation,
                    user=env["user"],
                    uploaded_file=SimpleUploadedFile(
                        "proof.pdf", VALID_PDF, content_type="application/pdf"
                    ),
                )
                return "UPLOADED"
            except ApiError as error:
                return error.code
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(upload, first_request, env["relation"])
        second = pool.submit(upload, second_request, second_relation)
        assert sorted([first.result(timeout=20), second.result(timeout=20)]) == [
            "STORAGE_LIMIT_EXCEEDED",
            "UPLOADED",
        ]
    assert storage_used_bytes(env["school"]) == len(VALID_PDF)
    assert sum(obj.attachments.count() for obj in (first_request, second_request)) == 1


def test_multiple_school_relations_are_independent_and_foreign_ids_are_hidden(
    family_env,
    make_school,
    make_membership,
):
    env = family_env
    school = make_school("مدرسة الابن الثاني")
    teacher = make_membership(env["teacher"].user, school, ["TEACHER"])
    vice = make_membership(env["vice"].user, school, ["VICE_PRINCIPAL"])
    second = build_env(
        school=school, teacher_membership=teacher, vice_membership=vice, prefix="37200"
    )
    relation = GuardianStudentRelation.objects.create(
        school=school,
        student=second["students"][0],
        user=env["user"],
        status="ACTIVE",
        contact_bound=False,
        approved_by=vice.user,
        approved_at=timezone.now(),
    )
    session = make_session(second, 1)
    mark(second, session, relation.student, "ABSENT")
    foreign = post(
        env["client"],
        f"{env['prefix']}/corrections/",
        {"session_id": session.id, "reason": "مراجعة ابن آخر"},
    )
    assert foreign.status_code == 404
    assert submit(env).status_code == 201
    response = post(
        env["client"],
        f"/api/v1/parent/children/{relation.id}/corrections/",
        {"session_id": session.id, "reason": "مراجعة حضور الابن الثاني"},
    )
    assert response.status_code == 201
    items = env["client"].get("/api/v1/parent/requests/").json()["items"]
    assert {item["relation_id"] for item in items} == {relation.id, env["relation"].id}
    second_prefix = f"/api/v1/parent/children/{relation.id}"
    excuse_response = post(
        env["client"],
        f"{second_prefix}/excuses/",
        {
            "reason_type": "FAMILY",
            "notes": "عذر الابن الثاني",
            "targets": [{"attendance_date": DAY.isoformat(), "period_sequence": 1}],
        },
    )
    assert excuse_response.status_code == 201
    second_request_id = excuse_response.json()["id"]
    attachment_response = env["client"].post(
        f"{second_prefix}/excuses/{second_request_id}/attachments/",
        {
            "file": SimpleUploadedFile("second.pdf", VALID_PDF, content_type="application/pdf"),
        },
    )
    assert attachment_response.status_code == 201
    attachment_id = attachment_response.json()["id"]
    assert (
        env["client"]
        .get(
            f"{env['prefix']}/excuses/{second_request_id}/attachments/{attachment_id}/download/",
        )
        .status_code
        == 404
    )
    assert (
        post(env["client"], f"{env['prefix']}/excuses/{second_request_id}/cancel/").status_code
        == 404
    )
    assert approve(env, second_request_id).status_code == 404
    second_warning = StudentWarning.objects.create(
        school=school,
        student=relation.student,
        academic_year=second["year"],
        warning_type="UNEXCUSED_FULL_DAY_ABSENCE",
        level="LEVEL_1",
        status="ISSUED",
        threshold_at_issue=3,
        metric_value_at_issue=3,
        student_name_snapshot=relation.student.full_name,
        issued_by_membership=vice,
        issued_at=timezone.now(),
    )
    assert (
        post(
            env["client"], f"{env['prefix']}/warnings/{second_warning.id}/acknowledge/"
        ).status_code
        == 404
    )
    publication = FamilyPublication.objects.create(
        school=school,
        student=relation.student,
        title="مدرسة ثانية",
        body="نص مصرح",
        published_by_membership=vice,
        published_at=timezone.now(),
    )
    assert (
        env["client"].get(f"{env['prefix']}/publications/{publication.id}/download/").status_code
        == 404
    )
    env["relation"].status = "REVOKED"
    env["relation"].save(update_fields=["status"])
    items = env["client"].get("/api/v1/parent/requests/").json()["items"]
    assert len(items) == 2 and {item["relation_id"] for item in items} == {relation.id}
    assert (
        env["client"].get(f"/api/v1/parent/children/{relation.id}/publications/").status_code == 200
    )


def test_parent_private_attachment_backup_restore_round_trip(family_env, tmp_path):
    from operations.storage_integrity import backup_private_objects, restore_private_objects

    env = family_env
    request_id = submit(env).json()["id"]
    assert (
        env["client"]
        .post(
            f"{env['prefix']}/excuses/{request_id}/attachments/",
            {
                "file": SimpleUploadedFile("proof.pdf", VALID_PDF, content_type="application/pdf"),
            },
        )
        .status_code
        == 201
    )
    attachment = ParentExcuseRequest.objects.get(id=request_id).attachments.first()
    destination = tmp_path / "isolated-object-backup"
    run, manifest = backup_private_objects(destination)
    assert run.status == "SUCCEEDED" and manifest.exists()
    storage, name = attachment.file.storage, attachment.file.name
    storage.delete(name)
    assert restore_private_objects(destination) == {"restored": 1, "skipped": 0}
    with storage.open(name, "rb") as restored:
        assert restored.read() == VALID_PDF


def test_request_pagination_preserves_history_after_one_hundred_records(family_env):
    env = family_env
    ParentExcuseRequest.objects.bulk_create(
        [
            ParentExcuseRequest(
                school=env["school"],
                student=env["relation"].student,
                relation=env["relation"],
                requester=env["user"],
                status="REJECTED",
                reason_type="FAMILY",
                notes=f"سجل تاريخي {number}",
                targets=[],
                target_fingerprint=f"history-{number}",
            )
            for number in range(105)
        ]
    )
    first = env["client"].get(f"{env['prefix']}/excuses/?page_size=100").json()
    second = env["client"].get(f"{env['prefix']}/excuses/?page_size=100&page=2").json()
    assert first["count"] == second["count"] == 105
    assert len(first["items"]) == 100 and len(second["items"]) == 5
    assert first["next"] and second["previous"] and second["next"] is None
    assert {row["id"] for row in first["items"]}.isdisjoint({row["id"] for row in second["items"]})
    aggregate = env["client"].get("/api/v1/parent/requests/?page_size=100&page=2").json()
    assert aggregate["count"] == 105 and len(aggregate["items"]) == 5
    staff = env["staff_client"].get("/api/v1/staff/parents/requests/?page_size=100&page=2").json()
    assert staff["count"] == 105 and len(staff["excuses"]) == 5
    assert env["client"].get("/api/v1/parent/requests/?page=1001").status_code == 400
    assert env["client"].get(f"{env['prefix']}/excuses/?page_size=101").status_code == 400


def test_aggregate_subscription_blocked_hides_sensitive_content(family_env, monkeypatch):
    env = family_env
    assert submit(env).status_code == 201
    ParentNotification.objects.create(
        school=env["school"],
        relation=env["relation"],
        user=env["user"],
        kind="EXCUSE",
        dedup_key="secret",
        title="PRIVATE_STUDENT_DATA",
        body="PRIVATE_MEDICAL_DATA",
    )
    ParentNotification.objects.create(
        school=env["school"],
        relation=env["relation"],
        user=env["user"],
        kind="RELATION_STATUS",
        dedup_key="generic",
        title="العلاقة تحتاج مراجعة",
    )
    monkeypatch.setattr("parents.access.get_school_access_mode", lambda school: "BLOCKED")
    requests = env["client"].get("/api/v1/parent/requests/").json()
    notices = env["client"].get("/api/v1/parent/notifications/").json()
    assert requests["count"] == 0 and requests["items"] == []
    assert notices["count"] == 1 and notices["items"][0]["kind"] == "RELATION_STATUS"
    assert "PRIVATE_" not in str(notices)


def test_notifications_include_owned_child_context_and_relation_filter(family_env):
    env = family_env
    second_relation = GuardianStudentRelation.objects.create(
        school=env["school"],
        student=env["students"][1],
        user=env["user"],
        status="ACTIVE",
        contact_bound=False,
        approved_by=env["vice"].user,
        approved_at=timezone.now(),
    )
    for relation in (env["relation"], second_relation):
        ParentNotification.objects.create(
            school=env["school"],
            relation=relation,
            user=env["user"],
            kind="EXCUSE",
            dedup_key="context:test",
            title="طلب يحتاج المتابعة",
        )
    response = env["client"].get(f"/api/v1/parent/notifications/?relation_id={second_relation.id}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    notice = payload["items"][0]
    assert notice["relation_id"] == second_relation.id
    assert notice["student_name"] == second_relation.student.full_name
    assert notice["school_name"] == env["school"].name
    read = post(env["client"], f"/api/v1/parent/notifications/{notice['id']}/read/")
    assert read.json()["student_name"] == second_relation.student.full_name
    second_relation.status = "SUSPENDED_CONTACT_REVIEW"
    second_relation.save(update_fields=["status"])
    ParentNotification.objects.create(
        school=env["school"],
        relation=second_relation,
        user=env["user"],
        kind="RELATION_STATUS",
        dedup_key="context:generic",
        title="العلاقة تحتاج مراجعة",
    )
    generic = (
        env["client"].get(f"/api/v1/parent/notifications/?relation_id={second_relation.id}").json()
    )
    assert generic["count"] == 1
    assert generic["items"][0]["student_name"] is None
    assert generic["items"][0]["school_name"] is None


def test_notification_relation_filter_does_not_confirm_foreign_relation(family_env, make_user):
    env = family_env
    other_user = make_user("0551700071")
    foreign_relation = GuardianStudentRelation.objects.create(
        school=env["school"],
        student=env["students"][1],
        user=other_user,
        status="ACTIVE",
        contact_bound=False,
        approved_by=env["vice"].user,
        approved_at=timezone.now(),
    )
    ParentNotification.objects.create(
        school=env["school"],
        relation=foreign_relation,
        user=other_user,
        kind="EXCUSE",
        dedup_key="foreign",
        title="PRIVATE_FOREIGN_NOTICE",
    )
    for relation_id in (foreign_relation.id, 999999999):
        response = env["client"].get(f"/api/v1/parent/notifications/?relation_id={relation_id}")
        assert response.status_code == 200
        assert response.json() == {"count": 0, "items": [], "next": None, "previous": None}
    assert env["client"].get("/api/v1/parent/notifications/?relation_id=invalid").status_code == 400


def test_staff_acknowledgements_are_paginated_masked_and_school_scoped(
    family_env, make_school, make_user, make_membership
):
    env = family_env
    warning = make_warning(env)
    assert (
        post(env["client"], f"{env['prefix']}/warnings/{warning.id}/acknowledge/").status_code
        == 200
    )
    publication_id = post(
        env["staff_client"],
        "/api/v1/staff/parents/publications/",
        {"student_id": env["relation"].student_id, "title": "محتوى منشور"},
    ).json()["id"]
    assert (
        post(
            env["client"], f"{env['prefix']}/publications/{publication_id}/acknowledge/"
        ).status_code
        == 200
    )
    other_school = make_school("مدرسة مستقلة")
    other_teacher = make_membership(make_user("0551700072"), other_school, ["TEACHER"])
    other_vice = make_membership(make_user("0551700073"), other_school, ["VICE_PRINCIPAL"])
    other = build_env(
        school=other_school,
        teacher_membership=other_teacher,
        vice_membership=other_vice,
        prefix="37300",
    )
    other_relation = GuardianStudentRelation.objects.create(
        school=other_school,
        student=other["students"][0],
        user=env["user"],
        status="ACTIVE",
        contact_bound=False,
        approved_by=other_vice.user,
        approved_at=timezone.now(),
    )
    other["relation"] = other_relation
    other_warning = make_warning(other)
    WarningAcknowledgement.objects.create(
        school=other_school,
        relation=other_relation,
        user=env["user"],
        warning=other_warning,
        acknowledged_at=timezone.now(),
    )
    url = "/api/v1/staff/parents/acknowledgements/?page_size=1"
    first = env["staff_client"].get(url).json()
    second = env["staff_client"].get(f"{url}&page=2").json()
    assert first["count"] == second["count"] == 2
    assert first["next"] and second["previous"]
    items = first["items"] + second["items"]
    assert {item["type"] for item in items} == {"WARNING", "PUBLICATION"}
    assert {item["relation_id"] for item in items} == {env["relation"].id}
    assert {item["target_id"] for item in items} == {warning.id, publication_id}
    assert env["user"].mobile not in str(items)
    assert all(item["parent_name"].endswith(env["user"].mobile[-4:]) for item in items)
    assert env["client"].get(url).status_code == 403
    teacher_client = Client()
    teacher_client.force_login(env["teacher"].user)
    session = teacher_client.session
    session["active_school_id"] = env["school"].id
    session.save()
    assert teacher_client.get(url).status_code == 403


def test_family_openapi_and_response_contracts_are_explicit(family_env):
    from drf_spectacular.generators import SchemaGenerator

    from parents.request_serializers import (
        ExcuseOutputSerializer,
        NotificationOutputSerializer,
        PublicationOutputSerializer,
        WarningOutputSerializer,
    )

    env = family_env
    response = submit(env)
    serializer = ExcuseOutputSerializer(data=response.json())
    assert serializer.is_valid(), serializer.errors
    publication = post(
        env["staff_client"],
        "/api/v1/staff/parents/publications/",
        {"student_id": env["relation"].student_id, "title": "نص نشر اختياري"},
    )
    serializer = PublicationOutputSerializer(data=publication.json())
    assert serializer.is_valid(), serializer.errors
    warning = make_warning(env)
    warning.status = "VOIDED"
    warning.save(update_fields=["status"])
    warning_payload = env["client"].get(f"{env['prefix']}/warnings/").json()["items"][0]
    serializer = WarningOutputSerializer(data=warning_payload)
    assert serializer.is_valid(), serializer.errors
    notice = env["client"].get("/api/v1/parent/notifications/").json()["items"][0]
    serializer = NotificationOutputSerializer(data=notice)
    assert serializer.is_valid(), serializer.errors
    schema = SchemaGenerator().get_schema(request=None, public=True)
    components = schema["components"]["schemas"]
    for name in (
        "ExcuseOutput",
        "CorrectionOutput",
        "PublicationOutput",
        "WarningOutput",
        "NotificationOutput",
    ):
        assert "properties" in components[name]
    excuse_properties = components["ExcuseOutput"]["properties"]
    assert {"targets", "attachments", "status", "relation_id"} <= set(excuse_properties)
    assert {
        "file",
        "school",
        "requester",
        "national_id",
        "guardian_mobile",
        "snapshot_data",
    }.isdisjoint(excuse_properties)
    aggregate_response = schema["paths"]["/api/v1/parent/requests/"]["get"]["responses"]["200"][
        "content"
    ]["application/json"]["schema"]
    assert aggregate_response["$ref"].endswith("/ParentRequestsPageOutput")
    assert "oneOf" in components["ParentRequestItem"]


def test_family_post_rate_limit_is_per_account_and_get_does_not_consume(family_env, monkeypatch):
    env = family_env
    monkeypatch.setattr("parents.request_api.FAMILY_WRITE_LIMIT", 1)
    assert env["client"].get(f"{env['prefix']}/excuses/").status_code == 200
    assert submit(env).status_code == 201
    response = submit(env)
    assert response.status_code == 429 and response.json()["code"] == "RATE_LIMITED"
    assert env["client"].get(f"{env['prefix']}/excuses/").status_code == 200
