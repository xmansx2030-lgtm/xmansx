# Phase 19 Report

## Status

All executable release gates passed on the final fresh stack. Git-tree isolation and final commit
metadata are the remaining administrative gates.

- Baseline commit: `c6d893ee5d7fc9426f5e3553d1e6b3a26c93a3d5`
- Branch: `feature/phase-19-load-security`
- Final commit: pending
- Load tool: Locust plus focused Django/Bridge benchmark commands
- Environment: isolated `xmansx-phase19-final` Compose project and synthetic data only

## Environment and datasets

The host is an ASUS Vivobook X1504VA with an Intel Core i7-1355U, 15.64 GiB RAM, and NVMe SSD.
Docker Desktop/WSL2 exposes 12 CPUs and 7.58 GiB RAM. The final stack uses PostgreSQL 18.6, Redis
8.0.6, nine synchronous Gunicorn workers, one Celery worker, Beat, and Nginx. The repeatable
generator supports 1/10/50/100 schools, 500/1,000/3,000/5,000 students per school, staff,
sections, periods, devices, and up to 365 days of history.

## Load and capacity

| Area | Final evidence |
| --- | --- |
| Teacher attendance peak | 100 users; 4,232 requests; 72.51 RPS; P50 630 ms; P95 1.9 s; P99 4.7 s; 0 errors |
| Composite peak | 100 users; 5,677 requests; P50 1.2 s; P95 3.5 s; P99 4.8 s; 0 errors |
| Executive dashboard | P95 250/520/1,300 ms at 10/25/50 users |
| Student profile | P95 310/510/1,600 ms at 25/50/100 users; 365-day selectors 3.2-4.2 ms |
| Devices | 5,000-event batch 4,224.5 ms; dedupe 456.4 ms |
| Roster | compare 5,000 in 545.4 ms; save in 1,346.3 ms |
| Noor import | 5,000 preview 7.27 s; commit 6.33 s; 31.3 MiB peak allocation |
| Excuses | 105-period preview 197 ms/48 queries; approval 648 ms/216 queries |
| Warnings | 5,000-student metrics 81-86 ms/one query |
| Referrals | 5,000 list 46.5 ms/4 queries; inbox 70.6 ms/4 queries |
| Counselor | P95 140/520 ms at 25/50 users |
| Platform admin | P95 51/94 ms at 10/25 users; 1,000-school selector 1,491.25 ms/4 queries |

The observed composite breakpoint is 120 users: 0.05% errors and P99 8.7 seconds. A 500-user
isolated login burst reached P95 23 seconds and 1.26% errors. The recommended initial production
control is below 50 mixed concurrent users per replica, followed by measurement on production
hardware. The initial 500 ms normal API and 750 ms attendance targets are not met at peak on this
host; this is reported as a capacity constraint, not hidden by relaxed assertions.

## Stress, soak, and infrastructure

The 30-minute soak completed 89,953 requests at 49.98 RPS with zero failures (P50 1.4 s, P95
3.3 s, P99 5.4 s). Backend memory rose 8.8 MiB and the worker was flat; no leak was evident.
PostgreSQL peaked at 18 connections, 8 active, and zero deadlocks. Redis peaked at 1,712,408 bytes
and 23 clients. Celery queue depth peaked at 100 in the deliberate worker outage and drained to
zero 14 seconds after restart.

Redis restart recovered with zero failures after cache hardening. Backend restart produced
expected connection resets only during its 3.63-second outage and the immediate recovery run had
zero failures. A 100-user PDF pressure run returned controlled admission responses while health
traffic remained available.

## Concurrency and security

The 11-test PostgreSQL suite proves attendance create/submit, excuse approval, warning issue,
case opening, and student/staff/device/storage limit races. Existing lifecycle tests cover
subscription activation, renew, plan change, and suspend/reactivate races. Bridge queue, ACK-loss,
and retry behavior passed without duplicate application.

Security verification covers tenant and role isolation, platform isolation, IDOR, CSRF, session
invalidation, rate limiting, private files, cache/PWA isolation, and malformed input. The backend
security suite passed 149/149. Dependency audits are clean after focused cryptography and pytest
upgrades. Open Critical findings: 0. Open High findings: 0.

## Performance changes

- Increased configurable Gunicorn process concurrency for I/O-bound request overlap.
- Added school-scoped transactional locking for strict subscription limit admission.
- Added bounded PDF render admission rather than allowing unbounded synchronous CPU pressure.
- Made non-security cache access resilient to Redis interruption while preserving strict auth
  throttling.
- Removed redundant attendance-session work on the already-created fast path.
- Corrected benchmark setup/query accounting; no speculative index was added because query counts
  remained bounded and no EXPLAIN evidence justified one.

Frontend initial JavaScript is 326.67 kB / 101.94 kB gzip versus the Phase 17 baseline of
322.30 kB / 100.58 kB gzip. The small increase came from concurrent UI work, not the Phase 19
load/security harness.

## Backup and restore regression

The Phase 18 smoke drill produced a 2,426,366-byte backup in 1,466 ms and restored it to a separate
database in 3,295 ms. SHA-256 verification passed. Source and restored counts matched: one school,
5,000 students, 87 attendance sessions, one device, and 49 migrations.

## Release gates

| Gate | Latest result |
| --- | --- |
| Backend | 722/722 PASS |
| Focused Phase 19 | 11/11 PASS |
| Backend security | 149/149 PASS |
| Bridge | 11/11 PASS |
| Vitest | 187/187 PASS |
| Playwright | 64/64 PASS, Chromium, one worker, zero retries |
| Ruff / typecheck / lint / build | PASS |
| Django check / migrations check | PASS |
| Django deploy check | exit 0; expected HTTP-local and legacy schema warnings documented |
| Fresh zero-to-head migration | PASS; all 49 migrations applied |
| Docker health | PASS; PostgreSQL/Redis/backend/worker/Beat healthy, frontend running |

## Known limitations and recommendations

- Local Docker has no per-service limits; repeat capacity tests on the pilot topology.
- Synchronous PDF generation is protected but remains CPU-heavy. Keep admission at four and alert
  on controlled busy responses.
- The 1,000-school selector is four queries but takes about 1.49 seconds locally; retain pagination
  and watch production P95 before considering evidence-backed indexing or denormalization.
- TLS terminates outside the local E2E topology; production must retain secure redirect, HSTS, and
  secure-cookie settings.
- Do not proceed to Phase 20 until the clean Git-tree requirement and final commit metadata pass.

## Final backup smoke

After the final E2E seed, a second smoke backup produced 454,094 bytes with SHA-256
`4ca0d0537ed57f034c9620f31bb34c7d3265fb8a6da789c59449d80bf0c03eeb` in 887 ms. Restore to the
separate `xmansx_phase19_restore_final` database completed in 7,440 ms. Source and restore both
contained 5 schools, 53 students, 558 attendance sessions, 4 devices, and 49 migrations.
