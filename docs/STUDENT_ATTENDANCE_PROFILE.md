# Student Attendance Profile

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

`from_date` and `to_date` are ISO dates. Missing dates use the active academic year. A request is limited to 366 days and invalid ranges return `INVALID_ATTENDANCE_DATE_RANGE` or `ATTENDANCE_PROFILE_RANGE_TOO_LARGE`. Detail endpoints use 25, 50, or 100 item pages.

## Attendance Semantics

The summary is aggregated from `DailyAttendanceSummary`; it does not recalculate FULL or PARTIAL in the view. FULL and PARTIAL exclude UNDETERMINED. The latter has an independent count and produces an incomplete-data banner. Period absence and lateness use submitted sessions and `AttendanceMark`; late minutes remain numeric in the API and are formatted in the frontend.

Daily history is newest first. Day detail uses `AttendanceDayContext.schedule_snapshot` and `AttendanceSession.bell_period_snapshot`, never the current bell schedule. A submitted session without a mark derives PRESENT. A missing or IN_PROGRESS session derives NOT_RECORDED. Historical section names come from the summary's dated section snapshot.

Attendance changes are history only and do not calculate current state. Actors use the school's `StaffProfile.display_name`; reasons are omitted when empty. Internal status codes are translated to Arabic labels in the API/UI.

## Frontend

The profile is at `/students/{studentId}/attendance` and is linked from student search results. Tabs are lazy TanStack Query requests: summary, days, period absences, period lates, and manager/vice-principal-only changes. Keys include school ID, student ID, and both date boundaries. School switching removes all non-`me` queries, preventing a stale profile flash. The UI shows the student's current status and enrollment, but historical rows retain their dated section.

Morning attendance is integrated from `SchoolArrival` as `{ "status": "AVAILABLE", "morning_late_occurrences": 0, "morning_late_minutes": 0 }` when the source is available. The UI keeps morning lateness separate from period lateness and exposes a lazy morning history tab.

## Integration With Phase 8.5

After merging Phase 8.5:

1. Rebase Phase 9 and resolve documentation/navigation conflicts.
2. Connect the summary service to `SchoolArrival` data.
3. Add morning late cards and a morning-late history section.
4. Keep morning and period lateness as separate metrics.
5. Run full backend/frontend regression and combined E2E scenarios.

The expected change boundary is the profile summary service plus the morning section; the page and existing period tabs should remain intact.

## Performance and Privacy

Summary queries use database aggregation. Detail lists are paginated and use `select_related`/`prefetch_related` to avoid per-row identity or actor queries. No profile-view audit noise is generated. Benchmarking and query-count verification require the project PostgreSQL/Docker services to be available.

## Deferred Work

Excuses, warnings, actions, referrals, documents, exports, notifications, WebSockets, and biometric/device models are outside Phase 9.
