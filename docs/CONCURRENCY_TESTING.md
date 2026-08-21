# Concurrency Testing

Phase 19 concurrency tests use real PostgreSQL transactions and independent database
connections. They are not SQLite simulations. Capacity checks serialize on a school-level row,
while domain uniqueness constraints remain the final duplicate guard.

## Correctness matrix

| Operation | Concurrent attempts | Expected rows/effect | Actual | Result |
| --- | ---: | --- | --- | --- |
| Attendance session creation | 2 | one session | one session | PASS |
| Attendance submit | 2 | one deterministic submission | one effective submission | PASS |
| Excuse approval | 2 | one coverage set | one coverage set | PASS |
| Warning issuance | 2 | one warning | one warning | PASS |
| Counselor case opening | 2 | one open case | one open case | PASS |
| Subscription activation | 2 | one transition/event | one transition/event | PASS |
| Subscription renew/plan/race suite | 2 each | deterministic lifecycle | deterministic | PASS |
| Student limit at 99/100 | 2 creates | at most 100 active | 100 active | PASS |
| Staff membership limit | 2 creates | limit not exceeded | limit retained | PASS |
| Device limit | 2 creates | limit not exceeded | limit retained | PASS |
| Storage limit | 2 uploads | byte limit not exceeded | limit retained | PASS |
| Roster ACK loss | repeated ACK | idempotent queue state | no duplicate apply | PASS |

The focused Phase 19 suite contains 11 tests and passed against PostgreSQL. Existing subscription
tests continue to cover activation, renewal, plan changes, suspension/reactivation, and event
idempotency.

## Locking policy

- Student, staff, device, and storage admission lock the owning school before counting usage.
- Attendance creation takes the shortest path for an already-existing session, then relies on
  transaction/constraint enforcement for competing creates.
- PDF generation uses a PostgreSQL advisory-lock pool with four slots. Saturation returns the
  explicit `PDF_GENERATION_BUSY` response instead of exhausting web workers.
- Cache availability is not part of correctness. Performance-cache reads fail open; the strict
  security cache alias remains fail closed for authentication rate limiting.

## Bridge pressure

Bridge tests cover a durable 5,000-event queue, backend unavailability, retry, ACK loss, and
idempotent drain. The full Bridge suite passed 11/11. Roster apply medians were 20.333 ms per
command at 100 commands, 25.209 ms at 500, and 28.771 ms at 1,000.

## Deadlocks

No repeated deadlock was observed in attendance, excuses, warnings, cases, subscriptions, limits,
or roster processing. Peak PostgreSQL observations reached 18 connections and 8 active
connections with zero deadlocks.

