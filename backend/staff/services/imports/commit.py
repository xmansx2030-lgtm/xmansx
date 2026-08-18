"""اعتماد استيراد المعلمين — ذري، Idempotent، محمي من stale، وآمن للسباقات.

- جديد: User (كلمة مؤقتة عبر secrets + must_change_password) + عضوية ACTIVE
  + دور TEACHER + StaffProfile. الكلمة تعاد مرة واحدة في الاستجابة فقط —
  لا تخزن plaintext في Job/staging/audit/logs إطلاقًا.
- موجود عالميًا: إعادة استخدام User + عضوية INVITED + دور TEACHER + Profile —
  كلمة مروره واسمه العالمي لا يمسان.
- سباق إنشاء User: قيد UNIQUE(mobile) هو الحكم؛ IntegrityError → إعادة جلب
  الموجود والتحول لمسار الدعوة.
"""

import secrets

from django.db import IntegrityError, transaction
from django.utils import timezone

from accounts.models import User
from audit.models import AuditAction
from audit.services import record_event
from common.errors import ApiError
from memberships.models import (
    MembershipStatus,
    SchoolMembership,
    SchoolMembershipRole,
    SchoolRole,
)
from staff.models import StaffImportJob, StaffImportStatus, StaffProfile, StaffSource
from staff.services.imports.pipeline import categorize_rows

_APPLY = {"NEW", "EXISTING_USER_INVITE", "ADD_TEACHER_ROLE", "PROFILE_UPDATE"}


def _generate_temp_password() -> str:
    return secrets.token_urlsafe(9)  # ~12 محرفًا، cryptographically secure


def commit_import(*, job_id: int, actor, request=None) -> tuple[StaffImportJob, list[dict]]:
    """الكتابات (فشل/تحديث معاينة) تثبت داخل الـ transaction والخطأ يرفع بعدها."""
    with transaction.atomic():
        job, credentials, deferred_error = _commit_locked(
            job_id=job_id, actor=actor, request=request
        )
    if deferred_error is not None:
        raise deferred_error
    return job, credentials


def _rows_to_normalized(rows) -> list[dict]:
    normalized = []
    for row in rows:
        data = dict(row.data)
        data["row_number"] = row.row_number
        data["mobile"] = row.mobile
        data["errors"] = list(row.error_codes)
        normalized.append(data)
    return normalized


def _commit_locked(*, job_id: int, actor, request=None):
    job = (
        StaffImportJob.objects.select_for_update()
        .select_related("school")
        .get(id=job_id)
    )

    if job.status == StaffImportStatus.COMPLETED:
        raise ApiError(
            "STAFF_IMPORT_ALREADY_COMMITTED", "تم اعتماد هذا الاستيراد مسبقاً.", 409
        )
    if job.status in (StaffImportStatus.PROCESSING, StaffImportStatus.IMPORTING):
        raise ApiError("IMPORT_ALREADY_RUNNING", "الاستيراد قيد التنفيذ حالياً.", 409)
    if job.status != StaffImportStatus.READY_FOR_REVIEW:
        raise ApiError("IMPORT_NOT_READY", "الاستيراد غير جاهز للاعتماد.", 409)

    staged = list(job.rows.all())
    stored_statuses = {row.row_number: row.status for row in staged}

    result = categorize_rows(job.school, _rows_to_normalized(staged))
    fresh_by_number = {r["row_number"]: r for r in result["rows"]}
    stale = any(
        fresh_by_number[num]["status"] != status for num, status in stored_statuses.items()
    )
    if stale:
        for row in staged:
            fresh = fresh_by_number[row.row_number]
            row.status = fresh["status"]
            row.data = {
                k: v for k, v in fresh.items()
                if k not in ("mobile", "errors", "row_number")
            }
            row.save(update_fields=["status", "data"])
        job.summary = {**job.summary, **result["summary"]}
        job.save(update_fields=["summary", "updated_at"])
        return job, [], ApiError(
            "STAFF_IMPORT_PREVIEW_STALE",
            "تغيرت بيانات الموظفين منذ إنشاء المعاينة. راجع المعاينة المحدثة ثم أعد الاعتماد.",
            409,
        )

    job.status = StaffImportStatus.IMPORTING
    job.save(update_fields=["status", "updated_at"])

    credentials: list[dict] = []
    counts = {"created": 0, "invited": 0, "roles_added": 0, "profiles_updated": 0}

    for row in result["rows"]:
        if row["status"] not in _APPLY:
            continue
        if row["status"] == "NEW":
            _apply_new(job, row, credentials, counts, actor, request)
        elif row["status"] == "EXISTING_USER_INVITE":
            _apply_invite(job, row, counts, actor, request)
        else:
            _apply_existing_member(job, row, counts, actor, request)

    job.status = StaffImportStatus.COMPLETED
    job.committed_at = timezone.now()
    job.new_user_rows = counts["created"]
    job.existing_user_rows = counts["invited"]
    job.summary = {**result["summary"], **counts}  # لا كلمات مرور هنا
    job.save(
        update_fields=[
            "status", "committed_at", "new_user_rows", "existing_user_rows",
            "summary", "updated_at",
        ]
    )
    record_event(
        AuditAction.STAFF_IMPORT_COMMITTED,
        request=request, actor=actor, school=job.school,
        target_type="StaffImportJob", target_id=job.id,
        metadata=counts,
    )

    # تنظيف PII المؤقت
    job.rows.all().delete()
    if job.file:
        job.file.delete(save=False)
        job.file = None
        job.save(update_fields=["file"])

    return job, credentials, None


