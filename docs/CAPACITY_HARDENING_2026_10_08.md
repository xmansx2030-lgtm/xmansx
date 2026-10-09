# Server pressure hardening — 2026-10-08

Target supplied by the owner: **100+ schools and 2,000 concurrent users**.
Delivery is local working-tree changes on `feature/parent-portal-20261008`,
starting at `d8f8de6d4365e518cff269d438c25715c31a4a7e`. No push, deployment,
provider plan change, production load test, or real SMS delivery was performed.
Existing printing work was preserved.

## Delivered changes

- Native PostgreSQL pooling is enabled in the small `render.yaml` service
  (`0..2`, one process/two threads). `render.scalable.yaml` prepares four
  application replicas, each two processes/four threads and pool `1..4`.
  Scaled wait queues are bounded: 16 per web process, 8 per worker process
  (small Blueprint: 4). Tenant RLS
  context is retained; transaction-mode PgBouncer was not introduced.
- Performance and security Redis clients use separate bounded blocking pools:
  eight connections per process/role, 250 ms pool wait, one-second connect/read
  timeouts. Celery publisher, transport, and result connection pools are also
  bounded. Production scaling uses physically separate cache, security, and
  broker stores; logical Redis databases do not isolate memory pressure.
- Cold cache fills share one process-local future and a Redis lease across
  replicas. Slow fills no longer spawn one fallback computation per waiter.
  Existing stale-grace and school/role/version keys are preserved. Cold waits
  exceeding five seconds return 503 with `Retry-After: 2`. Leases use atomic
  compare-and-delete so an expired owner cannot delete its successor's lock.
  A two-second circuit suppresses repeated performance-cache outage attempts;
  security Redis remains fail-closed, and optional cache invalidation cannot
  turn a successful mutation into a Redis error.
- Absence, lateness, and referral reports slice in PostgreSQL before row
  serialization. Totals still cover the complete filtered result. Print and
  Excel paths retain all filtered rows, including counselor scope. Stable
  tie-breakers prevent equal sort values from moving arbitrarily between pages.
- Authenticated APIs have an atomic shared per-account budget of 240 requests
  per minute, plus 12 full-report/Excel requests per minute. Limits use Redis
  server time, independent of application clock skew. Sharing a school's NAT
  IP does not combine accounts. Existing public login/registration limits
  remain in place. CSRF bootstrap and logout remain available even after budget
  exhaustion or a security-store outage. Health/readiness are exempt from the
  new throttle; a security-store failure returns 503 with a retry hint rather
  than bypassing the guard or falling back to database counters.
- Job/import/purge/roster/SMS-status polling now uses staggered five-second
  intervals, terminal-state stops, hidden-tab stops, and exponential failure
  backoff. Failure streaks survive React Query's per-fetch counter reset.
  Job polling also recovers when its first status read failed before any data
  was cached. HTTP `Retry-After` is parsed and honored. Network status 0 can
  retry; normal 4xx errors do not retry automatically. Student import commit
  tasks are routed to `imports`, alongside preview processing, instead of the
  maintenance queue.
- Nginx has an actual upstream keepalive pool, with DNS re-resolution after
  backend replacement. Its shared active API ceiling is 128 in the scalable
  Blueprint and 16 in the small Blueprint. Excess work receives JSON 503,
  `Retry-After: 2`, and private/no-store headers. Idle connections do not count,
  and health/readiness are exempt. The ceiling does not use school IP addresses.
  Gunicorn keeps connections alive for 10 seconds, staggers worker recycling,
  and bounds socket/backlog capacity at 512. This is distinct from the PostgreSQL
  connection ceiling.
- Docker build context excludes private/generated files, local backups,
  synthetic credentials and runtime logs. No dependency or lockfile changed.

## Verification

Frontend: **45 files / 434 tests passed** in 122.57 seconds. TypeScript and lint
passed. The production Docker/PWA build succeeded. Backend `ruff`, Django checks,
and migration drift checks passed; these changes require no database migration.
After extending recovery from a failed first job-status read, the three focused
frontend suites passed **12 tests in 49.42 seconds**, and TypeScript, lint and
the production Docker/PWA build passed again.

Full backend regression in Linux/Docker: **1,253 passed, zero failed, zero
skipped in 472.71 seconds** (`tmp/capacity-backend-final.log`), including actual
PDF rendering, restricted-role RLS, authentication and existing SMS/leave/gate
regressions. One HarfBuzz-Subset deprecation warning is non-failing. The later
CSRF/logout recovery assertions also passed: **4 pressure tests in 8.18 seconds**.

