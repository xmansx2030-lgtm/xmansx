# Hetzner deployment

The application runs as the independent `mowadhabah` Compose project in
`/opt/mowadhabah`. PostgreSQL 18, Redis, backend, frontend, Celery worker, and
the lightweight scheduler are separated from other projects on the host.
Only the frontend joins the existing `school-platform-edge` network. Its
temporary verification port binds to localhost. PostgreSQL and Redis have no
published ports. The database application role must remain non-superuser and
must not have `BYPASSRLS`.

## Environment and images

Store `.env`, `application.env`, and `database-admin.env` outside Git with mode
600 in a mode-700 deployment directory. Compose `.env` contains the immutable
backend/frontend image digests and database bootstrap variables.
`application.env` contains production application settings; the database
administrator password belongs only in the bootstrap files. Compose uses raw
environment-file parsing to preserve secret values containing dollar signs.

Preserve existing field-encryption and identifier-HMAC keys when restoring
school data. Keep the application's original authentication and email
configuration. Do not replace them with development defaults.

## Initial restore

Copy exactly one original custom-format PostgreSQL dump and its checksum
manifest into `restore/`. Run `stage.sh` only against a fresh deployment. It
refuses to restore over an application that is already running and the
database bootstrap refuses a populated schema. `verify_stage.sh` verifies
migrations, production settings, aggregate tenant isolation, encrypted
identifiers, and local HTTP readiness.

The database dump does not contain files on the former persistent disk.
Copy the original `media/` and `documents/` bytes into the storage volume,
preserving relative names, then run `verify_storage_integrity`. A complete
move also requires the logo and staff/student import files referenced by the
database. Keep the source service and disk until those references are resolved
and any data after the snapshot timestamp is reconciled. Do not overwrite
archived document checksums or regenerate issued PDFs to conceal missing files.
`recover_document_bytes.py` is a dry run unless explicitly given its save flag;
it saves only bytes whose original checksum and length match exactly.

## Public traffic and runtime

The shared edge proxy is managed by the `school_reports` repository. Merge the
Mowadhabah fragment into its tracked Caddyfile without replacing other routes,
validate the complete configuration using the running Caddy image, update the
bind-mounted file in place, and reload Caddy. Use HTTP-01 certificate challenges
behind the Cloudflare proxy. Maintain Cloudflare Full (strict).

Use a proxied A record for the apex pointing to the target host, and a proxied
www CNAME pointing to the apex. Preserve the existing Cloudflare nameservers
at the registrar and retain mail/DKIM/DMARC records.

After the replacement has been verified and selected as the active database:

```sh
python3 promote_environment.py
docker compose --profile live up -d backend frontend worker beat
docker compose exec -T backend python manage.py create_database_backup
docker compose exec -T backend python manage.py check_operational_health --component worker
docker compose exec -T backend python manage.py check_operational_health --component beat
```

Beat's first heartbeat appears after its configured interval. The production
backup namespace is `hetzner-production`, which keeps rotation separate from
the original Render recovery archive. Database backups retain the existing
daily/latest-only policy and verify remote bytes before rotation.

Install `mowadhabah-files-backup.service` and `.timer` into systemd, then enable
the timer. It archives actual media/document files daily to private R2, includes
a file manifest, verifies remote checksums, and records missing historical
references explicitly. An uploaded archive does not prove those missing files
were recovered. These file archives are retained; monitor bucket growth.

## Verification and evidence

- `public_smoke.py --credentials-env /protected/render-production.env` tests
  public HTTPS, CSRF, registration validation, an existing user's login/session,
  and logout. It creates no schools and never prints credentials or user bodies.
- `registration_drill.sh` restores a separate database and uses isolated Redis
  databases and disabled outbound notifications for a valid registration test.
  It refuses to overwrite an existing QA database.
- `sql_inventory.py` compares aggregate row counts/digests of an independent
  original restore and the candidate before traffic is opened. Authentication,
  audit, session, and backup tables can change normally during verification.
- Store inventories, manifests, deployment environments, and school file keys
  in protected recovery storage. Never commit them to this public repository.

After public traffic is enabled, treat Hetzner as the source of new writes.
Any rollback must preserve and reconcile those writes before switching
databases. Never restore the original dump over the live replacement.
