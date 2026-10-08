"""PostgreSQL enforcement, direct writes, rollback, and independent account boundaries."""

from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from django.contrib.admin.sites import AdminSite
from django.db import DatabaseError, connection, transaction
from django.utils import timezone

from accounts.models import User
from common.tenant_rls import clear_tenant_context, tenant_context
from parents.models import (
    GuardianActivation,
    GuardianContactReview,
    GuardianRegistrationRequest,
    GuardianStudentRelation,
    ParentExcuseRequest,
    ParentNotification,
    RecipientContactBlock,
)
from parents.security import contact_hash, token_hash
from students.admin import StudentAdmin
from students.models import Student
from students.services.imports.comparison import categorize_rows
from students.services.imports.normalization import normalize_guardian_mobile


def _student(school, suffix="a", mobile="+966550010001"):
    return Student.objects.create(
        school=school,
        full_name="طالب الاختبار",
        guardian_name="ولي الطالب",
        guardian_mobile=mobile,
        national_id_encrypted=f"encrypted-{suffix}",
        national_id_lookup_hash=suffix * 64,
        national_id_masked="******1234",
    )


def _relation(student, user, approver, *, bound=True):
    return GuardianStudentRelation.objects.create(
        school=student.school,
        student=student,
        user=user,
        status="ACTIVE",
        approved_by=approver,
        approved_at=timezone.now(),
        contact_bound=bound,
        contact_revision=student.guardian_contact_revision,
        approved_contact_hash=contact_hash(student.guardian_mobile),
    )


def _activation(student, approver):
    request = GuardianRegistrationRequest.objects.create(
        school=student.school,
        student=student,
        name="ولي الاختبار",
        mobile_encrypted="protected",
        mobile_hash="m" * 64,
        mobile_masked="+9665****0001",
        identifier_encrypted="protected",
        identifier_hash=student.national_id_lookup_hash,
        receipt_hash=token_hash(uuid4().hex),
        status="APPROVED",
        approved_by=approver,
        approved_at=timezone.now(),
        contact_revision=1,
    )
    activation = GuardianActivation.objects.create(
        school=student.school,
        student=student,
        request=request,
        token_hash=token_hash(uuid4().hex),
        contact_revision=1,
        expires_at=timezone.now() + timedelta(hours=24),
    )
    return request, activation


@pytest.mark.django_db
@pytest.mark.parametrize("write", ["save", "update", "bulk_update", "sql", "admin"])
def test_all_contact_writes_suspend_only_bound_relation_and_revoke_activation(
    make_school,
    make_user,
    write,
):
    school = make_school()
    parent = make_user("0550010001")
    independent = make_user("0550010002")
    approver = make_user("0550010003", is_superuser=write == "admin")
    student = _student(school)
    sibling = _student(school, "b")
    bound = _relation(student, parent, approver)
    other = _relation(student, independent, approver, bound=False)
    sibling_relation = _relation(sibling, parent, approver)
    request, activation = _activation(student, approver)
    student.guardian_mobile = "+966550019999"
    if write == "save":
        student.save(update_fields=["guardian_mobile"])
    elif write == "update":
        Student.objects.filter(pk=student.pk).update(guardian_mobile=student.guardian_mobile)
    elif write == "bulk_update":
        Student.objects.bulk_update([student], ["guardian_mobile"])
    elif write == "sql":
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE students_student SET guardian_mobile=%s WHERE id=%s",
                [student.guardian_mobile, student.id],
            )
    else:
        admin = StudentAdmin(Student, AdminSite())
        form = SimpleNamespace(
            cleaned_data={
                "contact_change_reason": "تحقق حضوري موثق",
                "contact_identity_verified": True,
                "contact_verification_note": "فحصت المدرسة وثائق صاحب الصفة",
            }
        )
        admin.save_model(SimpleNamespace(user=approver), student, form, True)
    student.refresh_from_db()
    bound.refresh_from_db()
    other.refresh_from_db()
    sibling_relation.refresh_from_db()
    request.refresh_from_db()
    activation.refresh_from_db()
    parent.refresh_from_db()
    assert student.guardian_contact_revision == 2
    assert bound.status == "SUSPENDED_CONTACT_REVIEW"
    assert other.status == sibling_relation.status == "ACTIVE"
    assert request.status == "NEEDS_INFO"
    assert activation.revoked_at is not None
    assert parent.mobile == "+966550010001"
    assert GuardianContactReview.objects.filter(student=student).count() == 1
    assert ParentNotification.objects.filter(relation=bound, kind="RELATION_STATUS").count() == 1
    # Returning the old contact remains suspended until a new explicit approval.
    Student.objects.filter(pk=student.pk).update(guardian_mobile="+966550010001")
    bound.refresh_from_db()
    assert bound.status == "SUSPENDED_CONTACT_REVIEW"


