# Parent Portal Operations

This implementation is local on `feature/parent-portal-20261008`. It has not been
pushed or deployed. School registration is disabled by default. Use the existing
release/backup procedures; do not run production commands without authorization.

## Configuration and preparation

- Set `PARENT_PORTAL_BASE_URL` to the actual trusted frontend HTTPS origin. Never
  derive activation links from an untrusted request Host. Local default is
  `http://localhost:5173`.
- Keep existing `FIELD_ENCRYPTION_KEYS`, `NATIONAL_ID_HMAC_KEY`, SMS encryption key,
  session/CSRF settings, private storage and Redis security cache. No new provider
  account or SMS template change is required.
- Field encryption reads existing and prior configured Fernet keys. A future HMAC
  key rotation must also migrate parent registration identifier/mobile hashes,
  approved contact hashes, recipient blocks and global-mobile request hashes.
  The existing student-only rotation is insufficient for these additive records;
  retain the current HMAC key until a coordinated rotation procedure is implemented.
- Defaults: activation expiry 172800 seconds; registration IP limit60/hour and
  mobile limit10/hour. Family POST limit120/hour, account password limit10/hour.
- Back up database, private objects and the corresponding encryption keys using
  [BACKUP_RESTORE.md](BACKUP_RESTORE.md). Parent excuse attachments participate in
  private-file inventory/checksum recovery and subscription storage quota.
- Test staging with the actual application database role. It must have neither
  SUPERUSER nor BYPASSRLS. Parent tables use FORCE RLS and tenant/exact identity guards.

## Authorized deployment sequence

1. Record intended commit, successful terminal CI, immutable release and backups.
2. Quiesce student writers, deploy compatible backend/frontend and apply the complete
   additive chain students0007–0008 + parents0001–0005. A standalone0007 schema has
   no persistent revision default and must not serve the baseline application;
   students0008 restores old INSERT compatibility. Use the migration release procedure.
   Verify `showmigrations` and
   `makemigrations --check --dry-run`; do not fake migrations.
3. Check readiness and the deployed release SHA, application role privileges,
   private storage access, security Redis availability and RLS/trigger installation.
4. Leave school registration disabled until an authorized manager explicitly enables
   it. Confirm the QR resolves to the school's public registration page without
   exposing students.
5. Run a reviewed synthetic staging journey: approve one child, activate, confirm
   owner-only access, invalidate contact, check old token/file denial, and verify
   existing teacher attendance/SMS/administrative leave/gate journeys.
6. If authorized to verify production delivery, send one reviewed activation SMS to
   an explicitly approved recipient; distinguish provider acceptance from inbox
   receipt. Never bulk-send during rollout verification.
7. Monitor activation FAILED/UNKNOWN, pending reviews, request processing,
   authenticated download denials and errors. UNKNOWN has no blind automatic retry;
   reissue requires fresh documented verification and revokes old tokens.

## Local verification and browser fixture

The independent release recipe uses the complete checkout mounted read-only through
`docker-compose.parent-verification.yml`; all root contract files remain available.
It starts a separate PostgreSQL/Redis stack with public local-test credentials,
no provider integration and a NOSUPERUSER NOBYPASSRLS HTTP application role.
Follow [the independent verification report](PARENT_PORTAL_INDEPENDENT_VERIFICATION.md)
for the tested commands and release evidence. The older Stage F recipe below is
historical evidence, not the new verification result.
The next release uses [restricted synthetic Staging](PARENT_PORTAL_STAGING_READINESS.md)
with separate HTTP/TLS projects and keys; follow that recipe for the expanded
fixture and six browser acceptance scenarios.

From `backend`: `.venv\Scripts\python.exe -m pytest --reuse-db -q -rs`,
`.venv\Scripts\ruff.exe check .`, `manage.py check`,
`manage.py makemigrations --check --dry-run`, and
`manage.py spectacular --file ../tmp/parent-openapi.yaml --validate` using the venv.
From `frontend`: `npm run test`, `npm run typecheck`, `npm run lint`, `npm run build`.

The Windows host lacks native PDF libraries. For the complete backend regression,
use the existing Docker dev image (Pango/WeasyPrint), an isolated test database and
temporary private-file root. The normal Compose backend mount omits the repository
root; mount `render.scalable.yaml` read-only at `/render.scalable.yaml` for the two
blueprint tests. The exact executed full command and1184-test result are in
[Stage F](PARENT_PORTAL_STAGE_F_REPORT.md). This requires no blueprint changes.

The browser fixture command `manage.py seed_parent_e2e --password <local-test-password>
--output ../artifacts/parent-e2e-fixture.json` requires DEBUG and a localhost database,
creates fresh synthetic schools, configures no SMS integration and resets no
existing schools. Registration is disabled by default; add `--enable-registration`
only for the three newly created synthetic schools when running registration E2E.
For the expanded release fixture use `seed_parent_staging` with the same explicit
flag and the isolated owner database documented in the Staging recipe.
Start the local backend on8000 and run
`npx playwright test --config playwright.parent.config.ts` from `frontend`.
Use the same local test password via `E2E_SEED_PASSWORD`; reseed before rerunning
the lifecycle because activation and decisions are intentionally single-use.

## Safe rollback and recovery

Disable new school registration first and revoke unsafe activation links/grants
through reviewed services. If reverting application code, retain additive tables,
revision fields and guards. A previous application can still update student contact
and the database guard must continue invalidating affected grants. Do not drop
tables, reverse security migrations or automatically restore suspended grants.
The pre-portal backend is not a safe credential rollback after guardian accounts
exist: its school/platform/Admin password reset paths lack the new guardian checks.
Keep those checks and the installed parents app in any backend rollback build;
otherwise keep that backend out of service. A schema-compatible old Student INSERT
does not prove a secure whole-backend rollback. Prefer a forward fix or reverting
only the frontend to a compatible verified release.
Apply a forward fix or coordinated database/private-object restore from a verified
backup when data recovery is actually required. Restoring a database alone does
not recover attachments. Recheck grant/contact revision consistency before reopening.

## Explicit limits

Global login-mobile change requests remain pending until an approved process proves
ownership of both the old account and new number. School staff cannot directly
edit a guardian account phone/password. Platform password reset and Django Admin
password reset are also blocked for every account with a guardian relationship.
Shared-impact confirmation cannot substitute for ownership verification.
Recovery remains a public-launch operational blocker; the independent report
describes the missing evidence and proposed central two-reviewer procedure.
Direct SQL contact reviews may lack keyed
contact hashes because the application secret is not installed in PostgreSQL;
atomic revision/suspension remains enforced. No parent electronic leave or gate
authority exists. No real SMS or production deployment was performed in local tests.
