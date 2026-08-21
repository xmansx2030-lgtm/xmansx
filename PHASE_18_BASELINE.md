# Phase 18 Observability and Disaster-Recovery Baseline

Date: 2026-08-21

Baseline branch: `feature/phase-17-production-hardening`

Baseline commit: `2b0abf294e88bbe0e4976fa51fbcc6ecb888592f`

Phase 18 branch: `feature/phase-18-observability-dr`

Rescue branch: `rescue/pre-phase-18-observability-dr`

## Repository State

- The baseline commit matches the approved Phase 17 release commit and the worktree was clean.
- Other agents use separate worktree paths and do not write to this Phase 18 worktree.
- No source, runtime log, or untracked file was present at inspection time.

## Current Observability

- `/api/v1/health/` is an unauthenticated process-only liveness endpoint.
- `/api/v1/readiness/` checks PostgreSQL and Redis and returns `503` when either fails.
- Docker healthchecks cover PostgreSQL, Redis, the backend liveness endpoint, and Celery
  worker `inspect ping`. Beat has no healthcheck beyond process state.
- Device Bridge and attendance-device records retain `last_seen_at`; devices also retain
  `last_successful_sync_at`. The existing operational threshold declares a device offline
  after five minutes, but there is no aggregate operational health view.
- Subscription transitions already use effective status and are not exclusively dependent
  on Celery Beat.

## Current Logs and Request Correlation

- Django emits structured JSON logs with timestamp, level, logger, message, and request ID.
- Request middleware validates or creates a bounded request ID and returns it in
  `X-Request-ID`.
- Request logs contain method, path, status, duration, and a numeric school identifier.
- Request headers, cookies, bodies, credentials, national IDs, and file contents are not
  collected by request logging.
- Celery task failures, retries, backup outcomes, and readiness incidents do not yet have a
  dedicated safe operational event path.

## Current Error Tracking and Metrics

- Documentation describes the application as Sentry-ready, but no SDK integration exists.
- There is no operational metrics endpoint or request count/error/latency aggregation.
- There is no persisted worker/beat heartbeat or failed-job inventory.

## Current Database Backup and Recovery

- No PostgreSQL backup, checksum manifest, retention, restore, or restore-verification command
  exists.
- No `BackupRun` record tracks running, successful, or failed backups.
- No backup concurrency lock or dry-run retention implementation exists.
- PostgreSQL client tools are not installed in the backend image.
- No prior clean-database restore drill or machine-readable restore report exists.

## Current Object-Storage Protection

- Excuse attachments use Django's default private file storage and retain size/checksum data.
- Generated documents use a separate private filesystem storage and retain size/checksum data.
- Production Compose stores both roots in private Docker volumes shared with the worker.
- S3-compatible storage is documented as a deployment option but is not configured in code.
- There is no DB-to-object integrity command, object backup manifest, restore command,
  provider-versioning policy, or secondary-copy policy.
- The Bridge SQLite delivery queue is local to the Bridge host and is outside PostgreSQL backup.

## Current Alerting and Recovery Process

- Health failures and application exceptions reach structured logs only.
- There are no deduplicated operational alert conditions for stale backups, worker/beat
  heartbeat, storage integrity, or restore verification.
- There is no incident runbook or documented database, Redis, worker, beat, storage, or Bridge
  recovery procedure.

## Critical Gaps

1. Add canonical live/ready endpoints while preserving existing endpoint compatibility.
2. Add safe low-cardinality HTTP metrics and platform-only operational health visibility.
3. Add worker/beat heartbeat and safe Celery failure/retry logging.
4. Add optional privacy-first error-tracking initialization that is inert without a DSN.
5. Add PostgreSQL custom-format backup, checksums, manifests, run history, locking, retention,
   and guarded restore tooling.
6. Add private-object inventory, integrity verification, protected copy, and restore tooling.
7. Prove recovery in a brand-new database and isolated file roots with representative domain
   and checksum verification.
8. Add disaster-recovery, backup, observability, and incident documentation.

## External Provider Dependencies

- Production PostgreSQL hosting should provide encrypted snapshots/PITR as defense in depth;
  those snapshots still require independent restore drills.
- Production backup copies must live outside the database host failure domain, in a private,
  encrypted bucket or equivalent protected repository.
- Object storage should enable provider versioning and preferably cross-account or secondary
  bucket replication. Credentials are supplied by a secret manager, never database backups.
- Error tracking requires a deployment-owned DSN. Missing credentials must never prevent local
  development, tests, or application startup.
