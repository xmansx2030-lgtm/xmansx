# Phase 17 Hardening Baseline

Date: 2026-08-21

Baseline branch: `feature/phase-16-saas-admin`

Baseline commit: `f77dbdd34bc1db9c6ab1ac8019d405e4ddea095a`

Phase 17 branch: `feature/phase-17-production-hardening`

Rescue branch: `rescue/pre-phase-17-hardening`

## Environment

- Git worktree was clean at inspection time.
- Other worktrees exist on separate branches; none points at the Phase 17 worktree.
- Docker Engine 29.5.3 and Docker Compose 5.1.4 are available.
- The Phase 16 isolated Docker stack was still running when this audit began.

## Security Settings Found

- Django settings are split into `base`, `local`, `test`, and `production` modules.
- Production already forces `DEBUG=False` and requires the Django secret, database,
  Redis, field-encryption, and national-ID HMAC environment variables.
- Production enables HTTPS redirect, proxy HTTPS detection, secure session/CSRF cookies,
  HSTS for 30 days, subdomain coverage, and deliberately leaves preload disabled.
- Session cookies are HttpOnly and both session and CSRF cookies use SameSite Lax.
- CORS is closed by default; local development explicitly supports isolated E2E origins.
- A restrictive same-origin CSP exists with no `unsafe-inline` or `unsafe-eval`.
- MIME sniffing protection, strict-origin referrer policy, clickjacking denial, request IDs,
  and structured request logging are present.
- Login CSRF, generic credential errors, rate limiting, session rotation, logout invalidation,
  and temporary-password handling already have backend regression coverage.
- Generated documents use private storage outside `MEDIA_ROOT`; document and excuse downloads
  are tenant-scoped and role-scoped.

## Missing Production Hardening

- Production does not reject wildcard/empty `ALLOWED_HOSTS`, insecure trusted origins, or
  development values in every sensitive setting.
- Session lifetime and browser-close behavior are not explicit or documented.
- Permissions Policy and explicit cross-origin opener/resource policies are absent.
- Production-like Compose does not exist; the current Compose file runs Django and Vite dev
  targets with mounted source.
- Frontend nginx does not yet set production security/cache headers.
- Focused tests do not load and validate the production settings module.

## PWA State

- ADR-007 defines an online-first PWA with no offline attendance queue.
- No PWA plugin, web app manifest, service worker registration, offline page, icons, install
  metadata, or update prompt is implemented.
- There is therefore no current installability or update-flow behavior to verify.

## Caching Risks And Existing Controls

- TanStack Query cache is memory-only; no persisted API cache is configured.
- School-owned query keys consistently use `['school', activeSchoolId, ...]`.
- School switch cancels requests and removes all non-identity query data.
- Logout clears the full QueryClient even when the logout request fails.
- The required service worker must keep `/api/**`, private files, and navigation responses
  containing authenticated data out of persistent runtime caches.

## UX, Responsive, RTL, And Accessibility Risks

- The document root and CSS are Arabic/RTL-first.
- The application header renders every role route inline; on mobile it wraps into a very tall,
  dense header and has no purpose-built compact navigation.
- Existing tables generally need browser verification for intentional horizontal scrolling.
- Long purge flow has prior regression coverage but still requires mobile visual verification.
- Shared buttons have focus-visible styling and forms generally use labels and live alerts.
- No global online/offline status, PWA update prompt, skip link, or consistent page focus target
  exists.
- Icon-only control accessibility and dialog focus behavior require route-level audit.

## Baseline Build And Warnings

- `npm run build`: PASS.
- Baseline main JavaScript: 659.24 kB minified / 175.41 kB gzip.
- Vite emitted one large-chunk warning because all routes are eagerly imported.
- `python manage.py check --deploy` under production settings exited successfully. It reported
  legacy drf-spectacular warnings, HSTS preload being intentionally disabled, and a weak
  audit-only secret warning. OpenAPI warnings are not a Phase 17 release gate.
- No unexpected source-controlled Vite runtime logs were present.

## Repair Direction

1. Add fail-fast production validation and focused security-header/settings tests.
2. Add safe online-first PWA behavior with static-asset caching only and explicit API bypass.
3. Add a user-controlled update flow, offline messaging, and cache cleanup on auth boundaries.
4. Split route bundles safely and introduce compact responsive navigation without changing
   role permissions or business workflows.
5. Add a production-like isolated Compose stack and run all release gates against it.
