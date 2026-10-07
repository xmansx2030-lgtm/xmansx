"""Idempotent official-calendar synchronization and tenant-safe activation."""

import logging
from datetime import date
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone

from academics.ministry_models import (
    CalendarProfile,
    MinistryCalendarSnapshot,
    MinistryCalendarSync,
    SchoolCalendarPolicy,
)
from academics.models import AcademicYear, Semester
from academics.services import academic_years, semesters
from academics.services.live_schedule import publish_live_schedule_change
from academics.services.ministry_source import (
    SOURCE_PAGE,
    MinistrySourceError,
    fetch_ministry_calendar,
)
from audit.services import record_event
from common.errors import ApiError
from common.tenant_rls import tenant_context
from schools.models import School
from students.models import Student, StudentEnrollment

logger = logging.getLogger(__name__)
SYNC_LOCK_ID = 786231903


def today_in_riyadh():
    return timezone.localdate(timezone=ZoneInfo("Asia/Riyadh"))


def _current_calendar(snapshot, today):
    started = [c for c in snapshot.calendars if c["dates"]["year_start"] <= today.isoformat()]
    return max(started, key=lambda c: c["dates"]["year_start"], default=None)


def sync_ministry_calendar():
    """One process fetches; failed fetches retain the last snapshot and all school data."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s)", [SYNC_LOCK_ID])
        locked = cursor.fetchone()[0]
    if not locked:
        return {"status": "BUSY"}
    try:
        state, _ = MinistryCalendarSync.objects.get_or_create(key="NATIONAL")
        checked_at = timezone.now()
        try:
            fingerprint, documents, calendars = fetch_ministry_calendar()
        except MinistrySourceError as exc:
            state.checked_at, state.error_code = checked_at, exc.code
            state.save(update_fields=["checked_at", "error_code", "updated_at"])
            return {"status": "SOURCE_ERROR", "error_code": exc.code}
        with transaction.atomic():
            snapshot, created = MinistryCalendarSnapshot.objects.get_or_create(
                fingerprint=fingerprint, defaults={"documents": documents, "calendars": calendars}
            )
            state.snapshot, state.checked_at = snapshot, checked_at
            state.succeeded_at, state.error_code = checked_at, ""
            state.save()
            if created:
                record_event(
                    "MINISTRY_CALENDAR_FETCHED",
                    target_type="MinistryCalendarSnapshot",
                    target_id=snapshot.pk,
                    metadata={"fingerprint": fingerprint, "source_url": SOURCE_PAGE},
                )
        return {
            "status": "FETCHED",
            "snapshot_id": snapshot.pk,
            "calendars": [
                {
                    "name": c["name"],
                    "status": c["status"],
                    "missing": c["missing"],
                    "problems": c["problems"],
                }
                for c in calendars
            ],
        }
    finally:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock(%s)", [SYNC_LOCK_ID])


@transaction.atomic
def require_manual_calendar(*, school):
    # Share the school-row lock with scope changes and automated activation.
    School.objects.select_for_update().get(pk=school.pk)
    if SchoolCalendarPolicy.objects.filter(
        school=school, profile=CalendarProfile.NATIONAL
    ).exists():
        raise ApiError(
            "MINISTRY_CALENDAR_MANAGED",
            "مواعيد هذه المدرسة تُدار من التقويم الرسمي لوزارة التعليم.",
            409,
        )


@transaction.atomic
def configure_calendar_scope(*, school, actor, profile, scope_note, request=None):
    school = School.objects.select_for_update().get(pk=school.pk)
    if profile not in CalendarProfile.values:
        raise ApiError("VALIDATION_ERROR", "نطاق التقويم غير صحيح.")
    if profile != CalendarProfile.UNCONFIRMED and len(scope_note.strip()) < 10:
        raise ApiError(
            "CALENDAR_SCOPE_REQUIRED", "وثّق سبب مطابقة نطاق المدرسة لهذا التقويم قبل اعتماده."
        )
    policy, _ = SchoolCalendarPolicy.objects.get_or_create(school=school)
    previous = policy.profile
    policy.profile, policy.scope_note, policy.outcome = profile, scope_note.strip(), ""
    policy.save()
    record_event(
        "SCHOOL_CALENDAR_SCOPE_CHANGED",
        actor=actor,
        request=request,
        school=school,
        target_type="SchoolCalendarPolicy",
        target_id=policy.pk,
        metadata={"from": previous, "to": profile, "scope_note": policy.scope_note},
    )
    return policy


def _matches(year, calendar):
    dates = calendar["dates"]
    if (
        year.start_date.isoformat() != dates["year_start"]
        or year.end_date.isoformat() != dates["year_end"]
    ):
        return False
    existing = list(year.semesters.all())
    return len(existing) <= 2 and all(
        semester.sequence in (1, 2)
        and semester.start_date.isoformat() == dates[f"semester_{semester.sequence}_start"]
        and semester.end_date.isoformat() == dates[f"semester_{semester.sequence}_end"]
        for semester in existing
    )


def _align_future_boundaries(year, calendar, today):
    dates = calendar["dates"]
    changes = []
    expected_year = {
        "start_date": date.fromisoformat(dates["year_start"]),
        "end_date": date.fromisoformat(dates["year_end"]),
    }
    changes.append((year, expected_year))
    terms = list(year.semesters.select_for_update().all())
    if len(terms) > 2 or any(term.sequence not in (1, 2) for term in terms):
        return False
    for term in terms:
        changes.append(
            (
                term,
                {
                    "start_date": date.fromisoformat(dates[f"semester_{term.sequence}_start"]),
                    "end_date": date.fromisoformat(dates[f"semester_{term.sequence}_end"]),
                },
            )
        )
    # Validate every change before writing any field. Historical boundaries stay fixed.
    for instance, desired in changes:
        for field, value in desired.items():
            previous = getattr(instance, field)
            if value != previous and (
                value <= today or previous <= today or instance.status == "CLOSED"
            ):
                return False
    for instance, desired in changes:
        changed = {
            field: {"from": getattr(instance, field).isoformat(), "to": value.isoformat()}
            for field, value in desired.items()
            if value != getattr(instance, field)
        }
        if not changed:
            continue
        for field, value in desired.items():
            setattr(instance, field, value)
        instance.save(update_fields=[*changed, "updated_at"])
        record_event(
            "MINISTRY_CALENDAR_FUTURE_DATES_UPDATED",
            school=year.school,
            target_type=type(instance).__name__,
            target_id=instance.pk,
            metadata={"changed": changed, "source_url": SOURCE_PAGE},
        )
    return True


def _ensure_year(school, snapshot, calendar, today):
    dates = calendar["dates"]
    # Match by dates, not display names or Hijri-list IDs. Never adopt an ambiguous year.
    candidates = list(
        AcademicYear.objects.select_for_update().filter(
            school=school, start_date=dates["year_start"]
        )
    )
    if len(candidates) > 1:
        raise ApiError("CALENDAR_YEAR_CONFLICT", "يوجد أكثر من عام دراسي بتاريخ البداية نفسه.", 409)
    if candidates:
        year = candidates[0]
        if year.status in ("CLOSED", "ARCHIVED") or (
            not _matches(year, calendar) and not _align_future_boundaries(year, calendar, today)
        ):
            raise ApiError(
                "CALENDAR_EXISTING_DATES_CONFLICT",
                "التقويم القائم يحتاج مراجعة إدارة المنصة قبل مطابقته بالمصدر.",
                409,
            )
    else:
        # Existing date overlaps indicate that adopting a new ID could detach rosters.
        if AcademicYear.objects.filter(
            school=school,
            start_date__lte=dates["year_end"],
            end_date__gte=dates["year_start"],
            status__in=["UPCOMING", "ACTIVE"],
        ).exists():
            raise ApiError("CALENDAR_EXISTING_DATES_CONFLICT", "يوجد عام قائم بحدود مختلفة.", 409)
        year = academic_years.create_year(
            school=school,
            actor=None,
            name=calendar["name"],
            start_date=date.fromisoformat(dates["year_start"]),
            end_date=date.fromisoformat(dates["year_end"]),
        )
    if year.ministry_snapshot_id != snapshot.pk:
        year.ministry_snapshot = snapshot
        year.save(update_fields=["ministry_snapshot", "updated_at"])
        record_event(
            "ACADEMIC_YEAR_MINISTRY_LINKED",
            school=school,
            target_type="AcademicYear",
            target_id=year.pk,
            metadata={"snapshot_id": snapshot.pk, "fingerprint": snapshot.fingerprint},
        )
    for sequence, name in ((1, "الفصل الدراسي الأول"), (2, "الفصل الدراسي الثاني")):
        if not year.semesters.filter(sequence=sequence).exists():
            semesters.create_semester(
                year=year,
                actor=None,
                name=name,
                sequence=sequence,
                start_date=date.fromisoformat(dates[f"semester_{sequence}_start"]),
                end_date=date.fromisoformat(dates[f"semester_{sequence}_end"]),
            )
    return year


def _enrollments_ready(school, year, today):
    # No copying students, guessing next grades, or rewriting enrollment history.
    expected = Student.objects.filter(school=school, status="ACTIVE")
    enrolled = StudentEnrollment.objects.filter(
        school=school,
        academic_year=year,
        status="ACTIVE",
        enrolled_at__lte=today,
        ended_at__isnull=True,
        grade__school=school,
        grade__is_active=True,
        section__school=school,
        section__is_active=True,
    ).values_list("student_id", flat=True)
    return not expected.exclude(id__in=enrolled).exists()


@transaction.atomic
def apply_school_calendar(*, school, snapshot, today=None):
    today = today or today_in_riyadh()
    school = School.objects.select_for_update().get(pk=school.pk)
    policy = SchoolCalendarPolicy.objects.select_for_update().filter(school=school).first()
    if policy is None or policy.profile != CalendarProfile.NATIONAL or school.status != "ACTIVE":
        return "SCOPE_NOT_APPLICABLE"
    current = _current_calendar(snapshot, today)
    outcome = "NO_CURRENT_CALENDAR"
    changed = False
    try:
        # Savepoint: conflicts roll back the whole school, including partially created years.
        with transaction.atomic():
            for calendar in snapshot.calendars:
                if (
                    calendar["status"] != "READY"
                    or calendar["dates"]["year_end"] < today.isoformat()
                ):
                    continue
                _ensure_year(school, snapshot, calendar, today)
            if current is not None:
                if current["status"] != "READY":
                    outcome = (
                        "SOURCE_INCOMPLETE"
                        if current["status"] == "INCOMPLETE"
                        else "SOURCE_INVALID"
                    )
                elif current["dates"]["year_end"] < today.isoformat():
                    outcome = "BETWEEN_ACADEMIC_YEARS"
                    changed = _close_ended_semesters(school, today)
                else:
                    year = _ensure_year(school, snapshot, current, today)
                    from attendance.models import AttendanceSession

                    day_used_by_other_year = (
                        AttendanceSession.objects.filter(school=school, attendance_date=today)
                        .exclude(academic_year=year)
                        .exists()
                    )
                    if year.status != "ACTIVE" and day_used_by_other_year:
                        outcome = "DAY_ALREADY_IN_USE"
                    elif year.status != "ACTIVE" and not _enrollments_ready(school, year, today):
                        outcome = "ENROLLMENTS_NOT_READY"
                    else:
                        changed = _close_ended_semesters(school, today)
                        if year.status != "ACTIVE":
                            academic_years.activate_year(year=year, actor=None)
                            _refresh_today_context(school, year, today)
                            changed = True
                        target = year.semesters.filter(
                            start_date__lte=today, end_date__gte=today
                        ).first()
                        if target and target.status != "ACTIVE":
                            semesters.activate_semester(semester=target, actor=None)
                            changed = True
                        outcome = "APPLIED" if target else "BETWEEN_SEMESTERS"
    except ApiError as exc:
        outcome = exc.code
        changed = False
    if changed:
        publish_live_schedule_change(school_id=school.pk)
    policy.checked_at = timezone.now()
    if policy.outcome != outcome:
        record_event(
            "MINISTRY_CALENDAR_APPLICATION",
            school=school,
            target_type="SchoolCalendarPolicy",
            target_id=policy.pk,
            metadata={"outcome": outcome, "snapshot_id": snapshot.pk},
        )
    policy.outcome = outcome
    policy.save(update_fields=["outcome", "checked_at", "updated_at"])
    return outcome


def _refresh_today_context(school, year, today):
    from attendance.models import AttendanceDayContext
    from attendance.services.day_context import build_day_schedule_snapshot
    from schools.services.settings import get_or_create_settings

    # Claim today's pristine context before a concurrent dashboard read can freeze
    # the old year. The unique key also handles a reader that started before activation.
    context, _ = AttendanceDayContext.objects.select_for_update().get_or_create(
        school=school,
        attendance_date=today,
        defaults={
            "academic_year": year,
            "schedule_snapshot": build_day_schedule_snapshot(school, today),
            "timezone_snapshot": get_or_create_settings(school=school).timezone,
        },
    )
    if context.academic_year_id != year.pk:
        context.academic_year = year
        context.schedule_snapshot = build_day_schedule_snapshot(school, today)
        context.save(update_fields=["academic_year", "schedule_snapshot", "updated_at"])
        record_event(
            "MINISTRY_CALENDAR_PRISTINE_CONTEXT_UPDATED",
            school=school,
            target_type="AttendanceDayContext",
            target_id=context.pk,
            metadata={"academic_year_id": year.pk},
        )


def _close_ended_semesters(school, today):
    ended = list(
        Semester.objects.select_for_update().filter(
            school=school, status="ACTIVE", end_date__lt=today
        )
    )
    for semester in ended:
        semester.status = "CLOSED"
        semester.save(update_fields=["status", "updated_at"])
        record_event(
            "SEMESTER_CLOSED",
            school=school,
            target_type="Semester",
            target_id=semester.pk,
            metadata={"reason": "MINISTRY_CALENDAR_DATE"},
        )
    return bool(ended)


@transaction.atomic
def apply_ministry_calendars():
    if not settings.MINISTRY_CALENDAR_ENABLED:
        return {"status": "DISABLED"}
    # Synchronization and application cannot race on different source snapshots.
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_xact_lock(%s)", [SYNC_LOCK_ID])
        if not cursor.fetchone()[0]:
            return {"status": "BUSY"}
    state = MinistryCalendarSync.objects.select_related("snapshot").filter(key="NATIONAL").first()
    if not state or not state.snapshot_id:
        return {"status": "NOT_SYNCED"}
    # Do not switch calendars using an errored or old source. Current operations continue.
    if (
        state.error_code
        or state.succeeded_at is None
        or (timezone.now() - state.succeeded_at).total_seconds() > 48 * 3600
    ):
        return {"status": "SOURCE_UNAVAILABLE"}
    with tenant_context(bypass=True):
        school_ids = list(
            SchoolCalendarPolicy.objects.filter(
                profile=CalendarProfile.NATIONAL, school__status="ACTIVE"
            ).values_list("school_id", flat=True)
        )
    results = {}
    for school_id in school_ids:
        with tenant_context(school_id=school_id):
            try:
                results[str(school_id)] = apply_school_calendar(
                    school=School.objects.get(pk=school_id), snapshot=state.snapshot
                )
            except Exception:
                logger.exception("Official calendar application failed for school %s", school_id)
                results[str(school_id)] = "APPLICATION_ERROR"
    return {"status": "FINISHED", "schools": results}


def calendar_status(*, school=None):
    state = MinistryCalendarSync.objects.select_related("snapshot").filter(key="NATIONAL").first()
    policy = SchoolCalendarPolicy.objects.filter(school=school).first() if school else None
    snapshot = state.snapshot if state and state.snapshot_id else None
    current = _current_calendar(snapshot, today_in_riyadh()) if snapshot else None
    error_code = state.error_code if state else "NOT_SYNCED"
    if (
        state
        and not error_code
        and (
            state.succeeded_at is None
            or (timezone.now() - state.succeeded_at).total_seconds() > 48 * 3600
        )
    ):
        error_code = "MINISTRY_SOURCE_STALE"
    public_calendars = (
        [
            {key: value for key, value in calendar.items() if key != "events"}
            for calendar in snapshot.calendars
        ]
        if snapshot
        else []
    )
    return {
        "source_url": SOURCE_PAGE,
        "automatic_enabled": settings.MINISTRY_CALENDAR_ENABLED,
        "checked_at": state.checked_at if state else None,
        "succeeded_at": state.succeeded_at if state else None,
        "error_code": error_code,
        "fingerprint": snapshot.fingerprint if snapshot else None,
        "profile": policy.profile if policy else CalendarProfile.UNCONFIRMED,
        "scope_note": policy.scope_note if policy else "",
        "outcome": policy.outcome if policy else "",
        "application_checked_at": policy.checked_at if policy else None,
        "current_calendar": {key: value for key, value in current.items() if key != "events"}
        if current
        else None,
        "calendars": public_calendars,
    }
