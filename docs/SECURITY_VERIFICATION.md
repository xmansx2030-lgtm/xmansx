# Security Verification

Phase 19 security testing is defensive and runs only against the isolated local stack with
synthetic data.

## Automated gates

- Backend security suite: 149/149 passed.
- Phase 19 race/security suite: 11/11 passed.
- Tenant, role, platform-admin, IDOR, CSRF, session invalidation, private-file, cache, and
  subscription-limit isolation are covered by regression tests.
- Invalid UUIDs, dates, enums, oversized values, upload content, and pagination bounds return
  controlled 4xx responses rather than 500s.
- PWA regression covers logout, user switch, and school switch without serving sensitive API
  data from the service-worker cache.

## Runtime checks

The backend and frontend emit CSP, `X-Content-Type-Options`, `Referrer-Policy`, and
`Permissions-Policy`. HTTPS-aware backend requests emit HSTS. CSRF cookies are Secure in the
production settings. The final local E2E origin is explicitly trusted over HTTP only because TLS
terminates outside this isolated test topology.

Authentication rate limiting uses a dedicated strict Redis cache. General performance caches use
a resilient wrapper so a Redis restart degrades latency without disabling access control or
returning avoidable 500 errors. Cache keys include tenant identity and relevant object/version
identity; cross-school regression tests passed.

## Source and dependency review

- Tracked-file secret scan found no private keys or committed runtime credentials.
- Raw SQL sites use fixed statements and bound parameters.
- Backup/restore subprocess calls use argument arrays and never `shell=True`.
- `npm audit --omit=dev` found zero vulnerabilities.
- `pip-audit` initially found four cryptography advisories and one pytest advisory. Minimal
  upgrades to cryptography 50.x and pytest 9.0.3 removed all known advisories. The local
  `xmansx-backend` package is skipped because it is not a PyPI distribution.

Detailed remediations and severity are recorded in `PHASE_19_SECURITY_FINDINGS.md`.

