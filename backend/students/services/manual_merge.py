"""Manager-reviewed student merge. A preview is required before any write."""

import hashlib
import json
from collections import defaultdict
from datetime import timedelta

from django.core import signing
from django.db import transaction
from django.utils import timezone

from attendance.models import AttendanceMark, DailyAttendanceSummary
from audit.models import AuditAction
from audit.services import record_event
from common.errors import ApiError
from parents.access import lock_parent_school
from parents.models import GuardianStudentRelation
from students.management.commands.audit_student_reconciliation import audit_group
from students.models import (
    EnrollmentStatus,
    Student,
    StudentEnrollment,
    StudentImportJob,
    StudentStatus,
)

TOKEN_SALT = "students.manual-merge.v1"  # noqa: S105 - Django signing namespace, not a secret
TOKEN_MAX_AGE_SECONDS = 600
MOVABLE_RELATIONS = {
    "students.StudentEnrollment",
    "attendance.DailyAttendanceSummary",
    "attendance.AttendanceMark",
}
# These reviews remain attached to archived sources; they grant no access and move nowhere.
RETAINED_SOURCE_RELATIONS = {"parents.GuardianContactReview"}


def _error(code, message, *, status_code=400):
    raise ApiError(code, message, status_code=status_code)


def _normal_name(value):
    return " ".join(value.split())


def _row_snapshot(row, fields):
    return [getattr(row, field) for field in fields]


def _evidence_dates(student_id, section_id, summaries, marks):
    dates = [
        row.attendance_date
        for row in summaries
        if row.student_id == student_id and row.section_id == section_id
    ]
    dates.extend(
        row.session.attendance_date
        for row in marks
        if row.student_id == student_id and row.session.section_id == section_id
    )
    return dates


