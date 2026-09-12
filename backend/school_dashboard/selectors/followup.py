"""مؤشرات الإنذارات والإجراءات والمستندات والإحالات والإرشاد.

قواعد ثابتة:
- **مستحق ≠ صادر** (بند 35): عدّادان منفصلان لا يُجمعان ولا يُشتق أحدهما من الآخر.
- **إحالة ≠ حالة إرشادية** (بند 97): الإحالة طلب، والحالة ملف متابعة.
- الأرقام فقط — لا نصوص وصف ولا ملاحظات في لوحة الإدارة (بند 45).
- لا تقييم أداء لمعلم ولا لمرشد ولا درجة خطر لطالب (بنود 39/47/58).
"""

from django.db.models import Count, Q

from documents.models import DocumentStatus, DocumentType, GeneratedDocument
from referrals.models import OPEN_STATUSES, ReferralStatus, StudentReferral
from student_actions.models import StudentAction, StudentActionStatus, StudentActionType
from student_warnings.models import StudentWarning, WarningStatus


def _scoped_students(*, school, date_range, scope):
    """معرفات الطلاب ضمن فلتر الصف/الفصل — عبر الفصل التاريخي في ملخص اليوم."""
    from school_dashboard.selectors.attendance import summaries_queryset

    if not (scope or {}).get("section_id") and not (scope or {}).get("grade_id"):
        return None
    return set(
        summaries_queryset(school=school, date_range=date_range, scope=scope)
        .values_list("student_id", flat=True)
        .distinct()
    )


def warning_metrics(*, school, date_range, scope=None) -> dict:
    """الإنذارات: المستحق (لم يصدر) مقابل الصادر فعلًا — منفصلان تمامًا.

    المستحق حالة **لحظية** تُحسب من الاستحقاق الحالي (م11) ولا معنى لتأريخها،
    بينما الصادر يُعدّ داخل نطاق التاريخ المحدد.
    """
    from student_warnings.selectors.eligibility import eligibility_dashboard

    scope = scope or {}
    due: dict = {}
    try:
        eligibility = eligibility_dashboard(
            school=school,
            grade_id=scope.get("grade_id"),
            section_id=scope.get("section_id"),
            status_filter="all",
            page_size=25,
        )
        # ملاحظة: summary أعداد **طلاب** لا إنذارات، وقد يظهر الطالب في الطرفين
        # (صدر له مستوى وبات مستحقًا لمستوى أعلى) — العرض يوضح ذلك.
        due = eligibility.get("summary") or {}
        academic_year = eligibility.get("academic_year")
    except Exception:  # noqa: BLE001 — غياب عام دراسي نشط لا يُسقط اللوحة كلها
        academic_year = None

    issued = StudentWarning.objects.filter(
        school=school,
        status=WarningStatus.ISSUED,
        issued_at__date__gte=date_range.from_date,
        issued_at__date__lte=date_range.to_date,
    )
    students = _scoped_students(school=school, date_range=date_range, scope=scope)
    if students is not None:
        issued = issued.filter(student_id__in=students)

    issued_totals = issued.aggregate(
        total=Count("id"),
        level_1=Count("id", filter=Q(level="LEVEL_1")),
        level_2=Count("id", filter=Q(level="LEVEL_2")),
        level_3=Count("id", filter=Q(level="LEVEL_3")),
        absence=Count("id", filter=Q(warning_type="UNEXCUSED_FULL_DAY_ABSENCE")),
        morning_late=Count("id", filter=Q(warning_type="MORNING_LATE_OCCURRENCES")),
    )
    return {
        "academic_year": academic_year,
        # «مستحق» لحظي وليس ضمن النطاق — موضح صراحة للواجهة
        "due_is_point_in_time": True,
        "due_students_by_type": {
            rule_type: value.get("due_students", 0) for rule_type, value in due.items()
        },
        "issued_students_by_type": {
            rule_type: value.get("issued_students", 0) for rule_type, value in due.items()
        },
        "issued_in_range": {
            "total": issued_totals["total"] or 0,
            "level_1": issued_totals["level_1"] or 0,
            "level_2": issued_totals["level_2"] or 0,
            "level_3": issued_totals["level_3"] or 0,
            "by_type": {
                "UNEXCUSED_FULL_DAY_ABSENCE": issued_totals["absence"] or 0,
                "MORNING_LATE_OCCURRENCES": issued_totals["morning_late"] or 0,
            },
        },
    }


def action_metrics(*, school, date_range, scope=None) -> dict:
    """عدّاد نشاط إداري فقط — كثرة الإجراءات ليست «نجاحًا» (بند 39)."""
    actions = StudentAction.objects.filter(
        school=school,
        status=StudentActionStatus.COMPLETED,
        performed_at__date__gte=date_range.from_date,
        performed_at__date__lte=date_range.to_date,
    )
    students = _scoped_students(school=school, date_range=date_range, scope=scope)
    if students is not None:
        actions = actions.filter(student_id__in=students)

    by_type = dict(
        actions.values_list("action_type").annotate(total=Count("id")).values_list(
            "action_type", "total"
        )
    )
    return {
        "total": sum(by_type.values()),
        "by_type": {value: by_type.get(value, 0) for value, _ in StudentActionType.choices},
    }


