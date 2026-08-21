# Observability

## Health Layers

| Layer | Endpoint or signal | Authentication | Meaning |
|---|---|---|---|
| Liveness | `GET /api/v1/health/live/` | None | Django process can serve a cheap response |
| Compatibility liveness | `GET /api/v1/health/` | None | Same contract as canonical liveness |
| Readiness | `GET /api/v1/health/ready/` | None | PostgreSQL and Redis are reachable |
| Compatibility readiness | `GET /api/v1/readiness/` | None | Same contract as canonical readiness |
| Operational detail | `GET /api/v1/platform/system-health/` | Platform Admin | Safe aggregate health and process metrics |

Liveness never connects to PostgreSQL, Redis, storage, Celery, or an external provider. A
database outage therefore leaves liveness at `200` while readiness returns `503`. Redis is a
hard readiness dependency because sessions/rate limits, cache, Celery broker, and task results
depend on it. The application may still serve some process-only responses during a Redis outage,
but it is removed from ready traffic until Redis recovers.

Responses expose status words and aggregate counts only. They never include versions, hosts,
connection strings, worker names, credentials, stack traces, or customer records.

## Worker and Beat

- Worker health uses Celery `inspect ping`; Docker checks the addressed worker directly.
- Beat schedules `operations.system_heartbeat` every 120 seconds. Successful delivery through
  Beat, Redis, and a worker stores a timestamp in Redis for ten minutes.
- A heartbeat older than 300 seconds is stale. Beat's Docker healthcheck starts after 150 seconds
  to permit the first scheduled delivery.
- Task failures and retries emit structured `celery_task_failed` / `celery_task_retrying` events
  containing task name, bounded task ID, and exception type. Arguments, keyword arguments,
  result values, and payloads are excluded.
- Beat downtime delays subscription transitions and optional backup scheduling but does not
  change effective subscription status calculations or corrupt data.

## Device Bridge

Bridge and device state is derived from the existing `last_seen_at` timestamps:

| Derived state | Threshold |
|---|---|
| `ONLINE` | heartbeat age at most 2 minutes |
| `STALE` | older than 2 minutes and at most 5 minutes |
| `OFFLINE` | older than 5 minutes or never seen |

The Platform Admin operational endpoint exposes aggregate counts. School device APIs continue to
expose authorized per-device last heartbeat and last successful sync. No credential hash,
connection secret, local IP, or event payload appears in operational output. An offline device
never implies a student was absent.

## Request Correlation and Logs

`X-Request-ID` accepts only 8-64 characters from `[A-Za-z0-9._-]`; other input is replaced with a
random 32-character identifier. The response repeats the accepted/generated ID and JSON logs use
the same context.

Request logs contain timestamp, level, logger, request ID, route template, method, status, duration,
and a numeric school identifier when available. They do not collect bodies, headers, cookies,
passwords, temporary passwords, national IDs, private notes, attachments, authorization, Bridge
secrets, or device secrets. The formatter filters sensitive nested metadata as defense in depth.

## Error Tracking

Sentry initializes only when `SENTRY_DSN` is present. Missing credentials are a supported no-op.
`send_default_pii` is disabled, request data/cookies/user context are removed, authorization and
cookie headers are filtered, and a final nested-key scrub runs before every event. Sampling is
off by default and controlled by `SENTRY_TRACES_SAMPLE_RATE`.

Operational failures use stable codes such as `BACKUP_FAILED`, `UPLOAD_FAILED`, and
`STORAGE_INTEGRITY_FAILED`. Alert routing and deduplication are configured at the provider; code
must not emit the same alert on a tight loop.

## Metrics and Alerts

The platform-only health endpoint includes process-local HTTP request count, error rate, and
average latency grouped only by route template, method, and status class. It never labels metrics
with request, school, user, student, national ID, or literal URLs. This small registry is useful
for diagnostics; production should aggregate proxy/application metrics across all workers in the
deployment monitoring system.

Alert conditions:

- readiness unavailable for PostgreSQL or Redis;
- worker ping unavailable or Beat heartbeat older than five minutes;
- latest database backup failed, no successful backup exists, or success is older than 26 hours;
- storage verification reports missing objects, checksum mismatches, or provider errors;
- restore verification fails;
- Bridge/device offline aggregate increases unexpectedly.
