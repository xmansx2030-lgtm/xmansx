# Phase 17 Report

## Status

`PASS` - Production Hardening, PWA, RTL/Responsive, UX, Accessibility baseline,
and the full release regression completed on 2026-08-21 (Asia/Riyadh).

- Baseline: `f77dbdd34bc1db9c6ab1ac8019d405e4ddea095a`
- Branch: `feature/phase-17-production-hardening`
- Rescue branch: `rescue/pre-phase-17-hardening`
- Release commit: the commit containing this report; authoritative hash is in the release output.

## Production And Security

| Gate | Result |
|---|---|
| `DEBUG=False` and production fail-fast validation | PASS |
| Explicit hosts and trusted origins | PASS |
| Secure/HttpOnly/SameSite cookies | PASS |
| 12-hour sliding session and logout invalidation | PASS |
| CSRF valid/missing-origin regression | PASS |
| Login rate limit and enumeration resistance | PASS |
| Tenant, role, IDOR, and platform isolation | PASS |
| Private attachment/document authorization | PASS |
| MIME, corrupt, oversized, and traversal payloads | PASS |
| API no-store and response security headers | PASS |
| CSP without unsafe-inline/eval | PASS |
| Secret/log scan | PASS - no logging match found |
| `npm audit` | PASS - 0 vulnerabilities |

HSTS is 30 days with subdomains. `SECURE_HSTS_PRELOAD=False` is intentional until
the production domains are approved and observed; this is the only Django security
check warning. Password change preserves the rotated current session and invalidates
other sessions through Django's auth hash.

## PWA And Frontend

- Manifest: Arabic, RTL, standalone, correct identity/scope/start URL.
- Icons: 192, 512, and maskable 512 verified from production build.
- Service Worker: Workbox static precache; `/api/**` is NetworkOnly.
- Sensitive cache: no authenticated API/private download is persisted.
- Logout/user/school switch: QueryClient and legacy sensitive caches cleared.
- Offline: explicit failure; no fake attendance success or background mutation queue.
- Update: `phase17-v1 -> phase17-v2` prompt applied by user; session preserved.
- SPA direct routes and strict nginx headers: PASS.
- Initial JS: 659.24 kB / 175.41 kB gzip baseline -> 322.30 kB / 100.58 kB gzip.
- PWA precache: 50 entries, 834.47 KiB. No large-chunk build warning.

The PWA icon was generated with the built-in image generator from the prompt
"school/check mark app icon, blue/teal/coral, no text" and normalized to the three
required PNG assets. No third-party visual asset is loaded at runtime.

## UX, RTL, And Accessibility

Playwright and visual screenshot review covered `360x800`, `390x844`, `768x1024`,
`1024x768`, `1366x768`, and `1440x900`. Teacher, vice principal, counselor,
manager, and platform admin journeys passed. Navigation no longer clips: compact
menu below 1280px and wrapped desktop links above it. Skip link, focus-visible,
accessible icon names, labels, loading/error/empty states, long purge dialog, RTL,
and status text independent of color were verified.

## Release Gates

| Gate | Fresh result |
|---|---|
| Backend full pytest | 684/684 PASS (PostgreSQL + Redis) |
| Focused Phase 17 backend | 96/96 PASS (production settings) |
| Bridge pytest | 9/9 PASS |
| Vitest | 185/185 PASS (24 files) |
| Focused Phase 17 Playwright | 5/5 PASS |
| PWA update E2E | 1/1 PASS |
| Full Playwright | 64/64 PASS, retries=0, 8.7m |
| `ruff check backend` | PASS |
| TypeScript `tsc -b --force` | PASS |
| ESLint | PASS |
| Vite production build | PASS |
| Django `check` | PASS, 0 issues |
| Django `check --deploy` | exit 0; W021 documented; OpenAPI legacy non-gate |
| `makemigrations --check` | PASS - No changes detected |
| Fresh migrate | PASS - `xmansx_phase17_fresh_021956`, zero to head |
| Docker production-like stack | HEALTHY |

## Docker Topology

Compose project `xmansx-phase17-final` ran PostgreSQL 18, Redis 8, gunicorn backend,
Celery worker, Celery beat, and nginx frontend. Database and Redis health checks,
backend readiness, production asset serving, CSP, no-store API headers, service
worker registration, private shared volumes, and migrations all passed.

## Known Limitations

- Offline attendance is intentionally not implemented. The safe behavior is to fail
  visibly and preserve no sensitive operation outside the server.
- HSTS preload remains off by design; enabling it is an irreversible deployment
  decision after domain validation, not a local hardening switch.
- `check --deploy` emits 80 legacy drf-spectacular schema warnings. OpenAPI is not a
  Phase 17 release gate and the command exits 0.
- Lighthouse score was not used as a gate; production Playwright, service-worker,
  manifest, cache, screenshot, and accessibility assertions provide the release evidence.

## Decision

All Phase 17 acceptance gates passed. The repository is ready for Phase 18 after the
logical commits and final clean-tree verification. Phase 18 was not started.

