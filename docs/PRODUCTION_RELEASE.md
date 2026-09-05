# Production release

## Release contract

Every release is identified by one Git commit SHA. The `Release images` workflow runs only after
the main CI workflow succeeds (or by an explicit manual dispatch), builds the backend and frontend
production targets, and publishes both images to GHCR with that exact SHA. Mutable `latest` tags
are intentionally not used by deployment.

The host keeps the real production values in an unreadable-by-others `.env` file outside Git. At
minimum it must satisfy `config.settings.production`, enable HTTPS and secure cookies, use separate
private-object and backup buckets, require remote backups, and configure an external error/uptime
monitor. See `PRODUCTION_HARDENING.md` and `BACKUP_POLICY.md`.

## Host deployment

After authenticating Docker to GHCR, deploy the exact pair emitted by the workflow:

```bash
APP_DIR=/opt/xmansx/app \
BACKEND_IMAGE=ghcr.io/OWNER/REPO/backend:FULL_SHA \
FRONTEND_IMAGE=ghcr.io/OWNER/REPO/frontend:FULL_SHA \
HEALTHCHECK_URL=https://app.example.com/api/v1/health/ \
READINESS_URL=https://app.example.com/api/v1/health/ready/ \
bash scripts/deploy_release.sh
```

The script validates Compose interpolation before mutation, creates a required remote backup on an
existing installation, pulls immutable images, applies migrations, runs Django deployment checks,
starts the stack without local rebuilding, and refuses promotion unless liveness and readiness both
pass.

## Migration and rollback

Database migrations are forward-only during the automated release. If post-deploy health fails,
keep traffic on the previous release when the proxy topology allows it and investigate before any
database rollback. Never run `migrate <old>` until the migration is proven reversible against a
restored copy. Restore the pre-deploy backup into a new database for destructive rollback, verify
it, then switch traffic explicitly. Application-only rollback may reuse the previous immutable
image pair only when its schema compatibility is documented.

## Promotion evidence

Record the deployed Git SHA, both image digests, migration output, successful liveness/readiness,
worker and Beat health, Sentry release visibility, latest remote backup age, and a role-based smoke
journey. A workflow run or a local Compose pass is not evidence that a particular external host was
updated.
