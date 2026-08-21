# Phase 18 Release Report

## Status

**PASS - ready for Phase 19 after the Phase 18 release commit.**

- Branch: `feature/phase-18-observability-dr`
- Baseline commit: `2b0abf294e88bbe0e4976fa51fbcc6ecb888592f`
- Rescue branch: `rescue/pre-phase-18-observability-dr`
- Final commit: recorded by the release-gate output because a commit cannot contain its own hash
- Verification date: 2026-08-21 (Asia/Riyadh)

## Observability

- Canonical process-only liveness: `GET /api/v1/health/live/`
- Dependency readiness: `GET /api/v1/health/ready/` for PostgreSQL and Redis
- Compatibility endpoints remain available at `/health/` and `/readiness/`
- Platform Admin-only operational snapshot covers backend, DB, Redis, worker, Beat, Bridge/device
  aggregates, latest backup, storage integrity, and bounded process HTTP metrics
- Request IDs are validated, returned, and included in structured JSON logs
- Request metrics use route templates, methods, and status classes without tenant/user labels
- Optional Sentry integration is a no-op without a DSN and removes request body, cookies, user
  context, credentials, identifiers, and sensitive nested metadata before delivery
- Celery failure/retry logs exclude task arguments and payloads

Failure simulation results:

| Scenario | Detection | Web behavior | Result |
|---|---|---|---|
| PostgreSQL stopped | readiness DB=`error` | liveness 200, readiness 503 | PASS |
| Redis stopped | readiness Redis=`error` | liveness 200, readiness 503 | PASS |
| Worker stopped | worker=`unavailable` | independent web readiness 200 | PASS |
| Beat stopped/stale | Beat heartbeat=`stale` | independent web readiness 200 | PASS |
| Object roots empty | 2 missing objects | verification exits non-zero | PASS |
| `pg_dump` failure | `PG_DUMP_FAILED` | failed run, no valid artifact | PASS |
| Repository upload failure | `UPLOAD_FAILED` | never marked successful | PASS |
| Corrupt dump | checksum mismatch | rejected before DB connection | PASS |

## Backup Design

- PostgreSQL backups use `pg_dump -Fc`, an argument list with no shell, a 1 MiB streaming checksum,
  `.partial` staging, atomic rename, SHA-256 manifest, duration/size metadata, and an advisory lock.
- Production requires a private remote S3-compatible/R2 repository by default. Signed access,
  no public ACL, no overwrite, and server-side AES-256 are configured defaults.
- Upload retry revalidates the checksum and locks the failed run; repeated successful retry is
  idempotent.
- Retention keeps 7 daily, 4 weekly, 3 monthly, and the newest successful recovery point. Cleanup
  requires explicit `--apply`; `--dry-run` was exercised.
- Private excuse attachments and generated documents receive streamed protected copies with a
  manifest and checksum verification. Existing immutable documents are restored, not regenerated.
- Production Compose initializes media, private, backup staging, and backup repository volume
  ownership before non-root backend/worker startup.

## Restore Drill

The mandatory drill used `xmansx-phase18-final`, a new PostgreSQL target, and clean object volumes.
It seeded a school, manager, student/enrollment, attendance and morning arrival, excuse attachment,
warning, generated PDF, referral, counselor case, device history, active subscription, 13
entitlement snapshots, and subscription history.

| Measurement | Actual |
|---|---:|
| Database backup size | 380,742 bytes |
| Database backup duration | 6.001 s |
| Database restore duration | 17.349 s |
| Relationship + object verification | 15.948 s |
| Measured end-to-end recovery validation | 88.2 s |

The restored application started under Gunicorn. Manager login and student, attendance, excuse,
warning, document download, referral, counselor case, and subscription APIs returned 200. The
downloaded PDF SHA-256 matched the pre-backup checksum. Storage verification checked 2 objects with
zero missing objects, mismatches, or errors. Representative entity counts and relationships matched
the source manifest exactly. The machine-readable evidence is `RESTORE_DRILL_RESULT.json`.

- Target RPO: 24 hours
- Actual achievable RPO: 24 hours with the configured daily full backup
- Target RTO: 2 hours
- Actual restore drill: 88.2 seconds for the measured recovery validation path

Provider PITR can improve RPO only after an independent restore test. The measured RTO excludes
human incident declaration, provider provisioning queues, DNS/load-balancer change time, and large
production data transfer; production drills must continue to record those values.

## Regression Gates

| Gate | Result |
|---|---|
| Backend full pytest | 707/707 PASS |
| Focused Phase 18 pytest | 23/23 PASS |
| Bridge pytest | 9/9 PASS |
| Vitest | 185/185 PASS |
| Playwright full, Chromium, one worker, retries=0 | 64/64 PASS (13.2 min) |
| ruff | PASS |
| typecheck | PASS |
| lint | PASS |
| production build + PWA assets | PASS |
| Django check | PASS |
| Django check --deploy | PASS with documented non-blocking warnings |
| makemigrations --check | PASS - no changes detected |
| fresh PostgreSQL migrate zero to head | PASS |
| Docker Compose core services | HEALTHY; init job exited 0 |

`check --deploy` reports the intentionally disabled HSTS preload flag and legacy drf-spectacular
schema warnings. The local verification overlay also disables SSL redirect; the production default
remains enabled. OpenAPI exits 0 and is not a release gate.

## Security And Data Preservation

- Backup and restore commands never use a shell and validate filenames, checksums, target names,
  current-database exclusion, empty targets, and explicit confirmation.
- Logs, manifests, backup rows, health endpoints, and the drill result contain no credentials,
  national IDs, private notes, attachment bodies, Bridge secrets, or connection strings.
- Operational detail is Platform Admin-only; public health responses contain bounded status only.
- Students, attendance, excuses, warnings, documents, referrals, counselor cases, devices,
  subscription history, and entitlement snapshots all survived the clean restore.

## Known Limitations

- No external provider credentials were available. The local repository adapter, upload failure,
  partial cleanup, checksum guard, and idempotent retry were tested; a real production bucket test
  remains an infrastructure deployment responsibility before production traffic.
- Sentry event delivery was not sent to an external project. Initialization, safe no-op behavior,
  PII scrubbing, and stable operational event codes are covered.
- Process-local metrics are diagnostic. Production should aggregate proxy/application metrics and
  configure provider-side alert routing, deduplication, retention, and dashboards.
- RPO/RTO figures must be recalibrated with production-scale data and provider provisioning time.

Detailed policy and runbooks are in `docs/OBSERVABILITY.md`, `docs/BACKUP_POLICY.md`,
`docs/BACKUP_RESTORE.md`, `docs/DISASTER_RECOVERY.md`, and `docs/INCIDENT_RUNBOOK.md`.
