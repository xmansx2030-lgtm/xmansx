# Capacity Baseline

This document records observed local capacity, not guaranteed production capacity. Production
sizing must be repeated on the real topology with TLS termination, production database storage,
network latency, monitoring, and explicit container resource limits.

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

