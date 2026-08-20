# PHASE 16 REPORT

## Status

Phase 16 release verification is complete. All code, security, data-preservation, fresh-stack, and
regression gates below passed on the isolated Docker environment.

## Release Context

- Baseline branch: `release/pre-phase-16`
- Baseline commit: `f8b9624`
- Release branch: `feature/phase-16-saas-admin`
- Rescue branch: `rescue/pre-phase-16-final-verification`
- Isolated Compose project: `xmansx-phase16-final`
- Docker Desktop 4.79.0, engine 29.5.3, Compose 5.1.4

No Phase 17, payment, invoice, tax, coupon, checkout, or public-signup work is included.

## Implemented Scope

- Plans, numeric limits, boolean entitlements, and historical plan protection
- Per-subscription entitlement snapshots and explicit overrides
- Trial, activation, renewal, grace, expiry, suspension, reactivation, cancellation, and plan changes
- Effective status calculated at request time plus idempotent scheduled transition synchronization
- Student, staff, device, and storage enforcement with non-destructive over-limit behavior
- Backend feature gates, including `COUNSELING`
- Platform Admin APIs and frontend for dashboard, schools, plans, usage, events, and safe plan preview
- Transactional school + initial manager + subscription provisioning with one-time password display
- School subscription page and precise subscription/limit error codes
- Tenant-safe entitlement caching keyed by school, subscription, and subscription version

## Verification Repairs

- Serialized first activation, renewal, plan change, and suspend/reactivate operations with database
  row locks and regression tests.
- Preserved old entitlement snapshots after plan-default edits and invalidated cached limits on every
  lifecycle change or override.
- Added Noor preview capacity data without blocking preview; commit remains the enforcement point.
- Enforced storage limits on excuse uploads and generated documents while preserving existing files.
- Added backend counseling feature enforcement and specific access error codes.
- Removed Platform school-list N+1 behavior and added status, plan, trial, expiry, and over-limit
  filters plus manager and usage metadata.
- Made Platform overview count each school's latest effective subscription and aggregate active usage.
- Made expired renewal start from the current time rather than preserving an already elapsed end.
- Made school provisioning roll back fully when the initial manager exceeds the selected plan.
- Fixed a midnight-dependent attendance test fixture discovered by the full regression gate.
- Ignored transient `frontend/vite-*.log` runtime logs.

## Executed Gates

| Gate | Result |
|---|---:|
| Backend full pytest | 674/674 PASS |
| Focused Phase 16 pytest | 45/45 PASS |
| Bridge pytest | 9/9 PASS |
| Vitest | 181/181 PASS (22 files) |
| Phase 16 Playwright | 1/1 PASS |
| Full Playwright | 59/59 PASS in 11.0 minutes, retries disabled |
| Ruff | PASS |
| TypeScript typecheck | PASS |
| ESLint | PASS |
| Production frontend build | PASS |
| Django check | PASS |
| Django check --deploy | PASS (exit 0; 80 schema + 6 local deployment warnings reviewed) |
| makemigrations --check | PASS, no changes detected |
| Fresh migrate | PASS from zero through `subscriptions.0001_initial` |
| Docker health/readiness | PASS; PostgreSQL and Redis healthy, backend health HTTP 200 |
| OpenAPI generation (non-gate) | Exit 0; 14 warnings and 361 inference errors recorded |

All backend tests used real PostgreSQL and Redis in the isolated Compose project. No new skips,
xfails, retries, weakened assertions, or permission bypasses were added.

## Security And Isolation

- Platform Admin permission isolation: PASS for manager, vice principal, counselor, and teacher.
- Tenant and multi-school subscription isolation: PASS for ACTIVE versus EXPIRED schools.
- Platform privacy: PASS; school SaaS detail contains metadata, usage, subscription, and events only.
- Temporary password: shown once, stored hashed, must-change enforced, absent from later responses.
- Feature gate: `COUNSELING=false` returns `FEATURE_NOT_INCLUDED_IN_PLAN` from the backend.
- Cache data keys include school id, subscription id, and subscription version; the school-scoped
  pointer is validated before use and cleared immediately and after transaction commit.

## Data Preservation Matrix

| Operation | Students | Attendance | Docs | Referrals | Cases | Devices |
|---|---:|---:|---:|---:|---:|---:|
| Expire | Preserved | Preserved | Preserved | Preserved | Preserved | Preserved |
| Suspend | Preserved | Preserved | Preserved | Preserved | Preserved | Preserved |
| Downgrade | Preserved | Preserved | Preserved | Preserved | Preserved | Preserved |
| Cancel | Preserved | Preserved | Preserved | Preserved | Preserved | Preserved |
| Trial end | Preserved | Preserved | Preserved | Preserved | Preserved | Preserved |

The focused suite also verifies excuses, warnings, student actions, and enrollments. Subscription
lifecycle changes never call purge and never auto-disable existing students or devices.

## Limits And Snapshots

- Active-student formula: only `Student.status == ACTIVE`; graduated, transferred, withdrawn,
  inactive, and archived students do not consume capacity.
- Noor preview reports projected usage and remains available over limit; commit returns
  `STUDENT_LIMIT_EXCEEDED` until an upgrade raises the snapshot limit.
- Staff counts active school memberships once per school, even for an existing global user.
- Downgrade preserves existing over-limit students/devices and blocks only new growth.
- Finite usage at 80% or more reports `near_limit`; the school and Platform UI show a warning.
- Existing contract retained `MAX_STUDENTS=1000` after its plan default changed to 1500; a new
  contract received 1500.

## Performance

Measurements were run inside the isolated Docker stack against PostgreSQL. Benchmark fixtures were
created inside a transaction and rolled back.

| Operation | Duration | SQL queries |
|---|---:|---:|
| Usage at 500 students | 17.71 ms | 7 |
| Usage at 1,000 students | 9.16 ms | 7 |
| Usage at 3,000 students | 7.76 ms | 7 |
| Usage at 5,000 students | 7.88 ms | 7 |
| Platform list at 100 schools | 126.77 ms | 4 |
| Platform list at 500 schools | 611.24 ms | 4 |
| Platform list at 1,000 schools | 1,248.30 ms | 4 |
| 2,000 warm entitlement lookups | 2,737.47 ms | 0 |

Query count remains constant at each measured size, so no `EXPLAIN ANALYZE`-driven index change was
needed.

## Payment Readiness

Payment provider integration is ready only at the domain boundary. It is intentionally not
implemented in Phase 16.