@pytest.mark.django_db
@pytest.mark.parametrize("mobile", ["0550010001", "٠٥٥٠٠١٠٠٠١", "00966550010001", "+966550010001"])
def test_same_normalized_contact_does_not_change_revision(make_school, make_user, mobile):
    student = _student(make_school())
    user = make_user("0550010001")
    relation = _relation(student, user, user)
    Student.objects.filter(pk=student.pk).update(
        guardian_mobile=mobile, guardian_name="  ولي   الطالب  ", guardian_contact_revision=77
    )
    student.refresh_from_db()
    relation.refresh_from_db()
    assert student.guardian_contact_revision == 1
    assert relation.status == "ACTIVE"
    assert GuardianContactReview.objects.filter(student=student).count() == 0


@pytest.mark.django_db
@pytest.mark.parametrize(
    "change",
    [{"guardian_mobile": ""}, {"guardian_mobile": "invalid"}, {"guardian_name": "شخص آخر"}],
)
def test_manual_clear_invalid_direct_write_and_substantial_name_require_review(
    make_school,
    make_user,
    change,
):
    student = _student(make_school())
    user = make_user("0550010001")
    relation = _relation(student, user, user)
    Student.objects.filter(pk=student.pk).update(**change)
    relation.refresh_from_db()
    student.refresh_from_db()
    assert relation.status == "SUSPENDED_CONTACT_REVIEW"
    assert student.guardian_contact_revision == 2


@pytest.mark.django_db
def test_contact_update_rollback_restores_all_security_state(make_school, make_user):
    student = _student(make_school())
    user = make_user("0550010001")
    relation = _relation(student, user, user)
    request, activation = _activation(student, user)
    with pytest.raises(RuntimeError, match="import failure"):
        with transaction.atomic():
            Student.objects.filter(pk=student.pk).update(guardian_mobile="+966550019999")
            raise RuntimeError("import failure")
    student.refresh_from_db()
    relation.refresh_from_db()
    request.refresh_from_db()
    activation.refresh_from_db()
    assert student.guardian_contact_revision == 1
    assert relation.status == "ACTIVE"
    assert request.status == "APPROVED"
    assert activation.revoked_at is None
    assert not GuardianContactReview.objects.filter(student=student).exists()
    assert not ParentNotification.objects.filter(relation=relation).exists()


@pytest.mark.django_db
@pytest.mark.parametrize("imported", ["", "invalid", "0550010001"])
def test_noor_blank_invalid_and_equivalent_contact_preserve_previous(make_school, imported):
    school = make_school()
    student = _student(school)
    row = {
        "national_id_hash": student.national_id_lookup_hash,
        "student_number": None,
        "errors": [],
        "full_name": student.full_name,
        "guardian_name": "",
        "guardian_mobile": normalize_guardian_mobile(imported),
        "grade_code": "G1",
        "grade_name": "أول",
        "grade_sequence": 1,
        "section_code": "1",
        "section_name": "1",
        "department": "",
    }
    result = categorize_rows(school, None, [row])
    assert "guardian_mobile" not in result["rows"][0]["changes"]
    student.refresh_from_db()
    assert student.guardian_mobile == "+966550010001"
    assert student.guardian_contact_revision == 1


