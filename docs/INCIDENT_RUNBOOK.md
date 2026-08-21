# Incident Runbook

## First Ten Minutes

1. Record start time, reporter, affected environment, and safe correlation IDs.
2. Check liveness, readiness, Platform System Health, container health, and recent operational logs.
3. Classify database, Redis, worker, Beat, storage, backup, restore, or Bridge impact.
4. Protect data: stop unsafe writes or scheduled jobs when consistency is uncertain.
5. Assign incident lead and communications owner; never paste secrets or customer records into chat.

## Component Actions

- **Database down:** inspect provider, prevent split-brain, choose failover or clean restore, verify
  application and representative records before traffic.
- **Redis down:** restore Redis; expect login/rate-limit/cache/Celery disruption. Never repair
  PostgreSQL data from Redis because Redis is not a source of truth.
- **Worker down:** keep independent API traffic, replace worker, confirm ping, inspect failed/retrying
  task logs, and watch queued work resume.
- **Beat down:** ensure only one replacement scheduler, verify system heartbeat, run due subscription
  transitions idempotently, and confirm backup schedule state.
- **Object storage down:** block new upload readiness/completion, recover provider access, run storage
  integrity, and retry only operations designed for retry.
- **Backup failure:** preserve the failure code and fix dump/repository access. For an
  `UPLOAD_FAILED` run with intact staging artifacts, use `retry_backup_upload`; otherwise create a
  new full backup. Verify checksum/upload and escalate if the last success exceeds 26 hours.
- **Restore required:** follow `BACKUP_RESTORE.md`; never restore over the running DB or switch traffic
  before data/object/API verification.
- **Bridge outage:** revoke compromised credentials if applicable, replace/provision Bridge, reconcile
  roster and replay device history with deduplication.

## Closure

Confirm readiness, worker/Beat health, backup age, storage integrity, and product smoke tests. Record
actual data loss window, recovery time, root cause, corrective action, and whether backup/RPO/RTO
policy requires revision.