Real Redis lease probe: **two processes, eight simultaneous requests, one
1.25-second builder invocation**. Unit coverage also exercises local coalescing
with Redis unavailable, bounded cold waits, builder failure/recovery, outage
retry suppression, and protecting a successor's lease.

Real HTTP proxy probe: **20 requests over one upstream TCP connection**. Nginx
starts even when backend DNS is initially absent. Replacing a synthetic backend
with a different IP recovered automatically in 7.09 seconds; the probe observed
seven 502 responses during DNS convergence. This demonstrates bounded recovery,
not uninterrupted failover. Production rolling releases must retain healthy
backends during that interval.

Final proxy admission probe: **168 simultaneous slow requests produced 128
HTTP 200 and 40 HTTP 503**, with an observed upstream peak of exactly 128.
Rejected responses carried the JSON error code, retry hint and no-store policy;
both health/readiness returned 200 during saturation. The persistent reproduction
is [`loadtests/proxy_probe.py`](../loadtests/proxy_probe.py), with a synthetic
six-second upstream.

Runtime evidence is ignored, rather than committed with synthetic session
credentials.

## Capacity environment and workload

[`docker-compose.capacity.yml`](../docker-compose.capacity.yml) creates only the
disposable project `xmansx-capacity-check`, with a separate PostgreSQL volume,
three Redis services, four production-image backends, and production Nginx.
The exposed frontend is `http://127.0.0.1:58085`.

- Each backend: 1 CPU / 512 MiB, two processes/four threads, native pool `1..4`.
- PostgreSQL: 2 CPUs / 2 GiB. Web connections cannot exceed **32**, regardless
  of the client count. The runtime role is `NOSUPERUSER NOBYPASSRLS`.
- Synthetic dataset: **100 schools, 50,000 students, 2,301 users** (2,300 school
  staff plus one fixture administrator), and **300,000 historical attendance
  summaries**. No production database was used.
- [`loadtests/capacity.py`](../loadtests/capacity.py) allocates distinct accounts,
  verifies each actor enters its own school, and uses normal visible-page
  polling: manager/vice-principal dashboards and paged absence reports;
  counselor dashboard/cases; teacher current period, follow-up and referrals.
  Failed bootstraps remain observable and retry with the same actor; they do
  not create replacement accounts or inflate concurrency. The local HTTP
  harness relaxes Secure cookies only in its client cookie jar.
- The intended mix is 100 managers, 100 vice principals, 100 counselors, and
  1,700 teachers across 100 schools. Prepared sessions avoid Argon2/login burst
  cost. This is a **read/polling workload**, not a write/import/PDF/parent/login
  storm, soak, HA failover, or production TLS/network benchmark.

An early run was stopped after bootstrap failures caused the original harness
to replace actors indefinitely and exhaust its credential list. Its numbers
are not a capacity result. A second partial run exposed excessive queuing with
the initial 128 socket/backlog limit; this was raised to 512 without increasing
database pool sizes. Failed and interrupted artifacts remain separate from
the final run.

Completed pre-gateway run `capacity-v4` reached 2,000 simulated clients over
360 seconds: 25,707 requests, 19,009 failures (73.94%), P95 20 seconds and P99
28 seconds. Only 1,156 actors successfully verified their own school. This was
an unsuccessful stress run, not evidence for 2,000 active users. It preceded
the shared Nginx admission ceiling and a harness correction making network
timeouts use the same progressive polling backoff as HTTP 503. It cannot serve
as an isolated A/B comparison because both admission and the failure workload
changed. The final `capacity-v5` result follows below.

## Final capacity result: target not met

The six-minute `capacity-v5` run used the final API/proxy configuration, ramped
at 10 clients/second, and reached **2,000 clients**. **1,997 distinct accounts**
verified their own school: 100 managers, 100 vice principals, 100 counselors,
and 1,697 teachers, across all 100 schools. Prepared sessions and the production
restricted database role were used throughout. Locust exited **1** because
requests failed; this is not a passing capacity test.

| Measure | Result |
| --- | --- |
| Requests / successful / failed | 40,087 / 22,607 / 17,480 |
| Failure rate | **43.61%** |
| Failure types | 17,475 HTTP 503; 5 disconnected responses |
| P50 / P95 / P99, all measured requests | 0.42 s / 5.1 s / 7.8 s |
| Mean total / successful requests per second | 108.83 / 61.38 |
| Sampled PostgreSQL web connections / active / lock waiting, maxima | 32 / 12 / 0 |
| Maximum sampled backend / PostgreSQL memory | 207.9 MiB per backend / 363.5 MiB |
| Container OOM / restarts | None / zero |

