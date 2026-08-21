# Backup and Restore

## Create and Verify

Run from a host/container with PostgreSQL client tools and application database settings:

```bash
python manage.py create_database_backup
python manage.py verify_storage_integrity
python manage.py backup_private_objects --destination /protected/object-copy
python manage.py cleanup_backups --dry-run
```

`--local-only` is reserved for an isolated drill and is rejected when the environment requires a
remote repository. A successful database command prints only run ID, size, checksum, and duration.
The dump and adjacent JSON manifest are staged under `DATABASE_BACKUP_ROOT`; production then saves
both through the private `backups` Django storage alias.

## Restore to a Clean Database

1. Identify the latest successful `BackupRun`; confirm repository object size and manifest.
2. Download the dump and manifest to an isolated restore host without changing their names.
3. Provision a brand-new empty PostgreSQL database. Never point application traffic at it yet.
4. Run:

```bash
python manage.py restore_database_backup \
  --backup /restore/backup.dump \
  --manifest /restore/backup.json \
  --target-db xmansx_restore_YYYYMMDD \
  --confirm-target-empty
```

Production-labelled hosts additionally require `--allow-production-host`; normal practice is an
isolated host. The command validates the SHA-256 checksum before connecting, refuses the current
application database, refuses an invalid name or a non-empty target, uses `pg_restore
--exit-on-error`, and never switches application configuration.

5. Point a temporary backend process at the restored database and separate file roots.
6. Run `migrate`, `check`, and `verify_restored_data --manifest expected-data.json`.
7. Restore objects and verify again:

```bash
python manage.py restore_private_objects \
  --source /protected/object-copy \
  --confirm-restore
python manage.py verify_storage_integrity
```

8. Run manager login and selected student, attendance, excuse, warning, document, referral,
   counseling, subscription, and private-download smoke tests.
9. Record backup size/duration, restore duration, verification duration, entity counts, and final
   status in `RESTORE_DRILL_RESULT.json` without secrets or PII.

## Failure Handling

- Checksum mismatch: stop before restore. Acquire another repository copy; never rewrite the
  manifest to match corrupt bytes.
- `pg_restore` error: keep traffic on the original database, discard the partial target database,
  investigate, provision another empty target, and repeat.
- Object checksum mismatch/missing copy: do not mark recovery complete; use provider version history
  or the secondary repository.
- Upload failure after a local dump: `BackupRun` remains failed. Preserve diagnostics, fix the
  repository, then run `python manage.py retry_backup_upload --run-id <id>`. The retry accepts only
  an `UPLOAD_FAILED` run, revalidates the local checksum, locks the run, and is idempotent. Create a
  new full backup if the staged dump or manifest is unavailable.
- Never use `--overwrite` for objects until the isolated restore copy has been inspected.
