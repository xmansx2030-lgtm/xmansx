# Parent Portal Stage B — Registration & Activation

## Implemented scope and files

Each school can explicitly enable its UUID registration link and QR. Public
registration accepts the parent's name, normalized Saudi mobile, school student
identifier and relationship type. It encrypts sensitive fields, creates no account
and returns the same acknowledgement for matching, missing or duplicate identities.
The school reviews masked identity matching/sibling candidates, explicitly selects
one student and records its verification before approval.

New backend files: `parents/services.py`, `api.py`, `serializers.py`, `urls.py`,
`rate_limit.py`, `tests/test_parent_portal.py`, concurrency tests. Frontend:
`RegistrationPage.tsx`, `ActivationPage.tsx`, settings/QR, account and school
management pages under `frontend/src/features/parent`. Auth destination/guards,
`Me.has_parent_portal`, routes, public entry and space switching extend existing auth.

Models/migrations are the Stage A foundation; this stage creates no parallel User
or staff membership table. Production origin is configured through
`PARENT_PORTAL_BASE_URL`; a missing/invalid trusted origin rejects activation-link
workflows safely without breaking startup of the existing application.

## APIs, pages and permissions

Public API: registration metadata/POST, opaque receipt status/resubmission,
activation check/POST. Staff API: school settings, paginated request queue/detail,
documented approval/rejection/information request, activation reissue, paginated
relationship list and documented relationship decisions.

Public POSTs enforce CSRF and atomic fail-closed Redis limits. Parent password
change requires the existing password and validates the new password, locks the
account, rotates the current session and invalidates other session authentication.
Manager enables registration; manager/vice-principal review individual grants.

Activation tokens have 256-bit randomness, SHA-256 storage, 48-hour default
expiry, school/request/contact revision binding, single-use consumption and explicit
revocation. The browser removes the URL fragment immediately and keeps the token
only in memory. GET does not consume a token. Locks follow school KEY SHARE→
student→request→token, matching the existing Noor import's school-first order.
Existing global accounts require their owner's authenticated session and keep
password/name/employment intact. The same account can independently activate
children in multiple schools. Revocation in one school affects only that relationship.

School SMS uses existing encrypted provider credentials in a separate activation
delivery lifecycle. FAILED and ambiguous UNKNOWN outcomes are visible; no automatic
retry occurs. Explicit verified reissue revokes older tokens. Manual delivery is
available after documented verification and cannot reset an existing account.
Staff can inspect the last ten delivery/expiry/use/revocation records without tokens.

## Executed verification

Intermediate integration: **162 passed** across feature and related regressions.
Actual browser journey passed registration→staff approval→new account activation→
second school activation on the same account with no staff membership. Tests cover
Arabic numerals, generic responses, expiry/replay/reissue/contact changes, wrong
owner/existing employee, CSRF/rate limits and concurrent single-use activation.
Final password-session, delivery/schema and complete regression counts are in
[Stage F](PARENT_PORTAL_STAGE_F_REPORT.md).

The final frontend run executed **43 files / 405 tests**. Typecheck, lint and the
production/PWA build succeeded. The real final browser lifecycle passed in54.2s
(journey44.7s), including phone/tablet/desktop, against the final backend and fresh
isolated fixture. The final
focused115-case backend run passed in32.89s. Restricted-role RLS tests exercise
actual HTTP, not only mocked queries;
parent discovery never expands the owner into school staff authority.

## Existing Absence SMS Regression Verification

Activation does not create `AbsenceSmsNotice` or change absence candidate/eligible
filters. Only registration/activation and existing absence SMS may send messages;
password changes, requests, warnings and counseling notifications send none.
Provider tests are mocked; no real SMS was sent. Stage F records final SMS results.

## Existing Student Leave & Gate Workflow Verification

Parent auth creates no membership or gate authority. Negative HTTP/E2E tests verify
denial of administrative leave creation and gate routes. Existing leave/gate
regression remains in the full backend run.

## Required reporting coverage

| Required topic | Evidence in this report |
| --- | --- |
| 1. Actual implementation | Implemented scope and registration/activation lifecycle |
| 2. New files | Implemented scope and files; final Stage F inventory |
| 3. Modified files | Auth guards/payload/routing; final Stage F inventory |
| 4. Models | Shared foundation models from Stage A |
| 5. Migrations | Shared students0007 and parents0001–0004; no separate stage migration |
| 6. APIs | APIs, pages and permissions |
| 7. Frontend pages | Registration, activation, account, settings/QR and management |
| 8. Permissions | CSRF, limits, owner authentication and manager/vice-principal review |
| 9. Executed tests | Executed verification and final Stage F command record |
| 10. Test results | Intermediate162, frontend405 and real browser evidence; Stage F final totals |
| 11. RLS tests | Restricted PostgreSQL/HTTP role verification recorded in Stage F |
| 12. Regression results | Mandatory SMS and leave/gate sections |
| 13. Issues | Approval persistence, delivery ambiguity and generic duplicate receipts |
| 14. Technical debt | Lost-receipt verification and production delivery evidence |
| 15. Remaining work | Separately authorized production SMS and school rollout |

## Issues, debt and remaining work

Keep the original opaque registration receipt securely. Duplicate public submissions
do not receive somebody else's receipt or disclose their request state; the new
generic receipt stays pending. A lost receipt can be handled by the school through
verified activation delivery after review. No plaintext receipt/token is persisted
in browser offline storage. Production SMS delivery and school rollout remain
unperformed and need authorization; local provider outcomes are mocks.