The latency percentiles include quick rejected requests; they cannot be used
as successful-user latency or an SLA. The gateway recorded 17,498 admission
rejections, including requests still in flight at shutdown. Backend logs showed
no request 503, database pool error or Gunicorn worker timeout in this interval.
The ceiling stopped excess work before Django, but rejecting nearly half the
workload is **not** evidence of sufficient processing capacity.

Twenty-five resource snapshots between 06:02:52 and 06:09:05 UTC show backend
CPU medians of approximately 89–100% of one core per replica; PostgreSQL's median
was approximately 174% of a core under its two-CPU quota. Redis reported no
evictions, rejected connections or blocked clients. No sampled PostgreSQL lock
wait was observed; this does not rule out short waits between snapshots. The
load generator also approached one CPU core (peak sampled 94.66%). Docker had
12 CPUs and 7.58 GiB available, with other development containers running.
These are shared-host observations, not cloud-provider measurements or an
isolated measurement of one bottleneck.

At peak load, actual application health/readiness returned HTTP 200 in 0.140 s
and 2.729 s respectively. After the test, the queue drained and normal reads
returned 200. The capacity dataset/database and temporary test Redis were
removed after verification; ignored CSV/HTML/JSONL evidence remains under
`phase19-results/capacity/`, including a saved `actors-v5.json`.

**Conclusion:** the pooling/admission/failure controls are verified. The local
four-core web plus two-core database setup did not satisfy the 2,000-user
read/polling target. Profile the hot authenticated reads and database plans,
then test real allocated CPU/topology and all required write/background
workflows before choosing or advertising a production capacity. The proposed
Blueprint remains a candidate, not a capacity certification.

## Reproduction

Build the production images and start the disposable infrastructure:

```powershell
docker build --target prod -t xmansx-backend:capacity-20261008 backend
docker build --target prod -t xmansx-frontend:capacity-20261008 frontend
docker compose -f docker-compose.capacity.yml up -d postgres cache security broker
docker compose -f docker-compose.capacity.yml run --rm --no-deps tools python manage.py migrate --noinput
docker compose -f docker-compose.capacity.yml run --rm --no-deps tools python manage.py generate_phase19_data --schools 100 --students 500 --staff 20 --history-days 30 --history-students 100 --output /results/data.json
```

On a fresh disposable database, create its restricted runtime role:

```powershell
@'
CREATE ROLE capacity_app LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD 'capacity-disposable-app';
GRANT CONNECT ON DATABASE capacity_synthetic TO capacity_app;
GRANT USAGE ON SCHEMA public TO capacity_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO capacity_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO capacity_app;
'@ | docker compose -f docker-compose.capacity.yml exec -T postgres psql -U capacity_owner -d capacity_synthetic -v ON_ERROR_STOP=1
docker compose -f docker-compose.capacity.yml up -d backend frontend
```

The owner is used only for migrations/fixtures; web containers use
`capacity_app`. Verify readiness and warm application startup. In separate
terminals capture metrics and run:

```powershell
.\loadtests\measure_capacity.ps1 -DurationSeconds 380 -OutputFile phase19-results/capacity/resources-v5.jsonl
docker compose -f docker-compose.capacity.yml run --rm --no-deps load -f /loadtests/capacity.py --host http://frontend:8080 --headless --users 2000 --spawn-rate 10 --run-time 360s --csv /results/capacity-v5 --csv-full-history --html /results/capacity-v5.html --only-summary
```

Metrics capture aggregate Docker CPU/RAM, application PostgreSQL connections,
active queries/lock waits, and Redis memory/client/eviction/rejection counts.
They do **not** measure Django pool wait time or cloud-provider CPU metrics.
CSV history records the actual client count; `actors.json` records verified
distinct accounts and school distribution. Client bootstrap/session failures
are counted, and HTTP errors are not whitelisted away.
Use fresh output names for each repeat; resource JSONL is append-only.

## Production handoff

The scalable Blueprint is a candidate requiring the existing R2 migration and
[cutover gates](SCALABLE_PRODUCTION_CUTOVER.md). Pool budgets total 48 for web,
import children, maintenance and beat, plus four reserved import-parent
connections, administration and rolling-release overlap. Confirm the actual
database connection limit before deploying. [Render's Blueprint reference](https://render.com/docs/blueprint-spec)
defines the proposed compute-plan names; no provider resources were changed.

A local read benchmark cannot certify 2,000 users across all workflows. Before
publishing that capacity, measure the deployed topology, attendance-save bursts,
login storms, imports/PDF, parent access and recovery, with P95/P99, errors and
queue drain times. Keep the small single-service configuration for its measured
pilot scope; it does not represent the proposed multi-school topology.
