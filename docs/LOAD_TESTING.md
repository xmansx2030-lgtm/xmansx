# Load Testing

Phase 19 uses Locust against an isolated Compose project. It never targets production and the
generator creates synthetic schools, users, students, history, devices, and attendance data.

## Reproduce

1. Start an isolated Compose project with unique host ports and the
   production-like overlay. For example:

   ```powershell
   $env:POSTGRES_HOST_PORT = "58003"
   $env:REDIS_HOST_PORT = "58004"
   $env:BACKEND_HOST_PORT = "58005"
   $env:BACKEND_IMAGE = "xmansx-backend:scale-verify"
   docker compose -p xmansx-scalecheck -f docker-compose.yml -f docker-compose.loadtest.yml `
     up --no-build -d postgres redis backend
   ```

2. Run migrations and `generate_phase19_data` with the required school/student/history sizes.
3. Run `scripts/run_phase19_load.ps1` with a named Locust profile.
4. Run `scripts/capture_phase19_metrics.ps1` in parallel for Docker, PostgreSQL, Redis, and
   Celery observations.

The harness reads its host and credentials from environment variables. Do not hard-code a
shared database or production URL. CSV and log artifacts are written under the ignored
`phase19-results/` directory.

## 2026-09-22 scale-hardening rebaseline

The application now staggers browser polling, backs off after failures, stops
polling in hidden tabs, coalesces school-scoped live attendance reads, uses
bounded native PostgreSQL pools, and separates cache, security, and Celery Key
Value roles in `render.scalable.yaml`. Nginx also compresses API and static text
responses and reuses upstream HTTP/1.1 connections.

A partial local rebaseline was completed against one production-image backend
replica (two Gunicorn processes x four threads, native pool `1..4`) with local
PostgreSQL/Redis and 10 schools containing 500 students and 100 staff each.
Traffic went directly to Gunicorn, so this did not include frontend Nginx, TLS,
Render networking, HA failover, or the split managed Key Value services.

| Profile | Users | Requests | RPS | P50 | P95 | P99 | Errors |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Mixed | 100 | 5,913 | 99.73 | 420 ms | 1.5 s | 1.9 s | 0% |
| Dashboard | 100 | 5,723 | 95.82 | 800 ms | 1.3 s | 1.7 s | 0% |
| Dashboard | 150 | 5,802 | 95.61 | 1.3 s | 2.0 s | 2.4 s | 0% |
| Dashboard | 250 | 5,468 | 93.11 | 2.3 s | 3.9 s | 4.7 s | 0% |
| Dashboard | 500 | 6,112 | 102.51 | 4.3 s | 6.4 s | 6.7 s | 0% |
| Dashboard | 1,000 | 5,599 | 93.66 | 9.8 s | 11 s | 11 s | 0% |

The highest error-free level exercised was 1,000 dashboard users, but it is not
usable capacity: throughput plateaued near 100 RPS and latency queued sharply.
The responsive local range was around 100 dashboard users; 150 already reached
a two-second P95. After the run, readiness remained green, Gunicorn had exactly
eight idle PostgreSQL connections (the configured per-process maximum), Redis
had no blocked clients, and backend logs contained no traceback, error, critical,
or worker-timeout entry.

Do not claim these results as Render capacity. The same profiles still need to
be rerun on the target services with application, PostgreSQL, Key Value, and
Celery metrics captured together before changing the production pilot limit or
publishing an SLA.

## Environment

- ASUS Vivobook X1504VA, Intel Core i7-1355U (12 logical CPUs), 15.64 GiB RAM, NVMe SSD.
- Windows 11 with Docker Desktop/WSL2: 12 CPUs and 7.58 GiB memory available to Docker.
- PostgreSQL 18.6, Redis 8.0.6, Django 5.2, Gunicorn 9 sync workers, one Celery worker.
- Production-like Nginx frontend and synthetic dataset only.

## HTTP results

| Profile | Users | Requests | RPS | P50 | P95 | P99 | Unexpected errors |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Teacher attendance peak | 100 | 4,232 | 72.51 | 630 ms | 1.9 s | 4.7 s | 0% |
| Composite peak | 100 | 5,677 | 48.65 | 1.2 s | 3.5 s | 4.8 s | 0% |
| Composite stress | 120 | 6,521 | 55.14 | 1.2 s | 3.5 s | 8.7 s | 0.05% |
| Login burst | 50 | - | - | - | 1.4 s | - | 0% |
| Login burst | 100 | - | - | - | 3.1 s | - | 0% |
| Login burst | 250 | - | - | - | 11 s | - | 0% |
| Login burst, isolated | 500 | 948 | - | - | 23 s | - | 1.26% |
| Dashboard | 10 / 25 / 50 | - | - | - | 250 / 520 / 1,300 ms | - | 0% |
| Student profile | 25 / 50 / 100 | - | - | - | 310 / 510 / 1,600 ms | - | 0% |
| Counselor | 25 / 50 | - | - | - | 140 / 520 ms | - | 0% |
| Platform schools | 10 / 25 | - | - | - | 51 / 94 ms | - | 0% |

The teacher scenario completed all 100 starts and submissions without corruption. Its latency
misses the initial 750 ms P95 target on this constrained local stack, so capacity is bounded by
correctness and observed latency rather than relabeling the target.

## Focused datasets

| Operation | Size | Result |
| --- | ---: | --- |
| Device batch | 5,000 | 4,224.5 ms; dedupe check 456.4 ms |
| Roster compare | 5,000 | 545.4 ms; save 1,346.3 ms |
| Noor import | 5,000 | preview 7.27 s; commit 6.33 s; peak Python allocation 31.3 MiB |
| Warning metrics | 5,000 | 81-86 ms, one query |
| Student profile | 365 days | summary 3.2 ms / one query; daily 4.2 ms / one query |
| Platform list | 1,000 schools | 1,491.25 ms / four queries |
| Platform page after SQL pagination | 100 / 500 / 1,000 total schools | 249 / 233 / 217 ms; 100 serialized; five queries |

The 2026-09-11 scaling hardening moved platform status/plan/expiry/limit filters,
counts, and pagination into PostgreSQL. Serialization is now bounded by the
requested page (maximum 100) instead of the total school count. A 2026-09-11
local rerun stayed effectively flat while the tenant registry grew from 100 to
1,000 schools (249/233/217 ms, five queries); the historical 1,000-row timing
above intentionally remains as the pre-fix comparison. The target Render
topology still needs its own release benchmark before setting an external SLA.

Attendance analytics retained constant query counts at 500, 1,000, 3,000, and 5,000 students.
Period reads ranged from 22 to 280 ms; full rebuild ranged from 1.76 to 23.03 seconds.

## Soak and recovery

The 30-minute, 100-user soak completed 89,953 requests at 49.98 RPS with zero failures. P50,
P95, and P99 were 1.4, 3.3, and 5.4 seconds. Backend memory moved from 722.1 to 730.9 MiB,
worker memory from 725.6 to 725.4 MiB, and no connection or queue growth remained.

Redis restart initially caused 59 HTTP 500 responses. After the cache fail-open fix, 3,264
requests completed with zero failures. A backend restart caused 416 expected connection resets
during the 3.63-second outage; the immediate recovery run completed 1,728 requests without a
failure. These outage errors are not counted as application correctness passes.
