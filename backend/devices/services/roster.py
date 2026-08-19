"""Student-only device roster analysis and execution over the Phase 8.5 models."""

import hashlib
import json
import uuid

from django.utils import timezone as dj_timezone

from academics.models import AcademicYear, AcademicYearStatus
from devices.models import (
    AttendanceDevice,
    DeviceRosterSyncAction,
    DeviceRosterSyncItem,
    DeviceRosterSyncItemStatus,
    DeviceRosterSyncJob,
    DeviceRosterSyncStatus,
    IdentityStatus,
    StudentDeviceIdentity,
)
from students.models import EnrollmentStatus, Student, StudentStatus

ELIGIBLE_STATUS = StudentStatus.ACTIVE
INELIGIBLE_STATUSES = {
    StudentStatus.GRADUATED,
    StudentStatus.TRANSFERRED,
    StudentStatus.WITHDRAWN,
    StudentStatus.INACTIVE,
}


def _stable_external_user_id(student: Student) -> str:
    """Stable, non-sensitive ID; it contains no national ID or academic placement."""
    value = f"xmansx:student:{student.school_id}:{student.pk}"
    return f"stu-{uuid.uuid5(uuid.NAMESPACE_URL, value)}"


def _managed_snapshot(*, student: Student, enrollment) -> dict:
    return {
        "external_user_id": _stable_external_user_id(student),
        "display_name": student.full_name,
        "student_id": student.id,
        "grade_name": enrollment.grade.name if enrollment else None,
        "section_name": enrollment.section.name if enrollment else None,
    }


def active_student_roster(*, school) -> list[dict]:
    year = AcademicYear.objects.filter(
        school=school, status=AcademicYearStatus.ACTIVE
    ).first()
    if year is None:
        return []
    students = (
        Student.objects.filter(
            school=school,
            status=ELIGIBLE_STATUS,
            enrollments__school=school,
            enrollments__academic_year=year,
            enrollments__status=EnrollmentStatus.ACTIVE,
        )
        .prefetch_related("enrollments__grade", "enrollments__section")
        .distinct()
        .order_by("id")
    )
    result = []
    for student in students:
        enrollment = next(
            (
                row
                for row in student.enrollments.all()
                if row.academic_year_id == year.id and row.status == EnrollmentStatus.ACTIVE
            ),
            None,
        )
        result.append(_managed_snapshot(student=student, enrollment=enrollment))
    return result


