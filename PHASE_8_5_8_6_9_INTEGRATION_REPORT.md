# PHASE 8.5 + 8.6 + 9 Integration Report

## Status

Integrated implementation verified on `feature/phase-9-student-profile` after the rescue commit. No Phase 10 work was started.

## Branches/worktrees and rescue strategy

Only one worktree/branch existed. Parallel work was mixed in the worktree, so it was preserved in:

- `cfce2b3 wip: preserve parallel phase 8.5 8.6 and 9 work`

No reset, destructive checkout, or unreviewed deletion was used. A final integration commit is added on top of that rescue commit.

## PostgreSQL root cause and fix

Docker PostgreSQL uses host port `5433` and container port `5432`, with credentials `xmansx/xmansx-dev`. Django's fallback previously used `localhost:5432` when no `.env` existed. The local default was aligned to host port `5433`; Docker continues to override `POSTGRES_HOST=postgres` and `POSTGRES_PORT=5432`. Direct `psql` verification succeeded against the running container.

No real password was added to Git. `.env` is absent; only `.env.example` is tracked.

## Phase 8.5 verification

Implemented and tested device/Bridge authentication, credential rotation, encrypted device secrets, heartbeat/device health, event ingestion/deduplication, unmatched mapping/reprocessing, morning lateness, manual correction, durable Bridge queue, retry/backoff, batching, Simulator, reports, tenant/role isolation, ALL_ABSENT arrival indication, and purge integration.

Evidence:

- Existing backend device/morning tests pass.
- Bridge regression plus Simulator tests: `9 passed`.
- Full backend suite after integration: `339 passed`.
- Docker services: backend, postgres, redis, worker, beat, frontend running; backend/postgres/redis/worker healthy.
- Playwright regression: `25 passed`.

Physical vendor adapter status: `NOT VERIFIED / PHYSICAL_DEVICE_ADAPTER_PENDING`. Simulator is the verified adapter.

## Phase 8.6 verification

Roster synchronization extends the existing `devices` app. It uses `DeviceRosterSyncJob`, `DeviceRosterSyncItem`, per-device `StudentDeviceIdentity`, stable non-sensitive external IDs, capabilities, normalized users, preview hashes, manager approval, stale SaaS/device checks, idempotent command IDs, partial retry, post-apply read verification, unknown-user conflict protection, and SaaS-history preservation.

Backend comparison tests cover matched/create/update, lifecycle delete vs unknown conflict, missing Noor safety, and roster-version changes. The frontend provides `/devices/roster-sync` with action filters and approval/retry flows.

## Phase 9 verification

Student search, HMAC national-ID lookup, masked identity, attendance summaries, historical day/period details, permissions, pagination, and profile UI are present. The profile now integrates morning attendance instead of returning `NOT_AVAILABLE`:

- `morning_late_occurrences` and `morning_late_minutes` come from `SchoolArrival`.
- Period lateness remains `period_late_occurrences` and `period_late_minutes`.
- Morning history uses dated enrollment for grade/section.

## Integrated scenarios

The code path supports Noor-approved Student records -> active roster comparison -> Simulator roster commands -> morning event ingestion -> `SchoolArrival` -> period attendance summaries -> student profile. Existing Playwright covers Noor/import/attendance/lifecycle and full school isolation; focused backend tests cover the morning/profile split.

Device roster-specific browser E2E and the end-to-end Noor-to-device-to-profile scenario are not yet present in the repository's Playwright suite, so those are not claimed as executed.

## OpenAPI

The schema endpoint tests and new Phase 8.5/8.6/9 paths pass. The full `spectacular --validate` command still emits 302 legacy APIView serializer warnings and 7 pre-existing operationId collisions across older accounts/academics/staff/students endpoints. New roster retry and profile/morning endpoints are explicitly decorated. Full zero-warning OpenAPI cleanup remains technical debt outside this focused integration.

## Fresh migration and Docker

Docker migration applied `devices.0002_devicerostersyncjob_devicerostersyncitem_and_more` successfully. `makemigrations --check --dry-run` reports no model changes after migration generation. Django `check` passes. `check --deploy` reports expected local-development security warnings because Docker runs `DEBUG=True`/HTTP and development keys; production settings were not changed to hide these warnings.

## Regression evidence

- Backend: `339 passed`.
- Focused profile/morning/device tests: `24 passed`.
- Focused OpenAPI/profile/roster tests: `12 passed`.
- Bridge: `9 passed`.
- Frontend Vitest: `72 passed` across `11` files.
- Frontend typecheck: PASS.
- Frontend lint: PASS.
- Frontend build: PASS.
- Playwright: `25 passed`.
- Docker services: running; core health checks PASS.

## Security and purge

Tenant scoping, IDOR, role restrictions, Bridge credential authentication, foreign device injection, stale destructive writes, unknown-user deletion, replay/deduplication, secret minimization, and no biometric template storage were reviewed. Device removal does not purge SaaS history. `DeviceRosterSyncItem` is registered in `PURGE_STEPS` so permanent purge does not fail on its PROTECT relation.

## Performance

No formal 500/1000/3000/5000 roster benchmark or p95/query-count report was captured. The existing code uses aggregate queries and bounded batch operations, but benchmark completion remains pending.

## Git and artifacts

The rescue commit contains the mixed Phase 8.5/8.6/9 implementation. No `.env`, secrets, credentials, private keys, temporary Excel files, or local queue database were staged. Runtime media Excel files remain ignored and outside Git.

## Physical device status

Simulator verified. Physical fingerprint-device adapter pending model/vendor/protocol testing. No production physical support is claimed.

## Known limitations and technical debt

- Legacy OpenAPI warnings remain.
- Device-specific Playwright scenarios and performance benchmarks remain to be added.
- The worktree history is rescue-first rather than split into three clean feature commits because the starting work was mixed in one worktree.
- Docker `check --deploy` is intentionally warningful in local development settings.

## Ready for Phase 10?

No. The requested group is functionally integrated and regression-tested, but the explicit remaining items above must be accepted or completed before declaring the strict 100% gate. No Phase 10 feature was started.
