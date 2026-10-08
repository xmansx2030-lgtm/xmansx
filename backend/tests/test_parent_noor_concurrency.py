"""A real Noor commit racing a school review never restores an obsolete grant."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from time import perf_counter

import pytest
from django.db import close_old_connections, connections
from django.test import Client

from common.tenant_rls import tenant_context
from parents.models import GuardianContactReview
from students.models import ImportJobStatus, StudentImportJob, StudentImportRow
from students.services.imports.commit import commit_import
from students.services.imports.comparison import categorize_rows
from tests import test_parent_portal as journeys

portal_env = journeys.portal_env


@pytest.mark.django_db(transaction=True)
def test_concurrent_real_noor_commit_and_relation_review_preserves_contact_suspension(portal_env):
    env = portal_env
    relation, _, _ = journeys.activate(env)
    student = env["student"]
    student.refresh_from_db()
    old_revision = student.guardian_contact_revision
    row = {
        "row_number": 2,
        "national_id_encrypted": student.national_id_encrypted,
        "national_id_hash": student.national_id_lookup_hash,
        "national_id_masked": student.national_id_masked,
        "student_number": student.student_number,
        "full_name": student.full_name,
        "guardian_name": student.guardian_name,
        "guardian_mobile": "+966551900009",
        "grade_code": env["grade"].code,
        "grade_name": env["grade"].name,
        "grade_sequence": env["grade"].sequence,
        "section_code": env["section"].code,
        "section_name": env["section"].name,
        "department": env["section"].department,
        "errors": [],
    }
    preview = categorize_rows(env["school"], env["year"], [row])
    assert preview["summary"]["updated"] == 1
    staged = preview["rows"][0]
    job = StudentImportJob.objects.create(
        school=env["school"], academic_year=env["year"], uploaded_by=env["actor"],
        original_filename="parent-noor-race.xlsx", status=ImportJobStatus.READY_FOR_REVIEW,
    )
    StudentImportRow.objects.create(
        job=job, row_number=staged["row_number"], status=staged["status"],
        national_id_encrypted=staged["national_id_encrypted"],
        national_id_hash=staged["national_id_hash"],
        data={key: value for key, value in staged.items()
              if key not in {"national_id_encrypted", "national_id_hash", "errors", "row_number"}},
    )
    barrier = Barrier(2)

    def import_noor():
        close_old_connections()
        try:
            with tenant_context(school_id=env["school"].id, user_id=env["actor"].id):
                barrier.wait(timeout=15)
                return commit_import(job_id=job.id, actor=env["actor"]).status
        finally:
            connections.close_all()

    def review_relation():
        close_old_connections()
        try:
            client = Client()
            client.force_login(env["actor"])
            session = client.session
            session["active_school_id"] = env["school"].id
            session.save()
            barrier.wait(timeout=15)
            return journeys.post(
                client, f"/api/v1/staff/parents/relations/{relation.id}/decision/",
                {"status": "ACTIVE", "contact_bound": True,
                 "reason": "إعادة تحقق متزامنة مع نور",
                 "verification_note": "تحقق موثق من الرقم الحالي"},
            ).status_code
        finally:
            connections.close_all()

    started = perf_counter()
    with ThreadPoolExecutor(max_workers=2) as pool:
        imported, reviewed = pool.submit(import_noor), pool.submit(review_relation)
        assert imported.result(timeout=30) == ImportJobStatus.COMPLETED
        assert reviewed.result(timeout=30) in {200, 400}
    student.refresh_from_db()
    relation.refresh_from_db()
    job.refresh_from_db()
    assert student.guardian_mobile == "+966551900009"
    assert student.guardian_contact_revision == old_revision + 1
    assert relation.status == "SUSPENDED_CONTACT_REVIEW"
    assert relation.contact_revision == old_revision
    assert job.status == ImportJobStatus.COMPLETED
    assert GuardianContactReview.objects.filter(student=student, source="NOOR_IMPORT").count() == 1
    assert env["parent"].get(f"/api/v1/parent/children/{relation.id}/").status_code == 404
    elapsed_ms = (perf_counter() - started) * 1000
    print(f"parent workload:real Noor commit vs relation review;ms={elapsed_ms:.2f}")
