# PHASE 8.6 REPORT — Student Device Roster Synchronization

## Status

Implemented on the current Phase 8.5/Phase 9 worktree as an extension of the existing `devices` and `bridge` contracts. Physical vendor support remains pending; Simulator and SaaS contracts are implemented.

## PHASE 8.5 implementation inspected

Inspected `AttendanceDevice`, `DeviceBridgeInstallation`, `DeviceEvent`, `StudentDeviceIdentity`, `SchoolArrival`, `SchoolArrivalChange`, bridge credential authentication, heartbeat/config exchange, ingest/idempotency, durable event queue, adapter protocol, Simulator, migrations, purge integration, API serializers/views/URLs, and existing backend/Bridge tests.

## Device roster architecture

Added `DeviceRosterSyncJob` and `DeviceRosterSyncItem` inside `devices`. Existing Phase 8.5 device, identity, Bridge, arrival, and event models are reused. No duplicate device concept was added.

## Student-only policy and source of truth

The desired roster contains only students with `Student.status=ACTIVE`, an active enrollment, and the current active academic year. Staff and all non-student entities are excluded. Missing latest Noor rows are not lifecycle decisions and cannot produce DELETE.

## External user ID strategy

New IDs are stable `stu-UUIDv5` values derived from school ID and Student primary key. They are not national IDs and do not encode grade, section, or import row. Existing per-device `StudentDeviceIdentity.external_user_id` values are preserved. IDs may differ between devices by design.

## Adapter capabilities

`DeviceCapability` now includes `READ_USERS`, `CREATE_USER`, `UPDATE_USER`, and `DELETE_USER`. `DeviceConnector` exposes normalized roster read/CRUD methods. The generic Simulator persists users and implements all capabilities. No physical vendor adapter has been verified: `PHYSICAL_DEVICE_ROSTER_ADAPTER_PENDING`.

## Comparison engine

`compare_device_roster()` and `save_analysis()` provide `MATCHED`, `CREATE`, `UPDATE`, `DELETE`, and `CONFLICT`. Managed display name changes produce UPDATE; grade/section changes do not. Unknown or unresolved device users produce CONFLICT, never DELETE. Lifecycle-ineligible students with confident platform mappings produce DELETE candidates.

## Preview, approval, stale protection

Analyze creates a job and Bridge read request. Preview stores SaaS/device hashes and minimal snapshots. Manager approval rechecks the SaaS roster hash. Before writes, Bridge reads the device again and compares its hash; mismatch marks STALE and prevents commands. After commands, Bridge reads again and only a verified desired roster can become COMPLETED.

## Bridge commands and idempotency

Bridge receives minimal commands with unique command IDs and only `external_user_id`/`display_name`. Browser-to-LAN writes are not used. Simulator writes are idempotent. Duplicate successful ACKs are accepted. Partial retryable/final failures are represented per item and surfaced through PARTIALLY_FAILED/retry.

## Multi-device behavior

`StudentDeviceIdentity` remains per device and all jobs are device-scoped. The same student may have different stable IDs per device. Unknown users and conflicts are evaluated independently for each device.

## Noor and lifecycle integration

Completed `StudentImportJob` is recorded as optional provenance. Active roster is read from Student/enrollment/academic-year records, so uncommitted Noor imports cannot change device writes. GRADUATED, TRANSFERRED, WITHDRAWN, and INACTIVE students can become DELETE candidates only after lifecycle status is actually changed and a manager approves. Device removal preserves SaaS history.

## Permissions and tenant isolation

Manager: analyze, approve, retry, and writes. Vice Principal: read-only jobs/items. Teacher and counselor: denied. Every browser lookup filters `request.school`; Bridge lookup filters the authenticated Bridge school.

## APIs

Browser:

- `POST /api/v1/devices/{id}/roster-sync/analyze/`
- `GET /api/v1/device-roster-syncs/{id}/`
- `GET /api/v1/device-roster-syncs/{id}/items/`
- `POST /api/v1/device-roster-syncs/{id}/approve/`
- `POST /api/v1/device-roster-syncs/{id}/retry/`

Bridge:

- `POST /api/v1/bridge/roster/read/`
- `POST /api/v1/bridge/roster/command-result/`

OpenAPI decorators and serializers were added for the new endpoints.

## Frontend

Added `DeviceRosterSyncPage` at `/devices/roster-sync`, linked for managers/vice principals. It supports device selection, analyze polling, summary counts, action filters, approval, retry, conflict and history-preservation warnings. Query keys include school/device/job and React never connects to a LAN device.

## Tests and validation

- Backend roster comparison tests added for matched/create/update, inactive delete vs unknown conflict, missing-Noor safety, and roster-version changes.
- Existing Bridge tests plus Simulator roster CRUD test: `9 passed`.
- Django `check`: passed.
- Focused backend lint: passed.
- Frontend `typecheck`: passed.
- Frontend `lint`: passed after repairing an existing Phase 9 pagination parser issue.

Backend database tests could not execute because local PostgreSQL rejects the configured `xmansx` password. The migration was generated as `devices.0002_devicerostersyncjob_devicerostersyncitem_and_more.py`; migration commands emit the same database connectivity warning.

## Fresh migration, Docker, E2E, performance

Not verified in this environment because PostgreSQL authentication is unavailable. Docker/Playwright/performance benchmarks remain pending. No physical device test was available.

## Security review

Reviewed tenant spoofing, foreign device/job access, unknown-user deletion, stale previews, duplicate commands, ACK loss, sensitive payload minimization, per-device IDs, browser-to-LAN prohibition, and SaaS-history preservation. No biometric templates are stored or transmitted.

## Parallel PHASE 9 considerations

Phase 9 student profile remains separate. No device roster data is included in the attendance profile. The shared integration boundary remains Phase 8.5 morning attendance only. Files under the existing Phase 9 feature were not intentionally changed except repairing its already-broken pagination syntax exposed by frontend lint.

## Known limitations and risks

Physical adapters are not production-ready until a real make/model/protocol is tested. Bridge command status recovery after a process crash should be hardened with lease/timeout metadata before production rollout. Final API/E2E and query-count benchmarks await Docker/PostgreSQL.

## Files changed

- `backend/devices/models.py`
- `backend/devices/purge_integration.py`
- `backend/devices/migrations/0002_devicerostersyncjob_devicerostersyncitem_and_more.py`
- `backend/devices/services/roster.py`
- `backend/devices/api/roster_serializers.py`
- `backend/devices/api/serializers.py`
- `backend/devices/api/views.py`
- `backend/devices/urls.py`
- `backend/tests/test_device_roster_sync.py`
- `bridge/bridge_core/adapters/base.py`
- `bridge/bridge_core/adapters/simulator.py`
- `bridge/bridge_core/client.py`
- `bridge/bridge_core/engine.py`
- `bridge/tests/test_roster_adapter.py`
- `frontend/src/features/devices/api.ts`
- `frontend/src/features/devices/DeviceRosterSyncPage.tsx`
- `frontend/src/routes/index.tsx`
- `frontend/src/app/AppShell.tsx`
- `docs/DEVICE_ROSTER_SYNC.md`
- `PHASE_8_6_REPORT.md`

## Commit

No commit was created. Suggested commit: `feat: add student roster synchronization for attendance devices`.

## Ready for Phase 8.5 + 8.6 + 9 integration?

Contracts and implementation are ready for integration review. Full completion is pending PostgreSQL/Docker-backed regression, Playwright, performance benchmarks, and physical adapter verification.
