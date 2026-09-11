# Scalable production cutover

`render.scalable.yaml` is the production target for a large multi-school fleet.
It is deliberately not the auto-synced `render.yaml`, because the current
single-instance service owns a persistent disk. Removing that disk before its
objects are copied would be destructive.

## Required cutover order

1. Create two private R2 buckets: one for application objects and one for
   database backups. Apply lifecycle/versioning rules appropriate to retention.
2. Copy every object from the current media/document/backup disk to its matching
   R2 prefix. Compare object counts, byte totals, and sampled checksums.
3. Validate a remote database backup and perform a restore drill into an
   isolated database.
4. Create a Blueprint from `render.scalable.yaml`. Supply the five R2 values and
   initial platform-admin credentials when prompted.
5. Run `python manage.py migrate --noinput`. Confirm migrations
   `operations.0002`, `operations.0003`, and `operations.0004`, then verify
   `/api/v1/readiness/`. The application database role must be
   `NOSUPERUSER NOBYPASSRLS`; readiness intentionally fails otherwise.
6. Exercise one read and one write in two different test schools, confirm RLS
   isolation, import-worker processing, generated-document download, and audit
   records.
7. Move the public frontend/domain only after those gates pass. Keep the old
   service read-only until rollback retention expires.

## Capacity topology

- Two private Gunicorn instances; no local disk, so horizontal scaling works.
- Two import workers consuming only `imports`, isolated from web requests and
  maintenance work.
- One maintenance worker for heartbeat, purge, and backup queues.
- Exactly one scheduler instance.
- Managed 1 GB Key Value with persistence and `noeviction`.
- PostgreSQL 1 CPU / 2 GB, 50 GB autoscaling storage, private ingress, and an HA
  standby. Increase compute after load-test evidence, not by guesswork.

The Blueprint requires a Render Pro workspace for PostgreSQL HA. Do not route
the application through transaction-mode PgBouncer: tenant RLS context is held
in PostgreSQL session settings for the duration of each request.
