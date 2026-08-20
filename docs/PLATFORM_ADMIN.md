# Platform Admin

Platform Admin is a global role represented by `User.is_platform_admin` and implemented as
`is_superuser`. It is not a `SchoolMembership`.

## Scope

Platform Admin can manage SaaS metadata:

- platform dashboard
- schools list and school creation
- plan CRUD and disable
- subscription actions
- usage and limits
- subscription event timeline
- safe plan-change preview with current usage, proposed limits, and over-limit markers

The schools list supports status, plan, trial, expiring-soon, and over-limit filters. Usage counts are
computed with correlated subqueries and subscription/manager data is prefetched, keeping query count
constant as the list grows. The dashboard reports school status and active student/staff/device totals;
it does not invent revenue metrics without a payment system.

Platform Admin endpoints live under `/api/v1/platform/*` and require
`PlatformAdminRequired`.

## Data Boundary

Platform Admin APIs return school metadata, plan metadata, subscription state, usage counts, and
events. They do not return student records, guardian details, counselor notes, excuse attachments,
documents, attendance rows, or biometric payloads.

## UI

The frontend exposes `/platform` behind `RequirePlatformAdmin`. The area includes Dashboard,
Schools, and Plans tabs. School Manager access to `/platform` is denied by both frontend guard and
backend permission.
