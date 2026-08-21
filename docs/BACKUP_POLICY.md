# Backup Policy

## Objectives

- Target RPO: **24 hours** with the baseline daily full PostgreSQL backup.
- Target RTO: **2 hours** for database provisioning, checksum validation, restore, object restore,
  application checks, and smoke verification.
- The actual achievable RPO cannot be lower than the configured successful backup interval.
  Provider PITR may improve it, but is defense in depth until independently restored and tested.

## PostgreSQL

- Create one `pg_dump -Fc` full backup every 24 hours. Schedule is configurable; production should
  use a provider scheduler or independent operations runner outside the application failure domain.
- Celery Beat scheduling is available but disabled by default. It is supplemental because an
  application-wide outage can stop both the workload and its scheduler.
- Each dump includes schema, migrations, data, and every tenant. It receives a SHA-256 checksum,
  byte size, timestamp, safe environment/database identifiers, and a JSON manifest.
- A PostgreSQL advisory lock prevents concurrent full backups. `.partial` files never become valid
  backups. Upload failure leaves the `BackupRun` in `FAILED/UPLOAD_FAILED`.

## Retention

Baseline retention is configurable policy implemented as:

- 7 distinct daily recovery points;
- 4 distinct ISO-week recovery points;
- 3 distinct monthly recovery points;
- always retain the newest successful backup.

`cleanup_backups --dry-run` is mandatory before `--apply`. Cleanup never deletes the final valid
recovery point and preserves historical `BackupRun` metadata after deleting an artifact.

## Storage and Encryption

The only production copy must never be a local path or Docker volume on the PostgreSQL host.
Production sets `BACKUP_REQUIRE_REMOTE=true` and uses a private S3-compatible/R2 repository with a
backup-only prefix or bucket. The configured defaults prohibit public ACLs, require signed access,
avoid overwrite, and request server-side AES-256 encryption. Provider-managed KMS is preferred
where available. Access keys come from a secret manager and are never stored in a dump, manifest,
filename, log, or database row.

Provider snapshots/PITR are an additional layer, not a replacement for application-owned restore
testing. At least one recovery copy should be in another account or failure domain.

## Private Objects

Excuse attachments and generated documents are part of recovery. Production object storage must
enable versioning and lifecycle protection, with replication or a protected secondary copy. The
`backup_private_objects` command streams DB-referenced objects into a protected copy and records
key, size, checksum, relation type, and record ID. `verify_storage_integrity` performs batched
existence/checksum checks without deleting anything.

## Verification

- Run storage integrity verification after each protected object copy.
- Run an isolated clean-database and clean-object-root restore drill at least monthly and after
  migration, storage, encryption, or backup-tool changes.
- A backup is successful only after dump, checksum, required remote upload, and metadata update.
- A release restore drill must start the application, run checks/migrations, compare representative
  relationships, log in, exercise selected APIs, download private files, and match document hashes.

Backups contain PII and receive the strictest data classification. `.env`, secret-manager contents,
Bridge credentials, and infrastructure keys have a separate encrypted recovery process and are not
copied automatically into the backup repository.
