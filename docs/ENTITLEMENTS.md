# Entitlements

The entitlement service is the only supported way to decide limits and included features.

## APIs

- `get_school_entitlements(school)`
- `has_entitlement(school, key)`
- `get_limit(school, key)`
- `require_feature(school, key)`
- `require_capacity(school, key, current, adding=1)`
- `require_storage_capacity(school, adding_bytes=...)`

Business logic must not branch on plan names such as `PRO` or `BASIC`.

## Cache

Entitlement data keys contain school id, subscription id, and the subscription `updated_at` version.
A short-lived school-scoped pointer avoids re-querying the current subscription for every limit
lookup. The pointer target is validated to belong to the same school. Lifecycle actions and overrides
clear both pointer and value immediately and again after transaction commit, preventing stale limits
after upgrades, downgrades, or overrides.

## Over-Limit Policy

Downgrade can make usage exceed the new limit. The system displays over-limit usage and blocks new
growth, but never deletes existing students, staff memberships, devices, documents, or attachments.
Usage at 80% or more of a finite limit is marked near-limit so the UI can warn before enforcement.

## Enforced Limits

- Student import preview reports projected `MAX_STUDENTS` usage without blocking preview; commit is
  the enforcement point.
- Staff import commit checks `MAX_STAFF`.
- Device creation and device reactivation check `MAX_DEVICES`.
- Excuse attachment upload and generated document creation check `MAX_STORAGE_GB`.
- Counseling API endpoints enforce `COUNSELING` server-side and return
  `FEATURE_NOT_INCLUDED_IN_PLAN` when excluded.
