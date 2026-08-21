# Disaster Recovery

## Recovery Sequence

Detect and classify the incident, protect evidence, stop unsafe writes when consistency is at risk,
identify the last verified recovery point, recover into isolated infrastructure, verify, switch
traffic, smoke test, resume scheduled work, and record timings/decisions.

## Scenarios

| Scenario | Immediate action | Recovery path |
|---|---|---|
| Backend container failure | Remove it from ready traffic | Start immutable image, verify live/ready, add to traffic |
| PostgreSQL unavailable | Readiness removes app; stop writes if failover is uncertain | Restore/fail over, run checks and smoke tests, then resume |
| Redis unavailable | Readiness `503`; sessions/cache/Celery affected | Restore Redis service; durable truth remains PostgreSQL |
| Worker failure | Keep independent web APIs running; queued work remains pending | Replace worker, confirm ping, observe queue drain and failures |
| Beat failure | Effective subscription policy still applies; scheduled work is delayed | Start one Beat instance, verify heartbeat, reconcile due jobs |
| Object storage unavailable | Fail upload/document completion safely | Restore provider access; verify objects; retry failed operations |
| Accidental DB loss/corruption | Freeze unsafe writes and preserve evidence | Restore latest valid dump/PITR to new DB, verify, then switch |
| Missing stored document | Do not regenerate an immutable issued document | Recover exact checksum from version history/secondary copy |
| Bridge host failure | SaaS remains available; unsent local queue may be at risk | Replace Bridge host using the Bridge procedure below |

## PostgreSQL Runbook

1. Confirm liveness/readiness and provider state; declare the incident.
2. Prevent split-brain or writes to a suspected corrupt database.
3. Select the newest checksum-valid backup consistent with the incident time.
4. Provision a replacement database and restore without touching the failed database.
5. Run migrations/checks, representative manifest verification, and private-object verification.
6. Start a temporary application against restored infrastructure and run smoke tests.
7. Switch secrets/service discovery only after approval; watch error/latency/task signals.
8. Resume workers then Beat, reconcile delayed transitions/jobs, and document actual RPO/RTO.

## Bridge Host Recovery

Install the signed Bridge package on a replacement Windows machine, revoke the old installation
credential, provision a new one-time credential, configure LAN device access, read the device roster,
reconcile identities with SaaS, and resume event delivery. Never copy device secrets from logs.

The Bridge SQLite queue is outside PostgreSQL backup. Events acknowledged by SaaS are durable in
PostgreSQL; unsent events existing only on a destroyed host may be lost. Re-read supported device
event history and rely on SaaS dedupe keys when replaying. A raw SQLite queue copy is evidence for
controlled recovery, not the primary DR strategy.
