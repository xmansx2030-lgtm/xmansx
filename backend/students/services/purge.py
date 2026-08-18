"""الحذف النهائي (Permanent Purge) — فردي وجماعي.

المبادئ:
- SCHOOL_MANAGER فقط (تفرض في طبقة الـ API) — ولا Tenant bypass لمدير المنصة.
- الطالب ACTIVE لا يحذف (STUDENT_ACTIVE_CANNOT_PURGE) — التصنيف أولًا.
- Preview بملخص خادمي + confirmation token (Redis، 10 دقائق) + إعادة تحقق عند
  التنفيذ (PURGE_PREVIEW_STALE عند أي تغير في المجموعة أو حالاتها).
- حذف DB ذري لكل طالب بترتيب التبعيات عبر سجل PURGE_STEPS القابل للتوسعة —
  **كل موديول قادم يملك بيانات طالب (أعذار/إنذارات/إحالات/مستندات/حضور) ملزم
  بالتسجيل هنا** وإلا فشل الحذف بـ ProtectedError (فشل صاخب لا صامت).
- ملفات التخزين عبر سجل PURGE_STORAGE_COLLECTORS (خارج الـ transaction):
  فشل حذف ملف لا يتجاهل — يعد storage_objects_failed وتصبح العملية
  PARTIALLY_FAILED (حذف الصفوف وحده ليس Purge كاملًا).
- الخصوصية: بعد الاكتمال تمسح student_ids من الـ Job، وAudit بلا أي PII.
"""

import hashlib
import logging
import secrets

from django.core.cache import cache
from django.db import transaction

from audit.services import record_event
from common.errors import ApiError
from students.models import (
    PurgeJobStatus,
    Student,
    StudentEnrollment,
    StudentPurgeJob,
    StudentStatus,
)
from students.services.lifecycle import get_students_for_school

logger = logging.getLogger("xmansx.purge")

PURGE_BATCH_SIZE = 50  # مضبوط بقياس benchmark_purge — انظر DATA_PURGE.md
PREVIEW_TTL_SECONDS = 600

# (تسمية عربية للملخص، دالة queryset(student_ids) للحذف) — الترتيب = ترتيب الحذف
PURGE_STEPS: list[tuple[str, object]] = [
    (
        "القيود الدراسية",
        lambda ids: StudentEnrollment.objects.filter(student_id__in=ids),
    ),
]

# دوال تجمع ملفات التخزين للطالب: collector(student) -> list[FieldFile-like]
# (لا ملفات طلاب في الوحدات الحالية — الوحدات القادمة تسجل هنا: مرفقات الأعذار،
#  المستندات المولدة، ... الآلية مثبتة باختبارات fake storage)
PURGE_STORAGE_COLLECTORS: list = []


def _selection_fingerprint(students: list[Student]) -> str:
    payload = "|".join(f"{s.id}:{s.status}" for s in sorted(students, key=lambda s: s.id))
    return hashlib.sha256(payload.encode()).hexdigest()


def _validate_purgeable(students: list[Student]) -> None:
    active = [s for s in students if s.status == StudentStatus.ACTIVE]
    if active:
        raise ApiError(
            "STUDENT_ACTIVE_CANNOT_PURGE",
            "لا يمكن الحذف النهائي لطلاب نشطين — غيّر حالتهم أولاً.",
            status_code=409,
        )


def collect_summary(student_ids: list[int]) -> dict:
    """ملخص خادمي موثوق لما سيحذف — لا اعتماد على أرقام الواجهة."""
    summary = {"students": len(student_ids)}
    total = 0
    for label, queryset_fn in PURGE_STEPS:
        count = queryset_fn(student_ids).count()
        summary[label] = count
        total += count
    storage_count = 0
    for student in Student.objects.filter(id__in=student_ids):
        for collector in PURGE_STORAGE_COLLECTORS:
            storage_count += len(collector(student))
    summary["الملفات المخزنة"] = storage_count
    summary["database_records"] = total + len(student_ids)
    return summary


def create_purge_preview(*, school, actor, student_ids: list[int]) -> dict:
    students = get_students_for_school(school=school, student_ids=student_ids)
    _validate_purgeable(students)
    _ensure_no_running_job(school)

    summary = collect_summary([s.id for s in students])
    token = secrets.token_urlsafe(24)
    cache.set(
        f"purge-preview:{token}",
        {
            "school_id": school.id,
            "actor_id": actor.id,
            "student_ids": [s.id for s in students],
            "fingerprint": _selection_fingerprint(students),
        },
        timeout=PREVIEW_TTL_SECONDS,
    )
    return {
        "confirmation_token": token,
        "summary": summary,
        "expires_in_seconds": PREVIEW_TTL_SECONDS,
    }


def _ensure_no_running_job(school) -> None:
    if StudentPurgeJob.objects.filter(
        school=school, status__in=[PurgeJobStatus.PENDING, PurgeJobStatus.RUNNING]
    ).exists():
        raise ApiError(
            "PURGE_ALREADY_RUNNING", "توجد عملية حذف جارية لهذه المدرسة.", status_code=409
        )


def create_purge_job(*, school, actor, confirmation_token: str, reason: str = "",
                     request=None) -> StudentPurgeJob:
    payload = cache.get(f"purge-preview:{confirmation_token}")
    if payload is None or payload["school_id"] != school.id:
        raise ApiError(
            "PURGE_PREVIEW_STALE",
            "انتهت صلاحية معاينة الحذف — أعد المعاينة ثم أكد من جديد.",
            status_code=409,
        )
    students = list(Student.objects.filter(school=school, id__in=payload["student_ids"]))
    # إعادة تحقق كاملة: أي تغير في المجموعة أو حالاتها منذ المعاينة يرفض
    if (
        len(students) != len(payload["student_ids"])
        or _selection_fingerprint(students) != payload["fingerprint"]
    ):
        cache.delete(f"purge-preview:{confirmation_token}")
        raise ApiError(
            "PURGE_PREVIEW_STALE",
            "تغيرت بيانات الطلاب منذ المعاينة — أعد المعاينة ثم أكد من جديد.",
            status_code=409,
        )
    _validate_purgeable(students)
    _ensure_no_running_job(school)
    cache.delete(f"purge-preview:{confirmation_token}")  # token يستخدم مرة واحدة

    job = StudentPurgeJob.objects.create(
        school=school,
        created_by=actor,
        reason=reason[:100],
        student_ids=[s.id for s in students],
        total_students=len(students),
    )
    record_event(
        "STUDENT_BULK_PURGE_STARTED",
        request=request,
        actor=actor,
        school=school,
        target_type="StudentPurgeJob",
        target_id=job.id,
        metadata={"students": job.total_students, "reason": job.reason},
    )
    return job


def purge_student(student: Student) -> tuple[int, int, int]:
    """حذف طالب واحد: DB ذريًا ثم ملفات التخزين — يعيد (db_rows, storage_ok, storage_failed)."""
    storage_files = []
    for collector in PURGE_STORAGE_COLLECTORS:
        storage_files.extend(collector(student))

    db_rows = 0
    with transaction.atomic():
        for _, queryset_fn in PURGE_STEPS:
            deleted, _ = queryset_fn([student.id]).delete()
            db_rows += deleted
        student.delete()
        db_rows += 1

    storage_ok = 0
    storage_failed = 0
    for file_obj in storage_files:
        try:
            file_obj.delete(save=False)
            storage_ok += 1
        except Exception:
            logger.exception("purge: storage object deletion failed")
            storage_failed += 1
    return db_rows, storage_ok, storage_failed
