# Phase 19 Baseline

Captured before Phase 19 implementation on 2026-08-21 (Asia/Riyadh).

## Source baseline

- Branch before work: `main`
- Baseline commit: `c6d893ee5d7fc9426f5e3553d1e6b3a26c93a3d5`
- Phase 19 branch: `feature/phase-19-load-security`
- Rescue branch: `rescue/pre-phase-19-load-security`
- Baseline worktree: clean

## Host

| Resource | Value |
| --- | --- |
| Model | ASUS Vivobook X1504VA |
| Operating system | Windows 11 Home Single Language 10.0.26200, 64-bit |
| Processor | Intel Core i7-1355U, 10 physical / 12 logical cores |
| Memory | 15.64 GiB |
| Storage | 476.9 GiB NVMe SSD |

## Docker allocation

| Resource | Value |
| --- | --- |
| Docker Engine | 29.5.3 |
| Docker Compose | 5.1.4 |
| Runtime | Docker Desktop / WSL2 |
| CPUs | 12 |
| Memory | 7.58 GiB |
| Storage driver | overlayfs |
| Kernel | 6.18.33.2-microsoft-standard-WSL2 |

Containers have no explicit per-service CPU or memory limits in the Compose files. Phase 19
therefore reports capacity only for this shared local Docker allocation, not as a production
capacity claim.

## Application topology

- Backend: Django 5.2 served by Gunicorn with 3 synchronous workers and a 60-second timeout.
- Database: PostgreSQL 18.6, persistent Django connections (`CONN_MAX_AGE=60`).
- Cache/broker: Redis 8.0.6.
- Background work: one Celery worker service and one Celery Beat service.
- Frontend: production Vite build served by Nginx in the production-like Compose overlay.

### PostgreSQL defaults observed

| Setting | Value |
| --- | --- |
| `max_connections` | 100 |
| `shared_buffers` | 159.9 MiB |
| `work_mem` | 4 MiB |
| `effective_cache_size` | 5 GiB |
| `random_page_cost` | 4 |
| `max_locks_per_transaction` | 64 |

### Redis defaults observed

| Setting | Value |
| --- | --- |
| `maxmemory` | unlimited within the Docker VM |
| `maxmemory-policy` | `noeviction` |

## Existing verification assets

The repository already contains focused management-command benchmarks for attendance,
attendance analytics and monitoring, student import/profile/purge, devices/roster, Bridge
roster application, warnings, referrals, documents, excuses, staff import, subscriptions,
and the executive dashboard.

No k6, Locust, or JMeter harness was present at baseline. Phase 19 will use a reproducible HTTP
load harness for request distributions and mixed traffic, while retaining the existing focused
benchmarks for selector query counts and domain-heavy workflows.

## Initial test targets

These are release targets from the Phase 19 task, not measured results:

- Normal API P95 below 500 ms.
- Critical attendance path P95 below 750 ms.
- Executive dashboard P95 below 1 second.
- Unexpected HTTP 5xx rate below 0.1%.

All later reports must distinguish local observed capacity, first saturation point, and any
inference. No result from this host is a production sizing guarantee.
