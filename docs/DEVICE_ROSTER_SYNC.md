# Student Device Roster Synchronization (Phase 8.6)

## Scope

This feature manages student device accounts only. It does not manage staff, biometric templates, fingerprints, faces, or cards. Removing a user from a device never deletes `Student`, enrollment, attendance, `DeviceEvent`, `SchoolArrival`, or historical summaries in SaaS.

## Phase 8.5 contract reused

The implementation extends the existing `devices` app and reuses:

- `AttendanceDevice` and `DeviceBridgeInstallation` for tenant/device/Bridge ownership.
- `StudentDeviceIdentity` for the per-device mapping.
- Bridge authentication from the credential header.
- `DeviceConnector` and `SimulatorConnector` for device I/O.
- Existing heartbeat and durable Bridge queue patterns.

No second device or Bridge model is introduced.

## Stable external ID

The platform ID is `stu-<UUIDv5>` derived from the school ID and immutable Student primary key. It contains no national ID, name, grade, section, or Excel row number. A pre-existing `StudentDeviceIdentity` external ID is preserved for that device, so the same student may safely have different IDs on different devices.

The device receives only `external_user_id` and managed `display_name`.

## Source of truth

The desired roster is derived from `Student.status=ACTIVE`, an `ACTIVE` `StudentEnrollment`, and the current active `AcademicYear`. A missing row in a Noor file is not a lifecycle decision and cannot cause DELETE. Completed imports are recorded as provenance only; preview data comes from the approved Student records.

## Comparison

`compare_device_roster()` produces `MATCHED`, `CREATE`, `UPDATE`, `DELETE`, or `CONFLICT`:

- `MATCHED`: stable managed ID and display name agree.
- `CREATE`: eligible platform student is absent from the device.
- `UPDATE`: managed display name differs.
- `DELETE`: a known platform-managed identity maps to a student with a reviewed inactive lifecycle status.
- `CONFLICT`: duplicate, unresolved, or unknown device users. Unknown users are never deleted.

Grade/section changes do not cause UPDATE because the device roster does not manage academic placement.

## Preview and approval

`DeviceRosterSyncJob` stores SaaS and device roster hashes plus safe counts. `DeviceRosterSyncItem` stores action, status, reason, command ID, and minimal before/after snapshots. It never stores national ID or vendor payload.

The workflow is:

1. Manager requests analyze.
2. Bridge reads users through the adapter and posts normalized users.
3. SaaS creates a paginated review list.
4. Manager approves.
5. SaaS hash is revalidated.
6. Bridge reads the device again; a changed device hash marks the job `STALE` and no write occurs.
7. Bridge polls minimal commands and posts per-item results.
8. Bridge reads the final roster again; only a verified desired roster becomes `COMPLETED`.

Only `SCHOOL_MANAGER` can analyze, approve, retry, or write. `VICE_PRINCIPAL` can read jobs/items. Teachers and counselors are denied.

## Bridge API

Browser-facing:

- `POST /api/v1/devices/{id}/roster-sync/analyze/`
- `GET /api/v1/device-roster-syncs/{id}/`
- `GET /api/v1/device-roster-syncs/{id}/items/`
- `POST /api/v1/device-roster-syncs/{id}/approve/`
- `POST /api/v1/device-roster-syncs/{id}/retry/`

Authenticated Bridge-only:

- `POST /api/v1/bridge/roster/read/`
- `POST /api/v1/bridge/roster/command-result/`

The Bridge contract uses `READ_USERS`, `CREATE_USER`, `UPDATE_USER`, and `DELETE_USER`. The Simulator implements all four and persists normalized users in a JSON file. No physical vendor adapter has been tested; production device support remains `PHYSICAL_DEVICE_ROSTER_ADAPTER_PENDING`.

## Idempotency and failure

Commands have unique `command_id` values. Simulator CREATE/UPDATE/DELETE are state-idempotent. Duplicate successful ACKs are accepted without a second write. Retry operates only on `FAILED_RETRYABLE` items. Offline Bridge operation leaves work in SaaS/Bridge queues and does not claim completion. Partial results are represented by `PARTIALLY_FAILED`.

## Security

All manager APIs are school-scoped by `request.school`; foreign device/job IDs return 404. The Bridge derives school identity from its credential, not payload. Unknown users and conflicts are never auto-deleted. No sensitive student fields are sent to the device or stored in snapshots. Existing purge integration remains separate: device removal is not permanent SaaS purge.

## Frontend

`/devices/roster-sync` provides device selection, analyze polling, counts, action filters, safe preview rows, approval, retry, stale/conflict warnings, and school-scoped TanStack Query keys. It does not make LAN calls from React.

## Deferred/known limitations

- Physical vendor adapter and physical-device verification are pending.
- Bridge test execution requires the project Python environment; no production service deployment is claimed.
- Final database-backed API/E2E performance tests require PostgreSQL/Redis/Docker credentials.
