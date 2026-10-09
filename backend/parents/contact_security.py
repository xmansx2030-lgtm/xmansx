"""Contact changes remain separate from global account identity and access grants."""

from contextlib import contextmanager

from django.core.exceptions import ValidationError
from django.db import connection

from accounts.mobile import normalize_mobile
from common.errors import ApiError
from common.tenant_rls import can_restore_tenant_context
from school_sms.security import recipient_hash


def normalized_contact(value: str) -> str:
    if not value or not value.strip():
        return ""
    try:
        return normalize_mobile(value)
    except ValidationError:
        return value.strip()


def contact_changed(student, data: dict) -> bool:
    from students.services.imports.normalization import normalize_text

    return (
        "guardian_mobile" in data
        and normalized_contact(student.guardian_mobile)
        != normalized_contact(data["guardian_mobile"])
    ) or (
        "guardian_name" in data
        and normalize_text(student.guardian_name).casefold()
        != normalize_text(data["guardian_name"]).casefold()
    )


@contextmanager
def contact_write_context(
    *,
    source: str,
    actor=None,
    reason: str = "",
    previous_mobile=None,
    current_mobile=None,
):
    """Attach safe provenance to the authoritative PostgreSQL trigger."""
    if not connection.in_atomic_block:
        raise RuntimeError("Contact writes require an atomic transaction")
    keys = (
        "app.parent_contact_source",
        "app.parent_contact_actor",
        "app.parent_contact_reason",
        "app.parent_previous_contact_hash",
        "app.parent_current_contact_hash",
    )
    values = (
        source[:40],
        str(actor.pk) if actor else "",
        reason[:300],
        recipient_hash(normalized_contact(previous_mobile)) if previous_mobile is not None else "",
        recipient_hash(normalized_contact(current_mobile)) if current_mobile is not None else "",
    )
    with connection.cursor() as cursor:
        previous = []
        for key in keys:
            cursor.execute("SELECT current_setting(%s, true)", [key])
            previous.append(cursor.fetchone()[0] or "")
        for key, value in zip(keys, values, strict=True):
            cursor.execute("SELECT set_config(%s, %s, true)", [key, value])
    try:
        yield
    finally:
        if can_restore_tenant_context():
            with connection.cursor() as cursor:
                for key, value in zip(keys, previous, strict=True):
                    cursor.execute("SELECT set_config(%s, %s, true)", [key, value])


def require_contact_verification(student, data: dict) -> None:
    """Keep legacy non-portal updates compatible; protected bindings require proof."""
    from parents.models import GuardianStudentRelation

    if (
        contact_changed(student, data)
        and GuardianStudentRelation.objects.filter(
            student=student,
            contact_bound=True,
            status__in=["ACTIVE", "SUSPENDED_CONTACT_REVIEW", "PENDING"],
        ).exists()
    ):
        if (
            not data.get("contact_identity_verified")
            or not str(data.get("contact_change_reason", "")).strip()
            or not str(data.get("contact_verification_note", "")).strip()
        ):
            raise ApiError(
                "CONTACT_VERIFICATION_REQUIRED",
                "تحقق من صفة مقدم الطلب وسجل سبب تغيير التواصل وإثبات التحقق.",
                400,
            )


def recipient_blocked(*, school, student_id: int, mobile: str) -> bool:
    """Only explicit evidence about this student/number blocks existing absence SMS."""
    from parents.models import RecipientContactBlock

    return RecipientContactBlock.objects.filter(
        school=school,
        student_id=student_id,
        mobile_hash=recipient_hash(mobile),
        resolved_at__isnull=True,
    ).exists()


def blocked_student_ids(*, school, students) -> set[int]:
    """Batch the explicit recipient check so a large SMS preview has no per-row queries."""
    from parents.models import RecipientContactBlock

    hashes = {student.pk: recipient_hash(student.guardian_mobile) for student in students}
    return {
        student_id
        for student_id, mobile_hash in RecipientContactBlock.objects.filter(
            school=school,
            student_id__in=hashes,
            resolved_at__isnull=True,
        ).values_list("student_id", "mobile_hash")
        if hashes[student_id] == mobile_hash
    }