def _ensure_profile(job, membership, row, counts, actor, request, created_membership: bool):
    profile = getattr(membership, "staff_profile", None)
    if profile is None:
        StaffProfile.objects.create(
            school=job.school,
            membership=membership,
            display_name=row["full_name"],
            employee_number=row["employee_number"],
            job_title=row["job_title"],
            source=StaffSource.IMPORT,
        )
        record_event(
            AuditAction.STAFF_PROFILE_CREATED,
            request=request, actor=actor, school=job.school,
            target_type="SchoolMembership", target_id=membership.id,
        )
    else:
        changed = []
        if profile.display_name != row["full_name"]:
            profile.display_name = row["full_name"]
            changed.append("display_name")
        if row["employee_number"] and profile.employee_number != row["employee_number"]:
            profile.employee_number = row["employee_number"]
            changed.append("employee_number")
        if row["job_title"] and profile.job_title != row["job_title"]:
            profile.job_title = row["job_title"]
            changed.append("job_title")
        if changed:
            profile.save()
            counts["profiles_updated"] += 1
            record_event(
                AuditAction.STAFF_PROFILE_UPDATED,
                request=request, actor=actor, school=job.school,
                target_type="SchoolMembership", target_id=membership.id,
                metadata={"changed_fields": changed},
            )


def _apply_new(job, row, credentials, counts, actor, request):
    temp_password = _generate_temp_password()
    try:
        with transaction.atomic():  # savepoint لالتقاط سباق UNIQUE(mobile)
            user = User.objects.create_user(
                mobile=row["mobile"],
                password=temp_password,
                first_name=row["full_name"],
                must_change_password=True,
            )
    except IntegrityError:
        # أنشأه طلب آخر في نفس اللحظة — نتحول لمسار الدعوة
        _apply_invite(job, row, counts, actor, request)
        return

    membership = SchoolMembership.objects.create(
        user=user, school=job.school, status=MembershipStatus.ACTIVE
    )
    SchoolMembershipRole.objects.create(membership=membership, role=SchoolRole.TEACHER)
    _ensure_profile(job, membership, row, counts, actor, request, created_membership=True)
    counts["created"] += 1
    credentials.append(
        {
            "name": row["full_name"],
            "mobile_masked": row["mobile_masked"],
            "temporary_password": temp_password,  # يعاد في الاستجابة فقط — لا يخزن
        }
    )


def _apply_invite(job, row, counts, actor, request):
    user = User.objects.get(mobile=row["mobile"])
    membership, created = SchoolMembership.objects.get_or_create(
        user=user, school=job.school, defaults={"status": MembershipStatus.INVITED}
    )
    if created:
        record_event(
            AuditAction.SCHOOL_MEMBERSHIP_INVITED,
            request=request, actor=actor, school=job.school,
            target_type="SchoolMembership", target_id=membership.id,
            metadata={"mobile_masked": row["mobile_masked"]},
        )
        counts["invited"] += 1
    SchoolMembershipRole.objects.get_or_create(membership=membership, role=SchoolRole.TEACHER)
    _ensure_profile(job, membership, row, counts, actor, request, created_membership=created)


def _apply_existing_member(job, row, counts, actor, request):
    membership = SchoolMembership.objects.select_related("user").get(
        id=row["membership_id"], school=job.school
    )
    _, created = SchoolMembershipRole.objects.get_or_create(
        membership=membership, role=SchoolRole.TEACHER
    )
    if created:
        counts["roles_added"] += 1
        record_event(
            AuditAction.STAFF_ROLE_ADDED,
            request=request, actor=actor, school=job.school,
            target_type="SchoolMembership", target_id=membership.id,
            metadata={"role": SchoolRole.TEACHER},
        )
    _ensure_profile(job, membership, row, counts, actor, request, created_membership=False)