@pytest.mark.django_db
def test_database_rejects_stale_relation_reapproval(make_school, make_user):
    student = _student(make_school())
    user = make_user("0550010001")
    relation = _relation(student, user, user)
    Student.objects.filter(pk=student.pk).update(guardian_mobile="+966550019999")
    with pytest.raises(DatabaseError, match="requires current school approval"):
        with transaction.atomic():
            GuardianStudentRelation.objects.filter(pk=relation.pk).update(status="ACTIVE")


@pytest.mark.django_db(transaction=True)
def test_non_bypass_postgres_role_enforces_parent_index_contact_change_and_global_identity(
    make_school,
    make_user,
    make_membership,
):
    school_a = make_school("أ")
    school_b = make_school("ب")
    parent = make_user("0550010001")
    reviewer = make_user("0550010002")
    student_a = _student(school_a)
    student_b = _student(school_b, "b")
    relation_a = _relation(student_a, parent, reviewer)
    relation_b = _relation(student_b, parent, reviewer)
    teacher_membership = make_membership(parent, school_a, ["TEACHER"])
    role = connection.ops.quote_name(f"parent_rls_{uuid4().hex}")
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
        assert GuardianStudentRelation.objects.count() == 0
        assert Student.objects.count() == 0
        with tenant_context(user_id=parent.id):
            assert set(GuardianStudentRelation.objects.values_list("id", flat=True)) == {
                relation_a.id,
                relation_b.id,
            }
            assert Student.objects.count() == 0
        with tenant_context(school_id=school_a.id, user_id=reviewer.id):
            assert not Student.objects.filter(pk=student_b.pk).exists()
            Student.objects.filter(pk=student_a.pk).update(guardian_mobile="+966550019999")
            assert (
                GuardianStudentRelation.objects.get(pk=relation_a.pk).status
                == "SUSPENDED_CONTACT_REVIEW"
            )
            assert GuardianContactReview.objects.filter(student=student_a).count() == 1
            # Subject has relationships at another school: scope cannot hide the lock.
            with pytest.raises(DatabaseError, match="independent verification"):
                with transaction.atomic():
                    User.objects.filter(pk=parent.pk).update(mobile="+966550018888")
            assert User.objects.get(pk=parent.pk).mobile == "+966550010001"
            from common.errors import ApiError
            from staff.services.management import reset_teacher_password

            original_password = User.objects.get(pk=parent.pk).password
            with pytest.raises(ApiError) as denied:
                reset_teacher_password(membership=teacher_membership, actor=reviewer)
            assert denied.value.code == "GUARDIAN_ACCOUNT_PASSWORD_RESET_NOT_ALLOWED"
            assert User.objects.get(pk=parent.pk).password == original_password
            with pytest.raises(DatabaseError, match="cross-school foreign key rejected"):
                with transaction.atomic():
                    RecipientContactBlock.objects.create(
                        school=school_a,
                        student=student_b,
                        mobile_hash="x" * 64,
                        reason="موثوقية المستلم",
                        verification_note="تم التحقق",
                        created_by=reviewer,
                    )
    finally:
        with connection.cursor() as cursor:
            cursor.execute("RESET ROLE")
            cursor.execute(f"DROP OWNED BY {role}")
            cursor.execute(f"DROP ROLE IF EXISTS {role}")
        clear_tenant_context()