def build_manual_merge_plan(*, school, ids):
    """Return a read-only plan; ambiguous history becomes a visible blocker."""
    if not 2 <= len(ids) <= 10 or len(ids) != len(set(ids)):
        _error("INVALID_MERGE_SELECTION", "حدد سجلًا معتمدًا ومن سجل إلى تسعة سجلات أخرى.")
    students = list(Student.objects.filter(school=school, pk__in=ids).order_by("pk"))
    if len(students) != len(ids):
        _error("STUDENT_NOT_FOUND", "أحد السجلات لا يتبع هذه المدرسة.", status_code=404)
    by_id = {student.pk: student for student in students}
    target = by_id[ids[0]]
    sources = [by_id[item] for item in ids[1:]]
    blockers = []
    warnings = []
    if GuardianStudentRelation.objects.filter(student__in=sources).exists():
        blockers.append(
            "توجد علاقات أولياء أمور في السجلات المصدر؛ راجعها وألغها صراحة قبل الدمج. "
            "لا تنقل العلاقات أو تمنح وصولًا إلى السجل المعتمد تلقائيًا."
        )
    if any(row.status != StudentStatus.ACTIVE or row.merged_into_id for row in students):
        blockers.append("يجب أن تكون جميع السجلات نشطة وغير مدمجة سابقًا.")
    if len({_normal_name(row.full_name) for row in students}) != 1:
        blockers.append("أسماء السجلات مختلفة؛ صحح الاسم وتحقق من الهوية أولًا.")
    guardians = {_normal_name(row.guardian_name) for row in students if row.guardian_name.strip()}
    if len(guardians) > 1:
        blockers.append("أسماء أولياء الأمور مختلفة؛ راجع البيانات قبل الدمج.")
    if StudentImportJob.objects.filter(
        school=school, status__in=["PROCESSING", "IMPORTING"]
    ).exists():
        blockers.append("يوجد استيراد طلاب قيد التنفيذ؛ انتظر اكتماله ثم أعد المعاينة.")
    if len({row.student_number for row in students if row.student_number}) > 1:
        warnings.append("الأرقام الأكاديمية مختلفة؛ سيبقى الرقم الأكاديمي في السجل المعتمد.")

    report = audit_group(ids, school_id=school.pk)
    for relation in report["relations"]:
        if relation["model"] not in MOVABLE_RELATIONS | RETAINED_SOURCE_RELATIONS and any(
            relation["counts"].get(source.pk, 0) for source in sources
        ):
            blockers.append(
                f"توجد بيانات مرتبطة في {relation['model']}؛ تحتاج تسوية مخصصة قبل الدمج."
            )

    enrollments = list(
        StudentEnrollment.objects.filter(student_id__in=ids)
        .select_related("grade", "section", "academic_year")
        .order_by("pk")
    )
    summaries = list(DailyAttendanceSummary.objects.filter(student_id__in=ids).order_by("pk"))
    marks = list(
        AttendanceMark.objects.filter(student_id__in=ids).select_related("session").order_by("pk")
    )
    active_by_student = defaultdict(list)
    for enrollment in enrollments:
        if enrollment.status == EnrollmentStatus.ACTIVE:
            active_by_student[enrollment.student_id].append(enrollment)
    if any(len(active_by_student[row.pk]) != 1 for row in students):
        blockers.append("يجب أن يكون لكل سجل قيد دراسي نشط واحد فقط.")
    target_active = (
        active_by_student[target.pk][0] if len(active_by_student[target.pk]) == 1 else None
    )

    duplicate_summaries = []
    kept_summaries = []
    daily_conflicts = []
    summaries_by_day = defaultdict(list)
    for row in summaries:
        summaries_by_day[row.attendance_date].append(row)
    for day, rows in sorted(summaries_by_day.items()):
        if len(rows) > 1:
            facts = {
                (
                    row.section_id,
                    row.academic_year_id,
                    row.expected_periods,
                    row.absence_status,
                    row.absent_periods,
                    row.excused_absent_periods,
                    row.unexcused_absent_periods,
                )
                for row in rows
            }
            if len(facts) != 1 or any(
                row.present_periods != row.submitted_periods - row.absent_periods for row in rows
            ):
                daily_conflicts.append(day.isoformat())
        chosen = max(
            rows,
            key=lambda row: (
                row.submitted_periods,
                row.student_id == target.pk,
                row.calculated_at,
                row.pk,
            ),
        )
        kept_summaries.append(chosen)
        duplicate_summaries.extend(row for row in rows if row.pk != chosen.pk)
    if daily_conflicts:
        blockers.append(
            "تختلف بيانات الحضور في الأيام: "
            + "، ".join(daily_conflicts)
            + ". صحح الحضور أولًا ثم أعد المعاينة."
        )

    marks_by_session = defaultdict(list)
    for row in marks:
        marks_by_session[row.session_id].append(row)
    kept_marks = []
    duplicate_marks = []
    for rows in marks_by_session.values():
        if len({row.status for row in rows}) > 1:
            blockers.append("توجد علامتا حضور مختلفتان للحصة نفسها؛ صحح الحضور أولًا.")
        chosen = next((row for row in rows if row.student_id == target.pk), rows[0])
        kept_marks.append(chosen)
        duplicate_marks.extend(row for row in rows if row.pk != chosen.pk)

    move_enrollments = []
    discard_enrollments = []
    converted_enrollment = None
    history_adjustments = []
    proposed_start = target_active.enrolled_at if target_active else None
    if target_active:
        differing = []
        for source in sources:
            if len(active_by_student[source.pk]) != 1:
                continue
            row = active_by_student[source.pk][0]
            if row.academic_year_id != target_active.academic_year_id:
                blockers.append("القيود النشطة تنتمي إلى أعوام دراسية مختلفة.")
            elif (row.grade_id, row.section_id) != (
                target_active.grade_id,
                target_active.section_id,
            ):
                differing.append(row)
            else:
                discard_enrollments.append(row)
        if len(differing) > 1:
            blockers.append("يوجد أكثر من فصل تاريخي مختلف؛ راجع القيود الدراسية يدويًا.")
        elif differing:
            row = differing[0]
            dates = _evidence_dates(row.student_id, row.section_id, summaries, marks)
            if row.enrolled_at > target_active.enrolled_at or any(
                day < row.enrolled_at for day in dates
            ):
                blockers.append("ترتيب قيد الفصل المختلف لا يطابق تاريخ الحضور.")
            elif dates and max(dates) >= timezone.localdate():
                blockers.append("يوجد حضور حديث في فصل مختلف؛ صحح الفصل الحالي أولًا.")
            else:
                boundary = max(
                    target_active.enrolled_at,
                    max(dates) + timedelta(days=1) if dates else target_active.enrolled_at,
                )
                if row.enrolled_at < boundary:
                    proposed_start = boundary
                    converted_enrollment = row
                    move_enrollments.append(row)
                    history_adjustments.append(
                        {
                            "source_id": row.student_id,
                            "grade": row.grade.name,
                            "section": row.section.name,
                            "from_date": row.enrolled_at.isoformat(),
                            "through_date": (boundary - timedelta(days=1)).isoformat(),
                            "current_from_date": boundary.isoformat(),
                        }
                    )
                elif dates:
                    blockers.append("لا يمكن حفظ حضور الفصل المختلف ضمن فترة قيد صحيحة.")
                else:
                    discard_enrollments.append(row)
        if proposed_start:
            current_section_ids = {
                row.pk
                for row in students
                if len(active_by_student[row.pk]) == 1
                and active_by_student[row.pk][0].section_id == target_active.section_id
                and active_by_student[row.pk][0].grade_id == target_active.grade_id
            }
            current_dates = [
                day
                for student_id in current_section_ids
                for day in _evidence_dates(student_id, target_active.section_id, summaries, marks)
            ]
            if any(day < proposed_start for day in current_dates):
                blockers.append("يوجد حضور في الفصل المعتمد قبل تاريخ بدايته المقترح.")
        for row in enrollments:
            if row.student_id == target.pk or row.status == EnrollmentStatus.ACTIVE:
                continue
            if row.ended_at and row.enrolled_at < row.ended_at and row.ended_at <= proposed_start:
                move_enrollments.append(row)
            elif row.ended_at == row.enrolled_at:
                discard_enrollments.append(row)
            else:
                blockers.append("يوجد قيد دراسي تاريخي متداخل يحتاج مراجعة قبل الدمج.")
        if any(
            row.student_id == target.pk
            and row.status != EnrollmentStatus.ACTIVE
            and (row.ended_at is None or row.ended_at > proposed_start)
            for row in enrollments
        ):
            blockers.append("القيد التاريخي للسجل المعتمد يتداخل مع فصله الحالي.")
        intervals = [
            row
            for row in enrollments
            if row.student_id == target.pk
            and row.status != EnrollmentStatus.ACTIVE
            and row.ended_at
            and row.enrolled_at < row.ended_at
        ] + [row for row in move_enrollments if row is not converted_enrollment]
        if converted_enrollment:
            intervals.append(converted_enrollment)
        intervals.sort(key=lambda row: row.enrolled_at)
        for previous, current in zip(intervals, intervals[1:], strict=False):
            previous_end = proposed_start if previous is converted_enrollment else previous.ended_at
            if previous_end and previous_end > current.enrolled_at:
                blockers.append("تتداخل الفترات التاريخية للقيود الدراسية.")
                break

    latest_import = report["latest_import_job_id"]
    if latest_import and target.pk in _latest_missing_ids(school):
        warnings.append("الرقم المعتمد غير موجود في آخر ملف استيراد؛ سيبقى ظاهرًا في قائمته.")
    if duplicate_summaries or duplicate_marks:
        warnings.append("ستُزال قيود الحضور المتطابقة فقط، وتُحفظ تفاصيلها في سجل التدقيق.")

    snapshot = {
        "students": [
            _row_snapshot(
                row,
                (
                    "pk",
                    "school_id",
                    "updated_at",
                    "status",
                    "merged_into_id",
                    "full_name",
                    "guardian_name",
                    "guardian_mobile",
                    "guardian_contact_revision",
                    "student_number",
                    "national_id_lookup_hash",
                ),
            )
            for row in students
        ],
        "enrollments": [
            _row_snapshot(
                row,
                (
                    "pk",
                    "student_id",
                    "updated_at",
                    "academic_year_id",
                    "grade_id",
                    "section_id",
                    "status",
                    "enrolled_at",
                    "ended_at",
                ),
            )
            for row in enrollments
        ],
        "summaries": [
            _row_snapshot(
                row,
                (
                    "pk",
                    "student_id",
                    "updated_at",
                    "academic_year_id",
                    "section_id",
                    "attendance_date",
                    "expected_periods",
                    "submitted_periods",
                    "present_periods",
                    "absent_periods",
                    "excused_absent_periods",
                    "unexcused_absent_periods",
                    "absence_status",
                    "calculated_at",
                ),
            )
            for row in summaries
        ],
        "marks": [
            _row_snapshot(row, ("pk", "student_id", "updated_at", "session_id", "status"))
            for row in marks
        ],
        "relations": report["relations"],
        "latest_import_job_id": latest_import,
        "today": timezone.localdate(),
    }
    revision = hashlib.sha256(
        json.dumps(snapshot, default=str, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return {
        "can_merge": not blockers,
        "target_id": target.pk,
        "students": [
            {
                "id": row.pk,
                "full_name": row.full_name,
                "national_id_masked": row.national_id_masked,
                "student_number": row.student_number,
                "guardian_name": row.guardian_name,
                "grade": active_by_student[row.pk][0].grade.name
                if len(active_by_student[row.pk]) == 1
                else None,
                "section": active_by_student[row.pk][0].section.name
                if len(active_by_student[row.pk]) == 1
                else None,
            }
            for row in (by_id[item] for item in ids)
        ],
        "summary": {
            "archived_records": len(sources),
            "attendance_days": len(kept_summaries),
            "duplicate_daily_summaries": len(duplicate_summaries),
            "attendance_marks": len(kept_marks),
            "duplicate_attendance_marks": len(duplicate_marks),
            "historical_enrollments": len(move_enrollments),
        },
        "history_adjustments": history_adjustments,
        "blockers": blockers,
        "warnings": warnings,
        "revision": revision,
        "_kept_summaries": kept_summaries,
        "_duplicate_summaries": duplicate_summaries,
        "_kept_marks": kept_marks,
        "_duplicate_marks": duplicate_marks,
        "_move_enrollments": move_enrollments,
        "_discard_enrollments": discard_enrollments,
        "_converted_enrollment": converted_enrollment,
        "_target_active": target_active,
        "_proposed_start": proposed_start,
    }


def _latest_missing_ids(school):
    job = StudentImportJob.objects.filter(school=school, status="COMPLETED").order_by("-pk").first()
    return set((job.summary or {}).get("missing_ids", [])) if job else set()


def preview_manual_merge(*, school, actor, ids):
    plan = build_manual_merge_plan(school=school, ids=ids)
    public = {
        key: value for key, value in plan.items() if not key.startswith("_") and key != "revision"
    }
    public["confirmation_token"] = (
        signing.dumps(
            {
                "school_id": school.pk,
                "actor_id": actor.pk,
                "ids": ids,
                "revision": plan["revision"],
            },
            salt=TOKEN_SALT,
        )
        if plan["can_merge"]
        else None
    )
    return public


@transaction.atomic
def apply_manual_merge(*, school, actor, request, token):
    try:
        payload = signing.loads(token, salt=TOKEN_SALT, max_age=TOKEN_MAX_AGE_SECONDS)
    except signing.BadSignature:
        _error(
            "MERGE_PREVIEW_EXPIRED",
            "انتهت صلاحية المعاينة؛ أعد مراجعة السجلات.",
            status_code=409,
        )
    if payload.get("school_id") != school.pk or payload.get("actor_id") != actor.pk:
        _error("MERGE_PREVIEW_EXPIRED", "المعاينة لا تخص هذه الجلسة المدرسية.", status_code=409)
    ids = payload.get("ids")
    if (
        not isinstance(ids, list)
        or not 2 <= len(ids) <= 10
        or not all(isinstance(item, int) and item > 0 for item in ids)
    ):
        _error("MERGE_PREVIEW_EXPIRED", "المعاينة غير صالحة؛ أعد المحاولة.", status_code=409)
    # Imports hold the school before enrollment/student locks. Acquire it first
    # so a concurrent Noor commit cannot form the opposite lock cycle.
    lock_parent_school(school.pk)
    list(Student.objects.select_for_update().filter(school=school, pk__in=ids).order_by("pk"))
    list(StudentEnrollment.objects.select_for_update().filter(student_id__in=ids))
    list(DailyAttendanceSummary.objects.select_for_update().filter(student_id__in=ids))
    list(AttendanceMark.objects.select_for_update().filter(student_id__in=ids))
    plan = build_manual_merge_plan(school=school, ids=ids)
    if not plan["can_merge"] or plan["revision"] != payload.get("revision"):
        _error("MERGE_PREVIEW_EXPIRED", "تغيرت بيانات السجلات؛ أعد معاينة الدمج.", status_code=409)
    target = Student.objects.get(pk=ids[0], school=school)
    source_ids = ids[1:]
    discarded_summaries = [
        {
            "id": row.pk,
            "student_id": row.student_id,
            "day": row.attendance_date.isoformat(),
            "status": row.absence_status,
            "submitted": row.submitted_periods,
            "present": row.present_periods,
            "absent": row.absent_periods,
        }
        for row in plan["_duplicate_summaries"]
    ]
    discarded_marks = [
        {
            "id": row.pk,
            "student_id": row.student_id,
            "session_id": row.session_id,
            "status": row.status,
        }
        for row in plan["_duplicate_marks"]
    ]
    if discarded_summaries:
        DailyAttendanceSummary.objects.filter(
            pk__in=[row["id"] for row in discarded_summaries]
        ).delete()
    if discarded_marks:
        AttendanceMark.objects.filter(pk__in=[row["id"] for row in discarded_marks]).delete()
    DailyAttendanceSummary.objects.filter(
        pk__in=[row.pk for row in plan["_kept_summaries"]], student_id__in=source_ids
    ).update(student=target)
    AttendanceMark.objects.filter(
        pk__in=[row.pk for row in plan["_kept_marks"]], student_id__in=source_ids
    ).update(student=target)
    for row in plan["_move_enrollments"]:
        if row is plan["_converted_enrollment"]:
            StudentEnrollment.objects.filter(pk=row.pk).update(
                student=target,
                status=EnrollmentStatus.TRANSFERRED,
                ended_at=plan["_proposed_start"],
            )
        else:
            StudentEnrollment.objects.filter(pk=row.pk).update(student=target)
    if plan["_proposed_start"] != plan["_target_active"].enrolled_at:
        StudentEnrollment.objects.filter(pk=plan["_target_active"].pk).update(
            enrolled_at=plan["_proposed_start"]
        )
    if plan["_discard_enrollments"]:
        StudentEnrollment.objects.filter(
            pk__in=[row.pk for row in plan["_discard_enrollments"]]
        ).delete()
    now = timezone.now()
    Student.objects.filter(pk__in=source_ids, school=school).update(
        status=StudentStatus.ARCHIVED,
        merged_into=target,
        status_changed_at=now,
        status_changed_by=actor,
        exit_date=timezone.localdate(),
        exit_reason=f"دُمج هذا السجل بسجل الطالب رقم {target.pk}",
        updated_at=now,
    )
    record_event(
        AuditAction.STUDENT_UPDATED,
        request=request,
        actor=actor,
        school=school,
        target_type="Student",
        target_id=target.pk,
        metadata={
            "operation": "manual_student_merge",
            "source_ids": source_ids,
            "discarded_daily_summaries": discarded_summaries,
            "discarded_attendance_marks": discarded_marks,
            "moved_historical_enrollments": [row.pk for row in plan["_move_enrollments"]],
            "discarded_enrollments": [row.pk for row in plan["_discard_enrollments"]],
            "history_adjustments": plan["history_adjustments"],
        },
    )
    return {"target_id": target.pk, "archived_source_ids": source_ids, "summary": plan["summary"]}
