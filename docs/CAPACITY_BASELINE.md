# Capacity Baseline

This document records observed local capacity, not guaranteed production capacity. Production
sizing must be repeated on the real topology with TLS termination, production database storage,
network latency, monitoring, and explicit container resource limits.

> A partial local rebaseline was completed on 2026-09-22 after polling,
> live-read caching, database pooling, Redis role isolation, and proxy changes.
> Production revalidation remains pending; neither local result is a Render SLA.

## Post-hardening local check (2026-09-22)

One production-image backend replica used two Gunicorn processes with four
threads each and a bounded `1..4` psycopg pool. Local PostgreSQL/Redis served 10
synthetic schools, each with 500 students and 100 staff. Requests went directly
to Gunicorn, without Nginx, TLS, Render networking, HA, or separate managed Key
Value services.

| Workload | Users | P50 | P95 | P99 | RPS | Errors |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Mixed | 100 | 420 ms | 1.5 s | 1.9 s | 99.73 | 0% |
| Dashboard | 100 | 800 ms | 1.3 s | 1.7 s | 95.82 | 0% |
| Dashboard | 150 | 1.3 s | 2.0 s | 2.4 s | 95.61 | 0% |
| Dashboard | 250 | 2.3 s | 3.9 s | 4.7 s | 93.11 | 0% |
| Dashboard | 500 | 4.3 s | 6.4 s | 6.7 s | 102.51 | 0% |
| Dashboard | 1,000 | 9.8 s | 11 s | 11 s | 93.66 | 0% |

The application stayed correct through the highest exercised dashboard load,
but throughput flattened near 100 RPS and latency became unacceptable. Treat
100 dashboard users as the locally responsive data point, not 1,000 as usable
capacity. The older baseline below is preserved for historical comparison.

## Tested topology

- Intel Core i7-1355U, 12 logical CPUs; 15.64 GiB host RAM; NVMe SSD.
- Docker Desktop/WSL2 allocation: 12 CPUs, 7.58 GiB RAM, no service-specific limits.
- Django/Gunicorn: 9 synchronous workers; PostgreSQL 18.6; Redis 8.0.6; one Celery worker.
- Dataset: up to 5,000 students per school, 365 days of history, and up to 1,000 schools for
  selector benchmarks.

## Observed limits

| Workload | Conservative level | First observed degradation |
| --- | --- | --- |
| Composite school peak | 100 concurrent users, zero errors | 120 users, 0.05% errors and P99 8.7 s |
| Teacher attendance | 100 concurrent teachers, zero errors | latency target already exceeded at 100 |
| Legitimate login burst | 100 acceptable for this host | 250 reaches P95 11 s; 500 has 1.26% errors |
| Executive dashboard | 25 concurrent users, P95 520 ms | 50 reaches P95 1.3 s |
| Student profile | 50 concurrent users, P95 510 ms | 100 reaches P95 1.6 s |

Correctness remained intact at every tested level. Latency, CPU, and login error rate define the
capacity boundary, not database corruption or queue loss.

## Starting production recommendation

Start a pilot below 50 concurrently active mixed users per application replica and below 100
simultaneous login attempts per burst, then measure real P95/P99 before raising limits. Keep PDF
render concurrency at four until production CPU/memory measurements justify a change. Configure
alerts for sustained P95 above one second on normal APIs, unexpected 5xx above 0.1%, PostgreSQL
connection saturation, Redis errors, and non-draining Celery queues.

These are deliberately conservative launch controls. They are not a claim that 50 is the maximum
the architecture can support, nor that the local 100-user result transfers directly to production.
