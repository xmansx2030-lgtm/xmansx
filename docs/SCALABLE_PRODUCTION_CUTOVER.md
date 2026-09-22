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

- Two private Gunicorn instances, each with two processes and four threads; no
  local disk, so horizontal scaling works.
- A bounded native psycopg pool per process (`1..4` web connections and `1..2`
  worker connections). Recalculate the total before increasing replica,
  process, thread, or Celery concurrency counts.
- Two import workers consuming only `imports`, isolated from web requests and
  maintenance work.
- One maintenance worker for heartbeat, purge, and backup queues.
- Exactly one scheduler instance.
- Three independent Key Value roles: an evictable, non-persistent application
  cache; a persistent `noeviction` security/rate-limit store; and a persistent
  `noeviction` Celery broker/result store. Cache pressure therefore cannot
  evict security counters or queued jobs.
- PostgreSQL 1 CPU / 2 GB, 50 GB autoscaling storage, private ingress, and an HA
  standby. Increase compute after load-test evidence, not by guesswork.
- Visible browser tabs use staggered polling and exponential failure backoff;
  hidden tabs stop polling. High-frequency current-period and monitoring reads
  are school-scoped, short-lived, and request-coalesced in the shared cache.

The Blueprint requires a Render Pro workspace for PostgreSQL HA. Do not route
the application through transaction-mode PgBouncer: tenant RLS context is held
in PostgreSQL session settings for the duration of each request.

## Connection budget

The current Blueprint can open at most 16 web-pool connections (2 replicas x 2
processes x 4) and 16 import-worker pool connections (2 replicas x 4 prefork
children x 2). The maintenance worker and scheduler are bounded separately by
the shared `1..2` worker setting. Treat this as a ceiling, not an expected
steady-state count, and leave room for migrations, administration, health
checks, and failover before changing any concurrency value.

## Required post-cutover benchmark

The code and topology remove known synchronization and shared-resource
bottlenecks, but they do not create a new verified concurrency number by
themselves. After cutover, rerun the Locust teacher, composite, login, dashboard,
soak, Redis-restart, and backend-restart profiles against the real topology.
Record P50/P95/P99, error rate, PostgreSQL pool wait/connect counts, Key Value
memory/connections, and Celery queue drain time before raising the pilot limit
or publishing an SLA.
