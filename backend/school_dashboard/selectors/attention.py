"""قائمة «يحتاج متابعة» — طابور عمل تشغيلي لا تصنيف خطورة (بنود 52-55).

كل عنصر يمثل **إجراءً إداريًا مطلوبًا الآن**، وليس حكمًا على طالب. لا درجات
خطر ولا ترتيب طلاب ولا أي قرار تلقائي — الأولوية هنا للترتيب البصري فقط.

مشتقة بالكامل من الاستعلامات القائمة: لا جدول ولا Read Model مخزّن (بند 54).
"""

from attendance.models import AttendanceSessionStatus
from attendance.selectors.monitoring import (
    NOT_STARTED,
    OVERDUE,
    get_current_section_attendance_statuses,
)
from excuses.models import AbsenceExcuse, AbsenceExcuseStatus
from parents.models import AttendanceCorrectionRequest, ParentExcuseRequest
from parents.request_models import ParentRequestStatus
from referrals.models import ReferralStatus, StudentReferral

#: سقف العناصر المعروضة لكل نوع — طابور عمل لا تقرير شامل
MAX_ITEMS_PER_KIND = 10

PRIORITY_HIGH = "HIGH"
PRIORITY_NORMAL = "NORMAL"


def _item(*, kind, entity_type, entity_id, reason_code, text, priority, target_url,
          occurred_at=None) -> dict:
    return {
        "kind": kind,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "reason_code": reason_code,
        "display_text": text,
        "priority": priority,  # للترتيب البصري فقط — ليست تقييمًا
        "target_url": target_url,
        "occurred_at": occurred_at,
    }


def overdue_sections(*, school) -> list[dict]:
    """فصول تجاوزت مهلة التحضير في الحصة الجارية."""
    monitoring = get_current_section_attendance_statuses(school=school)
    items = []
    for row in monitoring.get("sections", []):
        if row["timeliness_status"] != OVERDUE:
            continue
        # الاعتماد المتأخر حقيقة تاريخية تعرض في شاشة المتابعة، لكنه لم يعد
        # مهمة مفتوحة في طابور الإجراءات بعد اعتماد الفصل.
        if row["attendance_status"] == AttendanceSessionStatus.SUBMITTED:
            continue
        not_started = row["attendance_status"] == NOT_STARTED
        department_label = f" / {row['department']}" if row.get("department") else ""
        items.append(
            _item(
                kind="ATTENDANCE_OVERDUE",
                entity_type="SECTION",
                entity_id=row["section_id"],
                reason_code="SECTION_NOT_SUBMITTED" if not_started else "SECTION_LATE",
                text=(
                    f"{row['grade_name']} / فصل {row['section_name']}"
                    f"{department_label} — "
                    f"متأخر {row['minutes_overdue']} دقيقة"
                ),
                priority=PRIORITY_HIGH if not_started else PRIORITY_NORMAL,
                target_url="/attendance/monitoring",
            )
        )
    return items[:MAX_ITEMS_PER_KIND]


def pending_excuses(*, school) -> list[dict]:
    """أعذار بانتظار البت — تأخير البت يبقي الغياب «بدون عذر» بلا وجه حق."""
    rows = (
        AbsenceExcuse.objects.filter(school=school, status=AbsenceExcuseStatus.PENDING)
        .select_related("student")
        .order_by("recorded_at")[:MAX_ITEMS_PER_KIND]
    )
    return [
        _item(
            kind="EXCUSE_PENDING",
            entity_type="EXCUSE",
            entity_id=row.id,
            reason_code="EXCUSE_AWAITING_DECISION",
            text=f"عذر بانتظار الاعتماد — {row.student.full_name}",
            priority=PRIORITY_NORMAL,
            target_url="/excuses",
            occurred_at=row.recorded_at.isoformat(),
        )
        for row in rows
    ]


