# PHASE 9 REPORT — Student Attendance Profile

## Status

Implementation complete on the isolated Phase 9 branch at the current repository state. The feature is ready for review; full integration is blocked until PostgreSQL/Docker credentials are available and Phase 8.5 is merged.

## Parallel-development base commit

`59d95eb feat: add attendance analytics and daily absence summaries` (`PHASE 8 COMPLETE`).

## Branch name

`feature/phase-9-student-profile`

## Files intentionally not touched

No files under `backend/devices/` were created or modified. No `AttendanceDevice`, `DeviceBridgeInstallation`, `DeviceEvent`, `StudentDeviceIdentity`, `SchoolArrival`, or `SchoolArrivalChange` models were added. Phase 8.5 in-progress changes under `schools/*` and `backend/devices/` remain uncommitted and untouched.

## Student search

Added `GET /api/v1/students/search/` with active status as the default, name `icontains`, exact normalized national-ID HMAC matching, tenant scoping, pagination, and masked identity output. Search result names link to the attendance profile.

## Student profile architecture

`students/services/attendance_profile.py` is the read-only boundary. It separates summary, daily history, day detail, period marks, and change history queries. No new business model or migration is required.

## Attendance summary

Summary is aggregated with database `Count`/`Sum` over `DailyAttendanceSummary`: FULL days, PARTIAL days, independent UNDETERMINED days, absent periods, period-late occurrences, and period-late minutes. No current-period count is multiplied by FULL days.

## Daily history and timeline

Daily history is paginated newest first. Day detail uses `AttendanceDayContext.schedule_snapshot` and submitted `AttendanceSession.bell_period_snapshot`. PRESENT is derived only from a submitted session without an exception mark; missing or IN_PROGRESS sessions are NOT_RECORDED. Historical section data comes from the dated summary section.

## Attendance changes

Manager and vice principal only. Change history uses `AttendanceChange`, school staff display names, optional reasons, and Arabic status labels. It is not used to derive current attendance.

## Inactive students and privacy

Profiles resolve all non-purged student statuses. The response includes status, masked national ID, student number, and current enrollment only; guardian data, plaintext IDs, encrypted IDs, lookup hashes, and device data are excluded.

## Permissions and isolation

Manager and vice principal: full profile and changes. Counselor: basic read profile and attendance details, no change history. Teacher: denied directory/profile access. All lookups require `request.school`; foreign IDs return 404.

## API endpoints

- `/api/v1/students/search/`
- `/api/v1/students/{id}/attendance-profile/`
- `/api/v1/students/{id}/attendance-days/`
- `/api/v1/students/{id}/attendance-days/{date}/`
- `/api/v1/students/{id}/attendance-period-absences/`
- `/api/v1/students/{id}/attendance-period-lates/`
- `/api/v1/students/{id}/attendance-changes/`

The new views have explicit drf-spectacular response serializers. Range errors are `INVALID_ATTENDANCE_DATE_RANGE` and `ATTENDANCE_PROFILE_RANGE_TOO_LARGE`; permission and tenant behavior use existing centralized mechanisms.

## Frontend

Added `/students/:studentId/attendance`, typed API functions, date presets/custom range, KPI cards, incomplete-data banner, lazy TanStack Query tabs, day detail timeline, period absences/lates, and manager/vice-principal change history. Query keys include school, student, `from_date`, and `to_date`. `SchoolSwitcher` already removes all non-`me` queries, so profiles cannot persist across school switches. Morning attendance is explicitly `NOT_AVAILABLE` with no fake zero values.

## Tests and validation

Added focused backend tests for summary aggregation, search masking/tenant scope, role denial, IDOR, and the morning placeholder. Validation completed:

- Backend profile modules compile.
- Backend profile lint passes after import cleanup.
- Django `check --deploy` passes.
- Frontend `typecheck` passes.
- Frontend `lint` passes.
- Frontend `build` passes.

The existing and new Django tests could not execute because local PostgreSQL rejects the configured `xmansx` password. `makemigrations --check --dry-run` also reports the already-existing Phase 8.5 `SchoolSettings` migration from the dirty concurrent worktree; Phase 9 itself adds no migration.

Playwright, Docker, fresh-database, query-count, and performance benchmarks were not run because the database service/authentication was unavailable.

## Morning attendance integration contract

Current response:

```json
{"morning_attendance": {"status": "NOT_AVAILABLE"}}
```

No adapter, fake repository, import, query, or database table is present in this branch.

## Expected integration work after Phase 8.5

1. Merge Phase 8.5.
2. Rebase Phase 9 and resolve docs/navigation conflicts.
3. Connect `SchoolArrival` summary data.
4. Add morning late cards and history.
5. Keep morning lateness distinct from period lateness.
6. Run full regression and combined E2E scenarios.

## Merge/rebase risks

The known conflict surfaces are shared school settings, navigation/routes, and shared documentation. `backend/devices/*` is owned by Phase 8.5 and should remain outside the Phase 9 conflict resolution.

## Known limitations and technical debt

The frontend currently shows the first page for detail tabs; pagination controls for those tabs can be added without changing the API contract. Performance benchmarks and exact query counts remain to be measured against Docker PostgreSQL. Current date presets cover today, seven days, month, and custom inputs; academic-year defaults are enforced server-side.

## Files changed

- `backend/students/services/attendance_profile.py`
- `backend/students/api/profile_serializers.py`
- `backend/students/api/views.py`
- `backend/students/urls.py`
- `backend/tests/test_student_attendance_profile.py`
- `frontend/src/features/students/api.ts`
- `frontend/src/features/students/StudentAttendanceProfilePage.tsx`
- `frontend/src/features/students/StudentsPage.tsx`
- `frontend/src/routes/index.tsx`
- `docs/STUDENT_ATTENDANCE_PROFILE.md`
- `PHASE_9_REPORT.md`

## Commit

No commit was created. Suggested commit after review and environment-backed validation: `feat: add student attendance profile`.

## Ready for integration with Phase 8.5?

Code and contracts are ready for the planned merge/rebase sequence. Full acceptance is pending PostgreSQL/Docker-backed regression, E2E, benchmark, and final integration with Phase 8.5 morning attendance.