@pytest.mark.django_db
def test_contact_staff_endpoint_requires_proof_and_does_not_change_global_account(role_client):
    client, school, staff = role_client(["VICE_PRINCIPAL"])
    student = _student(school)
    _relation(student, staff, staff)
    url = f"/api/v1/staff/parents/students/{student.id}/contact/"
    assert (
        client.post(
            url, {"guardian_mobile": "0550019999"}, content_type="application/json"
        ).status_code
        == 400
    )
    response = client.post(
        url,
        {
            "guardian_mobile": "0550019999",
            "reason": "تحقق حضوري موثق",
            "verification_note": "فحصت المدرسة وثائق صاحب الصفة",
            "identity_verified": True,
        },
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json()["contact_revision"] == 2
    staff.refresh_from_db()
    assert staff.mobile != "+966550019999"
    review = GuardianContactReview.objects.get(student=student)
    same_contact = client.post(
        url,
        {
            "guardian_mobile": "+966550019999",
            "reason": "تأكيد رقم التواصل نفسه",
            "verification_note": "توثيق لاحق لا يستبدل إثبات التغيير السابق",
            "identity_verified": True,
        },
        content_type="application/json",
    )
    assert same_contact.status_code == 200
    assert same_contact.json()["contact_revision"] == 2
    assert same_contact.json()["review_id"] is None
    review.refresh_from_db()
    assert review.verification_note == "فحصت المدرسة وثائق صاحب الصفة"


@pytest.mark.django_db
def test_teacher_cannot_change_school_contact(role_client):
    client, school, _ = role_client(["TEACHER"])
    student = _student(school)
    response = client.post(
        f"/api/v1/staff/parents/students/{student.id}/contact/",
        {
            "guardian_mobile": "0550019999",
            "reason": "تحقق حضوري موثق",
            "verification_note": "فحصت المدرسة وثائق صاحب الصفة",
            "identity_verified": True,
        },
        content_type="application/json",
    )
    assert response.status_code == 403


@pytest.mark.django_db
@pytest.mark.parametrize("mismatch", ["student", "requester", "notification"])
def test_database_rejects_same_school_family_identity_mismatch(
    make_school,
    make_user,
    mismatch,
):
    school = make_school()
    parent = make_user("0550010001")
    other = make_user("0550010002")
    student = _student(school)
    sibling = _student(school, "b")
    relation = _relation(student, parent, parent)
    with pytest.raises(DatabaseError, match="parent relation identity mismatch"):
        with transaction.atomic():
            if mismatch == "notification":
                ParentNotification.objects.create(
                    school=school,
                    relation=relation,
                    user=other,
                    kind="RELATION_STATUS",
                    dedup_key="test-mismatch",
                    title="حالة العلاقة",
                )
            else:
                ParentExcuseRequest.objects.create(
                    school=school,
                    student=sibling if mismatch == "student" else student,
                    relation=relation,
                    requester=other if mismatch == "requester" else parent,
                    reason_type="OTHER",
                    targets=[],
                    target_fingerprint="f" * 64,
                )


@pytest.mark.django_db
def test_platform_password_reset_cannot_replace_independent_global_parent_ownership_proof(
    make_school,
    make_user,
    make_membership,
):
    from common.errors import ApiError
    from subscriptions.services.school_accounts import reset_manager_password

    school = make_school()
    parent = make_user("0550010001")
    platform = make_user("0550010002", is_superuser=True)
    membership = make_membership(parent, school, ["SCHOOL_MANAGER"])
    _relation(_student(school), parent, platform)
    original = parent.password
    with pytest.raises(ApiError) as denied:
        reset_manager_password(membership=membership, actor=platform)
    assert denied.value.code == "GUARDIAN_ACCOUNT_PASSWORD_RESET_NOT_ALLOWED"
    parent.refresh_from_db()
    assert parent.password == original
    with pytest.raises(ApiError) as confirmed_denial:
        reset_manager_password(
            membership=membership,
            actor=platform,
            confirm_shared_account_impact=True,
        )
    assert confirmed_denial.value.code == "GUARDIAN_ACCOUNT_PASSWORD_RESET_NOT_ALLOWED"
    parent.refresh_from_db()
    assert parent.password == original
    assert not parent.must_change_password
    assert GuardianStudentRelation.objects.filter(user=parent, status="ACTIVE").count() == 1


@pytest.mark.django_db
def test_all_contact_endpoints_have_explicit_openapi_contracts():
    from drf_spectacular.generators import SchemaGenerator

    schema = SchemaGenerator().get_schema(request=None, public=True)
    base = "/api/v1/staff/parents/"
    contracts = {
        "contact-reviews/": "get",
        "contact-reviews/{review_id}/resolve/": "post",
        "students/{student_id}/contact/": "post",
        "recipient-blocks/": "get",
        "students/{student_id}/recipient-blocks/": "post",
        "recipient-blocks/{block_id}/resolve/": "post",
        "global-mobile-changes/": "get",
        "students/{student_id}/global-mobile-change/": "post",
    }
    for suffix, method in contracts.items():
        operation = schema["paths"][base + suffix][method]
        responses = operation["responses"]
        assert any("content" in value for code, value in responses.items() if code.startswith("2"))
        if method == "post":
            assert operation["requestBody"]["content"]["application/json"]["schema"]


@pytest.mark.django_db
def test_admin_contact_form_exposes_proof_and_rejects_unverified_protected_change(
    make_school, make_user,
):
    from students.admin import StudentAdminForm

    student = _student(make_school())
    parent = make_user("0550010001")
    _relation(student, parent, parent)
    assert {
        "contact_change_reason", "contact_identity_verified", "contact_verification_note",
    } <= StudentAdminForm.base_fields.keys()
    form = StudentAdminForm(data={"guardian_mobile": "0550019999"}, instance=student)
    assert not form.is_valid()
    assert any("تحقق" in message for message in form.non_field_errors())
    student.refresh_from_db()
    assert student.guardian_contact_revision == 1


@pytest.mark.django_db
@pytest.mark.parametrize("kind", ["contact", "recipient"])
def test_resolution_preserves_initial_and_resolution_evidence_without_audit_pii(role_client, kind):
    from audit.models import AuditLog

    client, school, staff = role_client(["VICE_PRINCIPAL"])
    student = _student(school)
    initial = {"school": school, "student": student, "reason": "سبب أولي ثابت",
               "verification_note": "توثيق التحقق الأولي ثابت"}
    if kind == "contact":
        item = GuardianContactReview.objects.create(
            **initial, previous_revision=1, current_revision=2,
        )
        url = f"/api/v1/staff/parents/contact-reviews/{item.id}/resolve/"
        action = "PARENT_CONTACT_REVIEW_RESOLVED"
    else:
        item = RecipientContactBlock.objects.create(
            **initial, mobile_hash=contact_hash(student.guardian_mobile), created_by=staff,
        )
        url = f"/api/v1/staff/parents/recipient-blocks/{item.id}/resolve/"
        action = "PARENT_RECIPIENT_BLOCK_RESOLVED"
    resolution = {"reason": "سبب حل المراجعة مستقل", "identity_verified": True,
                  "verification_note": "إثبات هوية خاص +966550019999 لا يدخل التدقيق"}
    assert client.post(url, resolution, content_type="application/json").status_code == 200
    item.refresh_from_db()
    assert item.reason == initial["reason"]
    assert item.verification_note == initial["verification_note"]
    assert item.resolution_reason == resolution["reason"]
    assert item.resolution_verification_note == resolution["verification_note"]
    assert item.resolved_by_id == staff.id
    event = AuditLog.objects.get(action=action, target_id=str(item.id))
    assert event.metadata["resolution_documented"] is True
    assert "+966550019999" not in str(event.metadata)
    assert resolution["reason"] not in str(event.metadata)
    resolution["reason"] = "سبب لاحق لا يغير قرار الحل"
    assert client.post(url, resolution, content_type="application/json").status_code == 200
    item.refresh_from_db()
    assert item.resolution_reason == "سبب حل المراجعة مستقل"
    assert AuditLog.objects.filter(action=action, target_id=str(item.id)).count() == 1
