"""End-to-end HTTP isolation using the application's real PostgreSQL policy role."""

from uuid import uuid4

import pytest
from django.core.files.base import ContentFile
from django.db import connection
from django.test import override_settings
from django.utils import timezone

from common.tenant_rls import clear_tenant_context
from documents.models import GeneratedDocument
from parents.models import (
    FamilyPublication,
    GuardianStudentRelation,
    ParentExcuseAttachment,
    ParentExcuseRequest,
)
from tests import test_parent_requests as family_helpers
from tests.excuse_env import build_env

VALID_PDF = family_helpers.VALID_PDF
family_env = family_helpers.family_env


@pytest.mark.django_db(transaction=True)
def test_parent_http_nobypass_role_denies_foreign_children_and_existing_private_files(
    family_env,
    make_school,
    make_user,
    make_membership,
):
    env = family_env
    school_b = make_school("مدرسة أخرى")
    staff_b = make_membership(make_user("0551700101"), school_b, ["VICE_PRINCIPAL"])
    teacher_b = make_membership(make_user("0551700102"), school_b, ["TEACHER"])
    other = build_env(
        school=school_b,
        teacher_membership=teacher_b,
        vice_membership=staff_b,
        prefix="37101",
    )
    foreign_parent = make_user("0551700103")
    foreign_student = other["students"][0]
    foreign_relation = GuardianStudentRelation.objects.create(
        school=school_b,
        student=foreign_student,
        user=foreign_parent,
        status="ACTIVE",
        contact_bound=False,
        approved_by=staff_b.user,
        approved_at=timezone.now(),
    )
    document = GeneratedDocument.objects.create(
        school=school_b,
        student=foreign_student,
        document_type="STUDENT_ATTENDANCE_REPORT",
        template_key="test",
        template_version="1",
        snapshot_data={},
        status="READY",
        generated_by_membership=staff_b,
        file=ContentFile(VALID_PDF, name="private.pdf"),
    )
    publication = FamilyPublication.objects.create(
        school=school_b,
        student=foreign_student,
        document=document,
        title="مستند خاص",
        body="محتوى مدرسة أخرى",
        published_by_membership=staff_b,
        published_at=timezone.now(),
    )
    excuse = ParentExcuseRequest.objects.create(
        school=school_b,
        student=foreign_student,
        relation=foreign_relation,
        requester=foreign_parent,
        reason_type="OTHER",
        targets=[],
        target_fingerprint="x" * 64,
    )
    attachment = ParentExcuseAttachment.objects.create(
        school=school_b,
        parent_request=excuse,
        uploaded_by=foreign_parent,
        file=ContentFile(VALID_PDF, name="private.pdf"),
        original_filename="private.pdf",
        mime_type="application/pdf",
        size_bytes=len(VALID_PDF),
        checksum="c" * 64,
    )
    role = connection.ops.quote_name(f"parent_http_rls_{uuid4().hex}")
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"CREATE ROLE {role} NOSUPERUSER NOBYPASSRLS")
            cursor.execute(f"GRANT USAGE ON SCHEMA public TO {role}")
            cursor.execute(
                f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {role}"
            )
            cursor.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {role}")
            cursor.execute(f"SET ROLE {role}")
        clear_tenant_context()
        with override_settings(DATABASE_RLS_ENFORCED=True):
            account = env["client"].get("/api/v1/auth/me/")
            assert account.status_code == 200
            assert account.json()["has_parent_portal"] is True
            assert account.json()["memberships"] == []
            child = env["client"].get(f"{env['prefix']}/")
            assert child.status_code == 200
            assert child.json()["child"]["student"]["id"] == env["relation"].student_id
            forbidden = [
                f"/api/v1/parent/children/{foreign_relation.id}/",
                f"{env['prefix']}/publications/{publication.id}/download/",
                f"{env['prefix']}/excuses/{excuse.id}/attachments/{attachment.id}/download/",
                f"/api/v1/parent/children/{foreign_relation.id}/excuses/{excuse.id}/"
                f"attachments/{attachment.id}/download/",
            ]
            for path in forbidden:
                response = env["client"].get(path)
                assert response.status_code == 404, (path, response.content)
                assert foreign_student.full_name.encode() not in response.content
                assert VALID_PDF not in response.content
    finally:
        with connection.cursor() as cursor:
            cursor.execute("RESET ROLE")
            cursor.execute(f"DROP OWNED BY {role}")
            cursor.execute(f"DROP ROLE IF EXISTS {role}")
        clear_tenant_context()
