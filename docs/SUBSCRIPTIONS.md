# Subscriptions

`SchoolSubscription` is the contract between a school and a plan. It is separate from `School`.
School data remains intact across expiry, suspension, cancellation, trial end, and downgrade.

## Statuses

- `TRIAL`: trial period is active.
- `ACTIVE`: paid or administratively active period.
- `GRACE_PERIOD`: subscription ended but temporary access continues.
- `EXPIRED`: subscription ended; operational writes are blocked.
- `SUSPENDED`: platform administrative suspension; operational access is blocked.
- `CANCELLED`: cancelled contract; data remains.

## Lifecycle Actions

Platform Admin can:

- start and extend trial
- activate after trial or expiry
- change plan
- extend subscription
- suspend and reactivate
- cancel

Every action writes `SubscriptionEvent` and an `AuditLog` entry with safe metadata only.

Lifecycle mutations lock the current subscription row. Initial activation additionally locks the
school row so two concurrent first activations cannot create duplicate contracts. Concurrent renewal
cannot lose an extension, concurrent change to the same plan writes one event, and an overlapping
suspend/reactivate sequence follows database lock order.

## Historical Preservation

Renewal and activation after a live trial/grace close the prior contract historically and create a new
active contract. Plan change on a live subscription records `PLAN_CHANGED` and refreshes the
subscription snapshot; it never deletes over-limit data.

## Scheduled Transitions

`python manage.py process_subscription_transitions` runs the idempotent transition sync for trial,
active, and grace expiry. Request-time access checks still compute effective status from dates, so a
delayed worker cannot leave an expired school fully writable.
