# SaaS Plans

Phase 16 separates commercial plan metadata from schools and subscriptions.

## Source Of Truth

- `subscriptions.SaaSPlan` stores reusable plan metadata: `code`, Arabic/English names, description, active/public flags, billing period, price metadata, currency, and default trial days.
- `subscriptions.PlanEntitlement` stores plan defaults. Numeric limits use `numeric_value`; boolean features use `is_enabled`.
- Payment is intentionally absent in Phase 16. `price_amount`, `currency`, and `billing_period` are readiness metadata only.

## Entitlements

Numeric limits:

- `MAX_STUDENTS`
- `MAX_STAFF`
- `MAX_DEVICES`
- `MAX_STORAGE_GB`

Boolean features:

- `ATTENDANCE`
- `BIOMETRIC_DEVICES`
- `ROSTER_SYNC`
- `EXCUSES`
- `WARNINGS`
- `DOCUMENTS`
- `REFERRALS`
- `COUNSELING`
- `EXECUTIVE_DASHBOARD`

## Snapshot Rule

When a school subscription starts, plan entitlements are copied into `SubscriptionEntitlement`.
Later edits to a plan do not silently change existing schools. A platform action such as plan change
or entitlement override is required to alter a school's live snapshot.

## Plan Lifecycle

Used plans are not hard-deleted. Platform Admin disables a plan by setting `is_active=false` and
`is_public=false`, preserving historical subscriptions.
