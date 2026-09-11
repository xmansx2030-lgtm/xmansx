# Student Attendance Profile

> تحديث المرحلة 11: أضيف تبويب **الإنذارات** — ملخص (إنذارات الغياب/التأخر) وقائمة
> الإنذارات الصادرة، مع الفصل الصريح بين قيمة المقياس وقت الإصدار والقيمة الحالية
> (التفصيل: [STUDENT_WARNINGS.md](STUDENT_WARNINGS.md)). المرشد يقرأ التبويب ولا يصدر.

> تحديث المرحلة 12: أضيف تبويبا **الإجراءات** و**المستندات** — تسجيل ما فُعل تجاه
> الطالب، وإنشاء/إعادة طباعة مستنداته الرسمية من نسخها المخزنة
> ([STUDENT_ACTIONS.md](STUDENT_ACTIONS.md) و[GENERATED_DOCUMENTS.md](GENERATED_DOCUMENTS.md)).
> المرشد يقرأ التبويبين ولا ينشئ ولا ينزّل ملفات.

> أضيف تبويب **الاستئذانات** للمدير والوكيل، ويعرض سبب الاستئذان وتاريخه واليوم
> ووقت خروج الطالب والموظف الذي سجله، مع بقاء السجل الملغى وسبب إلغائه.

## Scope

Phase 9 is a read-heavy profile built only on the Phase 8 records: `Student`, `StudentEnrollment`, `Grade`, `Section`, `AttendanceDayContext`, `AttendanceSession`, `AttendanceMark`, `AttendanceChange`, and `DailyAttendanceSummary`. It adds no model and no migration.

The profile is tenant-scoped by `request.school`. A student purged from the database is naturally unavailable and returns 404. Guardian fields, plaintext national IDs, lookup hashes, and device credentials are not part of the profile response.

## Search

- `GET /api/v1/students/search/`
- Name search uses `full_name__icontains` inside the active school.
- National ID search normalizes input and compares the HMAC lookup hash exactly; it never decrypts all students.
- Active students are the default. A status filter is available for authorized inactive-student workflows.
- Pagination is mandatory and the response contains only a masked national ID.

## Permissions

`SCHOOL_MANAGER` and `VICE_PRINCIPAL` can read the complete profile and change history. `COUNSELOR` can read the basic profile and attendance detail but cannot read attendance changes. `TEACHER` has no directory search or arbitrary profile access.

## APIs

- `GET /api/v1/students/{id}/attendance-profile/`
- `GET /api/v1/students/{id}/attendance-days/`
- `GET /api/v1/students/{id}/attendance-days/{date}/`
- `GET /api/v1/students/{id}/attendance-period-absences/`
- `GET /api/v1/students/{id}/attendance-period-lates/`
- `GET /api/v1/students/{id}/attendance-changes/`
- `GET /api/v1/student-leaves/?student={id}`

`from_date` and `to_date` are ISO dates. Missing dates use the active academic year. A request is limited to 366 days and invalid ranges return `INVALID_ATTENDANCE_DATE_RANGE` or `ATTENDANCE_PROFILE_RANGE_TOO_LARGE`. Detail endpoints use 25, 50, or 100 item pages.

## Attendance Semantics

The summary is aggregated from `DailyAttendanceSummary`; it does not recalculate FULL or PARTIAL in the view. FULL and PARTIAL exclude UNDETERMINED. The latter has an independent count and produces an incomplete-data banner. Period absence uses submitted sessions and `AttendanceMark`; morning lateness comes only from `SchoolArrival`.

Daily history is newest first. Day detail uses `AttendanceDayContext.schedule_snapshot` and `AttendanceSession.bell_period_snapshot`, never the current bell schedule. A submitted session without a mark derives PRESENT. A missing or IN_PROGRESS session derives NOT_RECORDED. Historical section names come from the summary's dated section snapshot.

Attendance changes are history only and do not calculate current state. Actors use the school's `StaffProfile.display_name`; reasons are omitted when empty. Internal status codes are translated to Arabic labels in the API/UI.

## Frontend

The profile is at `/students/{studentId}/attendance` and is linked from student search results. Tabs are lazy TanStack Query requests: summary, days, period absences, morning attendance, and manager/vice-principal-only changes. Keys include school ID, student ID, and both date boundaries. School switching removes all non-`me` queries, preventing a stale profile flash. The UI shows the student's current status and enrollment, but historical rows retain their dated section.

Morning attendance is integrated from `SchoolArrival` as `{ "status": "AVAILABLE", "morning_late_occurrences": 0, "morning_late_minutes": 0 }` when the source is available. `SchoolArrival` is the sole lateness source, and the UI exposes its history in a lazy tab.

## Integration With Phase 8.5

After merging Phase 8.5:

1. Rebase Phase 9 and resolve documentation/navigation conflicts.
2. Connect the summary service to `SchoolArrival` data.
3. Add morning late cards and a morning-late history section.
4. Keep `SchoolArrival` as the sole lateness metric.
5. Run full backend/frontend regression and combined E2E scenarios.

The expected change boundary is the profile summary service plus the morning section; the page and existing period tabs should remain intact.

## Performance and Privacy

Summary queries use database aggregation. Detail lists are paginated and use `select_related`/`prefetch_related` to avoid per-row identity or actor queries. No profile-view audit noise is generated. Benchmarking and query-count verification require the project PostgreSQL/Docker services to be available.

## Phase 10 Additions — Excuse Classification

The profile keeps every Phase 9 total unchanged and layers the administrative
classification on top of it. `attendance-profile/` gained
`excused_absent_periods`, `unexcused_absent_periods`, `excused_full_absence_days`,
`unexcused_full_absence_days`, and `mixed_full_absence_days`; `attendance-days/`
rows gained `excused_absent_periods` / `unexcused_absent_periods`; and each period
in `attendance-days/{date}/` gained `excused` (`true`/`false` for absences,
`null` otherwise).

The UI shows the excused/unexcused cards **next to** the totals, never instead of
them: a student with 8 full-absence days is displayed as 8 total with a 3 excused
/ 5 unexcused breakdown, so an approved excuse never makes the absence disappear.
Mixed full-absence days get their own note and are counted in neither bucket.

An "الأعذار" tab lists the student's excuses (period, type, status, covered
periods, recorder, approver, attachment count) and opens the shared excuse detail
card. Managers and vice-principals also get quick-create buttons on an absent day
and on any unexcused period; counselors see the tab read-only and cannot open
attachments. Full domain rules are in [ABSENCE_EXCUSES.md](ABSENCE_EXCUSES.md).

## Deferred Work

Warnings, actions, referrals, documents, exports, notifications, WebSockets, and
biometric/device models are outside Phase 9 (excuses landed in Phase 10).