def roster_hash(users: list[dict]) -> str:
    canonical = [
        {
            "external_user_id": str(user.get("external_user_id", "")),
            "display_name": user.get("display_name", ""),
        }
        for user in users
    ]
    canonical.sort(key=lambda user: user["external_user_id"])
    return hashlib.sha256(
        json.dumps(canonical, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def _normalize_device_users(device_users: list[dict]) -> list[dict]:
    return [
        {
            "external_user_id": str(user.get("external_user_id", "")).strip()[:64],
            "display_name": str(user.get("display_name", "")).strip()[:150],
            "status": str(user.get("status", "ACTIVE"))[:20],
            "metadata_minimal": user.get("metadata_minimal") or {},
        }
        for user in device_users
        if str(user.get("external_user_id", "")).strip()
    ]


def compare_device_roster(*, school, device: AttendanceDevice, device_users: list[dict]) -> dict:
    desired = active_student_roster(school=school)
    desired_by_id = {row["external_user_id"]: row for row in desired}
    identities = {
        identity.external_user_id: identity
        for identity in StudentDeviceIdentity.objects.filter(
            school=school, device=device
        ).select_related("student")
    }
    identity_id_by_student = {
        identity.student_id: identity.external_user_id
        for identity in identities.values()
        if identity.student_id and identity.status == IdentityStatus.MATCHED
    }
    for row in desired:
        existing_external_id = identity_id_by_student.get(row["student_id"])
        if existing_external_id:
            row["external_user_id"] = existing_external_id
    normalized = _normalize_device_users(device_users)
    by_external_id: dict[str, list[dict]] = {}
    for user in normalized:
        by_external_id.setdefault(user["external_user_id"], []).append(user)

    items: list[dict] = []
    for external_id, users in by_external_id.items():
        identity = identities.get(external_id)
        if len(users) != 1 or (
            identity
            and identity.status in {IdentityStatus.CONFLICT, IdentityStatus.UNMATCHED}
        ):
            items.append({
                "student": None,
                "external_user_id": external_id,
                "action": DeviceRosterSyncAction.CONFLICT,
                "reason": "duplicate_or_unresolved_device_identity",
                "before": users[0],
                "after": {},
            })
            continue
        user = users[0]
        desired_row = desired_by_id.get(external_id)
        if desired_row is not None:
            action = (
                DeviceRosterSyncAction.MATCHED
                if user["display_name"] == desired_row["display_name"]
                else DeviceRosterSyncAction.UPDATE
            )
            items.append({
                "student": desired_row["student_id"],
                "external_user_id": external_id,
                "action": action,
                "reason": (
                    "managed_display_name_differs"
                    if action == DeviceRosterSyncAction.UPDATE
                    else ""
                ),
                "before": user,
                "after": desired_row,
            })
            continue
        if (
            identity
            and identity.student_id
            and identity.student.status in INELIGIBLE_STATUSES
        ):
            items.append({
                "student": identity.student_id,
                "external_user_id": external_id,
                "action": DeviceRosterSyncAction.DELETE,
                "reason": "student_lifecycle_not_eligible",
                "before": user,
                "after": {},
            })
        else:
            items.append({
                "student": None,
                "external_user_id": external_id,
                "action": DeviceRosterSyncAction.CONFLICT,
                "reason": "unknown_device_user_never_platform_managed",
                "before": user,
                "after": {},
            })

    present_ids = set(by_external_id)
    for desired_id, desired_row in desired_by_id.items():
        if desired_id not in present_ids:
            existing_identity = identities.get(desired_id)
            external_id = existing_identity.external_user_id if existing_identity else desired_id
            items.append({
                "student": desired_row["student_id"],
                "external_user_id": external_id,
                "action": DeviceRosterSyncAction.CREATE,
                "reason": "active_student_missing_from_device",
                "before": {},
                "after": {**desired_row, "external_user_id": external_id},
            })

    counts = {
        action: sum(item["action"] == action for item in items)
        for action in DeviceRosterSyncAction.values
    }
    return {
        "items": items,
        "summary": {
            "matched_count": counts[DeviceRosterSyncAction.MATCHED],
            "create_count": counts[DeviceRosterSyncAction.CREATE],
            "update_count": counts[DeviceRosterSyncAction.UPDATE],
            "delete_count": counts[DeviceRosterSyncAction.DELETE],
            "conflict_count": counts[DeviceRosterSyncAction.CONFLICT],
            "student_count": len(desired),
            "device_user_count": len(normalized),
        },
        "roster_version": roster_hash(desired),
        "device_roster_version": roster_hash(normalized),
    }


def save_analysis(*, job: DeviceRosterSyncJob, device_users: list[dict]) -> DeviceRosterSyncJob:
    result = compare_device_roster(
        school=job.school, device=job.device, device_users=device_users
    )
    job.items.all().delete()
    DeviceRosterSyncItem.objects.bulk_create([
        DeviceRosterSyncItem(
            job=job,
            device=job.device,
            student_id=item["student"],
            external_user_id=item["external_user_id"],
            action=item["action"],
            status=(
                DeviceRosterSyncItemStatus.SKIPPED
                if item["action"]
                in {DeviceRosterSyncAction.MATCHED, DeviceRosterSyncAction.CONFLICT}
                else DeviceRosterSyncItemStatus.PENDING
            ),
            reason=item["reason"],
            safe_before_snapshot={
                key: value for key, value in item["before"].items()
                if key in {"external_user_id", "display_name", "status"}
            },
            safe_after_snapshot={
                key: value for key, value in item["after"].items()
                if key in {"external_user_id", "display_name"}
            },
        )
        for item in result["items"]
    ])
    for field, value in result["summary"].items():
        if field.endswith("_count"):
            setattr(job, field, value)
    job.roster_version = result["roster_version"]
    job.device_roster_version = result["device_roster_version"]
    job.status = DeviceRosterSyncStatus.READY_FOR_REVIEW
    job.ready_at = dj_timezone.now()
    job.save(update_fields=[
        "roster_version", "device_roster_version", "matched_count", "create_count",
        "update_count", "delete_count", "conflict_count", "status", "ready_at", "updated_at",
    ])
    return job


def current_roster_version(*, school) -> str:
    return roster_hash(active_student_roster(school=school))


def approve_job(*, job: DeviceRosterSyncJob, membership) -> DeviceRosterSyncJob:
    if job.status != DeviceRosterSyncStatus.READY_FOR_REVIEW:
        raise ValueError("DEVICE_ROSTER_SYNC_NOT_READY")
    if current_roster_version(school=job.school) != job.roster_version:
        job.status = DeviceRosterSyncStatus.STALE
        job.save(update_fields=["status", "updated_at"])
        raise ValueError("DEVICE_ROSTER_PREVIEW_STALE")
    job.status = DeviceRosterSyncStatus.APPROVED
    job.approved_at = dj_timezone.now()
    for item in job.items.filter(
        action__in=[
            DeviceRosterSyncAction.CREATE,
            DeviceRosterSyncAction.UPDATE,
            DeviceRosterSyncAction.DELETE,
        ],
        status=DeviceRosterSyncItemStatus.PENDING,
    ).filter(command_id=""):
        item.command_id = uuid.uuid4().hex
        item.save(update_fields=["command_id", "updated_at"])
    if not job.items.filter(status=DeviceRosterSyncItemStatus.PENDING).exists():
        job.status = DeviceRosterSyncStatus.RUNNING
    job.save(update_fields=["status", "approved_at", "updated_at"])
    return job


def command_payload(item: DeviceRosterSyncItem) -> dict:
    return {
        "command_id": item.command_id,
        "job_id": item.job_id,
        "item_id": item.id,
        "device_id": item.device_id,
        "action": item.action,
        "external_user_id": item.external_user_id,
        "display_name": item.safe_after_snapshot.get("display_name", ""),
    }
