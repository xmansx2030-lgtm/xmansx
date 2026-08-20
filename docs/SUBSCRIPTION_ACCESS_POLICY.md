# Subscription Access Policy

Effective status is calculated from subscription dates at request time. The stored status is synced by
the scheduled command for history and reporting, but it is not the only truth.

| Status | Login | Read | Write | Subscription Page |
|---|---:|---:|---:|---:|
| `TRIAL` | Yes | Yes | Yes | Yes |
| `ACTIVE` | Yes | Yes | Yes | Yes |
| `GRACE_PERIOD` | Yes | Yes | Yes | Yes |
| `EXPIRED` | Yes | Yes | No | Yes |
| `SUSPENDED` | Yes | Safe GETs only | No | Yes |
| `CANCELLED` | Yes | Yes | No | Yes |
| No subscription legacy school | Yes | Yes | Yes | Yes |

`SchoolScopedAPIView` blocks non-read requests when the school's access mode is not `FULL`.
It returns `SUBSCRIPTION_EXPIRED`, `SCHOOL_SUSPENDED`, or `SUBSCRIPTION_CANCELLED`
when the effective status is known.
Legacy schools without a subscription remain fully usable so Phase 16 does not lock existing tenants
before their first platform-created contract.

`BLOCKED` is the suspension access mode, but authentication, school switching, `/me`, health, and
the subscription explanation page remain reachable. Existing safe GET endpoints also remain readable
so suspension can be diagnosed and reversed without repairing school data; all operational writes
are rejected with `SCHOOL_SUSPENDED`.
