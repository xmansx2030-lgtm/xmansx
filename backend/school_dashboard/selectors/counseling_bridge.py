"""وصلة المرحلة 14 بلوحة الإدارة — **أعداد مجمّعة فقط**.

قواعد ثابتة:
- لا نص إرشادي هنا إطلاقًا: لا ملخص جلسة ولا ملاحظات ولا وصف إحالة (بند 45/87).
- لا تقييم أداء لمرشد ولا ترتيب مرشدين (بند 88) — عدّادات تشغيلية لا غير.
- إحالة ≠ حالة إرشادية: هذا الملف يعدّ الحالات فقط، والإحالات في `referral_metrics`.
- لا إعادة حساب: الحالات والحقول تُقرأ من نماذج م14 كما هي.
"""

from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone as dj_timezone

from counseling.models import (
    LIVE_CASE_STATUSES,
    ActivityStatus,
    CaseStatus,
    CounselorCase,
    FollowUpActivity,
    FollowUpRequestStatus,
    TeacherFollowUpRequest,
)

#: سقف العناصر المعروضة لكل نوع في طابور العمل — مطابق لبقية الطابور
MAX_ITEMS_PER_KIND = 10

#: حالة بلا أي نشاط لهذه المدة تُعرض كعنصر تشغيلي (لا حكم على الطالب ولا المرشد)
STALE_CASE_DAYS = 14


def _scoped_cases(*, school, scope, date_range):
    """حالات المدرسة ضمن فلتر الصف/الفصل — نفس مصدر الطلاب المستخدم في اللوحة."""
    from school_dashboard.selectors.followup import _scoped_students

    cases = CounselorCase.objects.filter(school=school)
    students = _scoped_students(school=school, date_range=date_range, scope=scope)
    if students is not None:
        cases = cases.filter(student_id__in=students)
    return cases


def metrics(*, school, date_range, scope=None) -> dict:
    """مؤشرات الحالات الإرشادية للوحة الإدارة — استعلامات مجمّعة لا صف لكل حالة."""
    cases = _scoped_cases(school=school, scope=scope, date_range=date_range)

    by_status = cases.aggregate(
        open_cases=Count("id", filter=Q(status__in=LIVE_CASE_STATUSES)),
        under_assessment=Count("id", filter=Q(status=CaseStatus.UNDER_ASSESSMENT)),
        follow_up_active=Count("id", filter=Q(status=CaseStatus.FOLLOW_UP_ACTIVE)),
        resolved=Count("id", filter=Q(status=CaseStatus.RESOLVED)),
        closed=Count("id", filter=Q(status=CaseStatus.CLOSED)),
    )
    # داخل المدى الزمني المحدد — منفصل عن الأرصدة اللحظية أعلاه
    in_range = cases.aggregate(
        opened_in_range=Count(
            "id",
            filter=Q(
                opened_at__date__gte=date_range.from_date,
                opened_at__date__lte=date_range.to_date,
            ),
        ),
        closed_in_range=Count(
            "id",
            filter=Q(
                closed_at__date__gte=date_range.from_date,
                closed_at__date__lte=date_range.to_date,
            ),
        ),
    )

    waiting_teacher_responses = TeacherFollowUpRequest.objects.filter(
        case__in=cases, status=FollowUpRequestStatus.PENDING
    ).count()
    overdue_activities = FollowUpActivity.objects.filter(
        plan__case__in=cases,
        status=ActivityStatus.PENDING,
        due_date__lt=dj_timezone.localdate(),
    ).count()

    return {
        "available": True,
        "reason": None,
        "open_cases": by_status["open_cases"] or 0,
        "under_assessment": by_status["under_assessment"] or 0,
        "follow_up_active": by_status["follow_up_active"] or 0,
        "resolved": by_status["resolved"] or 0,
        "closed": by_status["closed"] or 0,
        "opened_in_range": in_range["opened_in_range"] or 0,
        "closed_in_range": in_range["closed_in_range"] or 0,
        "waiting_teacher_responses": waiting_teacher_responses,
        "overdue_activities": overdue_activities,
    }


def attention_items(*, school) -> list[dict]:
    """عناصر تشغيلية: طلب معلم تجاوز موعده، وحالة حية بلا نشاط."""
    from school_dashboard.selectors.attention import (
        PRIORITY_HIGH,
        PRIORITY_NORMAL,
        _item,
    )

    today = dj_timezone.localdate()
    items = []

    overdue_requests = (
        TeacherFollowUpRequest.objects.filter(
            school=school,
            status=FollowUpRequestStatus.PENDING,
            due_date__lt=today,
        )
        .select_related("case__student")
        .order_by("due_date")[:MAX_ITEMS_PER_KIND]
    )
    for row in overdue_requests:
        items.append(
            _item(
                kind="TEACHER_FOLLOW_UP_OVERDUE",
                entity_type="TEACHER_FOLLOW_UP_REQUEST",
                entity_id=row.id,
                reason_code="TEACHER_RESPONSE_OVERDUE",
                text=f"طلب متابعة معلم تجاوز موعده — {row.case.student.full_name}",
                priority=PRIORITY_HIGH,
                target_url=f"/counselor/cases/{row.case_id}",
                occurred_at=row.created_at.isoformat(),
            )
        )

    stale_before = dj_timezone.now() - timedelta(days=STALE_CASE_DAYS)
    stale_cases = (
        CounselorCase.objects.filter(
            school=school,
            status__in=LIVE_CASE_STATUSES,
            last_activity_at__lt=stale_before,
        )
        .select_related("student")
        .order_by("last_activity_at")[:MAX_ITEMS_PER_KIND]
    )
    for row in stale_cases:
        items.append(
            _item(
                kind="CASE_NO_RECENT_ACTIVITY",
                entity_type="COUNSELOR_CASE",
                entity_id=row.id,
                reason_code="CASE_INACTIVE",
                text=(
                    f"حالة بلا نشاط منذ {STALE_CASE_DAYS} يومًا أو أكثر — "
                    f"{row.student.full_name}"
                ),
                priority=PRIORITY_NORMAL,
                target_url=f"/counselor/cases/{row.id}",
                occurred_at=row.last_activity_at.isoformat(),
            )
        )

    return items