def document_metrics(*, school, date_range, scope=None) -> dict:
    """مستندات أُنشئت داخل النطاق — السجل لا عدد مرات التنزيل (بند 41)."""
    documents = GeneratedDocument.objects.filter(
        school=school,
        created_at__date__gte=date_range.from_date,
        created_at__date__lte=date_range.to_date,
    )
    students = _scoped_students(school=school, date_range=date_range, scope=scope)
    if students is not None:
        documents = documents.filter(student_id__in=students)

    by_type = dict(
        documents.filter(status=DocumentStatus.READY)
        .values_list("document_type")
        .annotate(total=Count("id"))
        .values_list("document_type", "total")
    )
    status_totals = documents.aggregate(
        ready=Count("id", filter=Q(status=DocumentStatus.READY)),
        pending=Count("id", filter=Q(status=DocumentStatus.PENDING)),
        failed=Count("id", filter=Q(status=DocumentStatus.FAILED)),
    )
    return {
        "ready": status_totals["ready"] or 0,
        "pending": status_totals["pending"] or 0,
        "failed": status_totals["failed"] or 0,
        "by_type": {value: by_type.get(value, 0) for value, _ in DocumentType.choices},
    }


def referral_metrics(*, school, date_range, scope=None) -> dict:
    """إحالات المدرسة كاملة — لا نطاق «ما يراه المستخدم» في لوحة الإدارة.

    الإنشاء داخل النطاق، والمفتوح حاليًا لحظي (حالة قائمة لا حدث مؤرخ).
    """
    created = StudentReferral.objects.filter(
        school=school,
        created_at__date__gte=date_range.from_date,
        created_at__date__lte=date_range.to_date,
    )
    students = _scoped_students(school=school, date_range=date_range, scope=scope)
    if students is not None:
        created = created.filter(student_id__in=students)

    totals = created.aggregate(
        total=Count("id"),
        new=Count("id", filter=Q(status=ReferralStatus.PENDING_VICE)),
        under_vice_review=Count(
            "id", filter=Q(status=ReferralStatus.UNDER_VICE_REVIEW)
        ),
        referred=Count("id", filter=Q(status=ReferralStatus.REFERRED)),
        acknowledged=Count("id", filter=Q(status=ReferralStatus.ACKNOWLEDGED)),
        closed=Count("id", filter=Q(status=ReferralStatus.CLOSED)),
        cancelled=Count("id", filter=Q(status=ReferralStatus.CANCELLED)),
    )
    by_category = dict(
        created.values_list("category").annotate(total=Count("id")).values_list(
            "category", "total"
        )
    )
    by_source = dict(
        created.values_list("source_type").annotate(total=Count("id")).values_list(
            "source_type", "total"
        )
    )

    open_now = StudentReferral.objects.filter(school=school, status__in=OPEN_STATUSES)
    if students is not None:
        open_now = open_now.filter(student_id__in=students)
    open_totals = open_now.aggregate(
        open_total=Count("id"),
        unassigned=Count(
            "id",
            filter=Q(assigned_vice_membership__isnull=True)
            & Q(status=ReferralStatus.PENDING_VICE),
        ),
    )
    return {
        "created_in_range": {
            "total": totals["total"] or 0,
            "new": totals["new"] or 0,
            "under_vice_review": totals["under_vice_review"] or 0,
            "referred": totals["referred"] or 0,
            "acknowledged": totals["acknowledged"] or 0,
            "closed": totals["closed"] or 0,
            "cancelled": totals["cancelled"] or 0,
        },
        "by_category": by_category,
        "by_source": by_source,
        "open_now": open_totals["open_total"] or 0,
        "unassigned_now": open_totals["unassigned"] or 0,
    }


def counseling_metrics(*, school, date_range, scope=None) -> dict:
    """مؤشرات الحالات الإرشادية — فاصل تكامل المرحلة 14.

    تطبيق `counseling` غير موجود في هذا الأساس، فتعيد اللوحة `available=false`
    بدل رقم كاذب أو انهيار. عند دمج م14 يُوصل هنا دون تغيير في الواجهة أو العقد.
    """
    from django.apps import apps

    if not apps.is_installed("counseling"):
        return {
            "available": False,
            "reason": "COUNSELING_MODULE_NOT_INSTALLED",
            "open_cases": None,
            "waiting_teacher_responses": None,
            "overdue_activities": None,
        }
    # يُنفذ عند توفر التطبيق — يُبقى الاستيراد كسولًا حتى لا يفشل الاستيراد أصلًا
    from school_dashboard.selectors import counseling_bridge

    return counseling_bridge.metrics(school=school, date_range=date_range, scope=scope)