def unassigned_referrals(*, school) -> list[dict]:
    """إحالات معلم لم تجد وكيلًا مطابقًا في توزيع الصفوف والفصول."""
    rows = (
        StudentReferral.objects.filter(
            school=school,
            status=ReferralStatus.PENDING_VICE,
            assigned_vice_membership__isnull=True,
        )
        .select_related("student")
        .order_by("created_at")[:MAX_ITEMS_PER_KIND]
    )
    return [
        _item(
            kind="REFERRAL_UNASSIGNED",
            entity_type="REFERRAL",
            entity_id=row.id,
            reason_code="REFERRAL_NEEDS_VICE_PRINCIPAL",
            text=f"إحالة تحتاج تعيين وكيل مسؤول — {row.student.full_name}",
            priority=PRIORITY_HIGH,
            target_url="/referrals",
            occurred_at=row.created_at.isoformat(),
        )
        for row in rows
    ]


def warning_due_students(*, school) -> list[dict]:
    """طلاب بلغوا عتبة إنذار ولم يصدر لهم — **عرض فقط، لا إصدار تلقائي** (بند 36)."""
    from student_warnings.selectors.eligibility import eligibility_dashboard

    try:
        result = eligibility_dashboard(
            school=school, status_filter="due", page_size=MAX_ITEMS_PER_KIND
        )
    except Exception:  # noqa: BLE001 — لا عام دراسي نشط: القسم يظهر فارغًا
        return []
    return [
        _item(
            kind="WARNING_DUE",
            entity_type="STUDENT",
            entity_id=row["student_id"],
            reason_code="WARNING_THRESHOLD_REACHED",
            text=(
                f"{row['full_name']} — بلغ عتبة {row['highest_due_level']} "
                f"({row['current_value']})"
            ),
            priority=PRIORITY_HIGH,
            target_url="/warnings",
        )
        for row in result.get("results", [])[:MAX_ITEMS_PER_KIND]
    ]


def counseling_items(*, school) -> list[dict]:
    """عناصر الإرشاد (طلبات معلمين متأخرة، حالات بلا نشاط) — فاصل المرحلة 14."""
    from django.apps import apps

    if not apps.is_installed("counseling"):
        return []
    from school_dashboard.selectors import counseling_bridge

    return counseling_bridge.attention_items(school=school)


def pending_family_requests(*, school, model, request_type) -> list[dict]:
    """School review queue; never copy request text, attachments or global contacts."""
    rows = (
        model.objects.filter(
            school=school, status__in=(ParentRequestStatus.PENDING, ParentRequestStatus.NEEDS_INFO)
        )
        .select_related("student")
        .order_by("created_at", "id")[:MAX_ITEMS_PER_KIND]
    )
    label = "عذر ولي أمر" if request_type == "EXCUSE" else "طلب تصحيح حضور"
    return [
        _item(
            kind=f"PARENT_{request_type}_PENDING",
            entity_type=f"PARENT_{request_type}_REQUEST",
            entity_id=row.id,
            reason_code="FAMILY_AWAITING_INFORMATION"
            if row.status == "NEEDS_INFO"
            else "FAMILY_AWAITING_SCHOOL_REVIEW",
            text=(
                f"{label} "
                f"{'يحتاج استكمالاً' if row.status == 'NEEDS_INFO' else 'بانتظار المراجعة'} "
                f"— {row.student.full_name}"
            ),
            priority=PRIORITY_NORMAL,
            target_url=f"/parent-management?tab=requests&type={request_type}&request={row.id}",
            occurred_at=row.created_at.isoformat(),
        )
        for row in rows
    ]


def attention_queue(*, school) -> dict:
    """طابور العمل الموحد — مرتب بالأولوية البصرية ثم النوع."""
    groups = {
        "attendance_overdue": overdue_sections(school=school),
        "warning_due": warning_due_students(school=school),
        "excuse_pending": pending_excuses(school=school),
        "referral_unassigned": unassigned_referrals(school=school),
        "counseling": counseling_items(school=school),
        "parent_excuse_pending": pending_family_requests(
            school=school, model=ParentExcuseRequest, request_type="EXCUSE"
        ),
        "parent_correction_pending": pending_family_requests(
            school=school, model=AttendanceCorrectionRequest, request_type="CORRECTION"
        ),
    }
    items = [item for group in groups.values() for item in group]
    items.sort(key=lambda row: (0 if row["priority"] == PRIORITY_HIGH else 1, row["kind"]))
    return {
        "total": len(items),
        "counts": {key: len(value) for key, value in groups.items()},
        "items": items,
        "item_cap_per_kind": MAX_ITEMS_PER_KIND,
    }
