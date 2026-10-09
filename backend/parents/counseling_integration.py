"""Family-facing publications in the counselor's private case workflow."""

from django.db.models import CharField, Count, Exists, F, Max, OuterRef, Q, Value
from django.db.models.functions import Cast, Concat
from django.utils import timezone

from counseling.models import LIVE_CASE_STATUSES, CounselorCase
from counseling.services.cases import log_case_event, touch_case
from parents.request_models import FamilyPublication, ParentNotification


def record_family_case_event(publication, event_type, *, membership=None):
    """Called inside the existing school/student-locked write transaction."""
    if not publication.case_id:
        return
    case = (
        CounselorCase.objects.select_for_update()
        .filter(
            id=publication.case_id,
            school_id=publication.school_id,
            student_id=publication.student_id,
        )
        .first()
    )
    if case is None:
        return
    log_case_event(
        case=case,
        event_type=event_type,
        membership=membership,
        metadata={"publication_id": publication.id, "title": publication.title},
    )
    touch_case(case)


def eligible_family_notifications(school_id):
    return ParentNotification.objects.filter(
        school_id=school_id,
        kind="FAMILY_PUBLICATION",
        requires_action=True,
        relation__school_id=school_id,
        relation__student__school_id=school_id,
        relation__status="ACTIVE",
        user_id=F("relation__user_id"),
        user__is_active=True,
    )


def attach_family_action_progress(publications, school_id):
    """One aggregate query for a page, rather than one query per publication."""
    keys = [f"publication:{obj.id}" for obj in publications]
    progress = (
        eligible_family_notifications(school_id)
        .filter(dedup_key__in=keys)
        .values(
            "dedup_key",
            "relation__student_id",
        )
        .annotate(
            action_count=Count("id"),
            completed_action_count=Count("id", filter=Q(action_completed_at__isnull=False)),
            action_completed_at=Max("action_completed_at"),
        )
    )
    indexed = {(row["dedup_key"], row["relation__student_id"]): row for row in progress}
    for obj in publications:
        obj.family_action_progress = indexed.get((f"publication:{obj.id}", obj.student_id), {})


def family_action_kpis(*, school, cases):
    pending = eligible_family_notifications(school.id).filter(
        dedup_key=OuterRef("notification_key"),
        relation__student_id=OuterRef("student_id"),
        action_completed_at__isnull=True,
    )
    publications = (
        FamilyPublication.objects.filter(
            school=school,
            case__in=cases.filter(status__in=LIVE_CASE_STATUSES),
            revoked_at__isnull=True,
        )
        .exclude(required_action="")
        .annotate(
            notification_key=Concat(Value("publication:"), Cast("id", output_field=CharField())),
        )
        .filter(Exists(pending))
    )
    counts = publications.aggregate(
        family_pending_actions=Count("id"),
        family_overdue_actions=Count("id", filter=Q(due_at__lt=timezone.now())),
    )
    return counts
