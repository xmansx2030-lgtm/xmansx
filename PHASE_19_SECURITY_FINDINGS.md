# Phase 19 Security Findings

No Critical or High finding remains open.

| Finding | Severity | Affected area | Evidence | Fix | Regression | Status |
| --- | --- | --- | --- | --- | --- | --- |
| Known cryptography and pytest advisories | HIGH | Python dependencies | `pip-audit` found PYSEC-2026-3552/3553/3554, GHSA-537c-gmf6-5ccf, and PYSEC-2026-1845 | Pinned cryptography 50.x and pytest 9.0.3+ | clean post-upgrade `pip-audit` and full backend suite | CLOSED |
| Redis restart caused avoidable HTTP 500 responses | MEDIUM | Performance cache availability | 59 failures during restart, 1.79% | Added fail-open resilient wrapper for non-security caches; auth throttling retains strict cache | restart run: 3,264 requests, zero failures | CLOSED |
| Concurrent limit checks could observe stale usage | HIGH | Student/staff/device/storage limits | Competing requests could count before either committed | Serialize admission on the school row inside the transaction | four real-PostgreSQL limit race tests | CLOSED |
| Synchronous PDF bursts could exhaust web workers | MEDIUM | Generated documents | Increasing concurrent render load saturated worker CPU/memory | Four-slot PostgreSQL advisory-lock admission control with explicit 429 code | 100-user run: 4 renders, 96 controlled busy responses, zero unexpected errors | CLOSED |
| PWA notification layer intercepted unrelated clicks | LOW | Session/settings UI | Full Playwright settings flow was blocked by offline-ready toast | Notification container no longer captures pointer events; action buttons remain interactive | focused settings Playwright passed | CLOSED |

## Verification summary

Tenant isolation, platform/school role isolation, IDOR protection, CSRF, session invalidation,
login throttling, file validation/private downloads, cache isolation, PWA cache safety, and limit
bypass protection all passed. Tracked-source secret scanning found no secret material. No
repeatable deadlock, cross-tenant leak, privilege escalation, or data corruption was observed.

