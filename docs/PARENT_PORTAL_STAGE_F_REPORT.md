# Parent Portal Stage F — Final Hardening

Implementation date: 2026-10-08. Branch: `feature/parent-portal-20261008`.
Initial SHA: `286c7163b57686575f4cb3785532c239fa338624`. Initial tree clean.
Delivery consists of local working-tree changes; no push or production deployment.

## Final delivered scope and inventory

Stages [A](PARENT_PORTAL_STAGE_A_REPORT.md), [B](PARENT_PORTAL_STAGE_B_REPORT.md),
[C](PARENT_PORTAL_STAGE_C_REPORT.md), [D](PARENT_PORTAL_STAGE_D_REPORT.md),
[E](PARENT_PORTAL_STAGE_E_REPORT.md), [architecture](PARENT_PORTAL_ARCHITECTURE.md),
[ADR-012](adr/ADR-012-guardian-access-independent-of-imported-contact.md) and
[operations](PARENT_PORTAL_OPERATIONS.md) describe implemented models, permissions,
APIs, frontend pages, migration/rollback and documented limits.

New backend app: foundation/contact/request models, services, explicit input/output
serializers, access/RLS context, atomic rate limits, whitelisted APIs/URLs, private
storage/purge integrations and synthetic E2E fixture command. Additive migrations:
student0007 and parents0001–0004. New tests cover contacts, registration/activation,
family requests, concurrency/workload, real HTTP RLS and absence SMS regression.
Modified existing integrations are confined to auth payload/routing, protected
student contact/Admin/import/merge, account reset/purge, recipient-specific SMS
safety, attachment quota and private inventory. Frontend adds a separate Arabic
parent space, school administration/QR and account destination/cache handling.

## Verification record

Baseline backend: **1043 passed, 29 skipped in204.12s**. Baseline frontend:
**42 files, 373 tests passed in105.32s**. Intermediate integration after fixing
approval persistence, fixture proof and an SMS normalization regression:
**162 passed in37.15s** (`tmp/parent-stage-integration-v2.log`).

Final focused command executes all nine `test_parent_*.py` suites plus
`test_queries.py` and `test_student_reconciliation_audit.py` using
`python -m pytest <those files> --reuse-db -q -s -rs` from the backend venv.
Result: **115 passed in32.89s** (`tmp/parent-final-focused-all.log`). This includes
all **30 family request/communication tests**, the six academic-year regressions,
six account-query budget cases, actual restricted-role SQL/HTTP and concurrent Noor.

Final frontend: **43 files / 405 tests passed in100.66s**; `npm run typecheck`,
`npm run lint`, and `npm run build` succeeded, including the production/PWA build.
Final real Playwright repeat: **1 passed in54.2s** (journey44.7s), final server and
fresh synthetic fixture. It covers registration/manual approval/activation,
one account in two schools, real draft/submitted attendance and polling/history,
excuse/correction review, separate explicit acknowledgements, contextual notifications,
private published PDF download/foreign denial, suspension and leave/gate denial.
Final desktop1366x900, tablet768x1024 and mobile390x844 screenshots were visually inspected:
`artifacts/parent-portal-desktop.png`, `artifacts/parent-portal-tablet.png`,
`artifacts/parent-portal-mobile.png`.
No horizontal page overflow or browser page error was observed.

Windows baseline/full runs skipped29 existing PDF-dependent tests because the
native engine is unavailable. A separate existing Docker image with the final repo
bind-mounted ran all four document/integration suites: **66 passed, zero skipped
in34.30s** (`tmp/parent-final-pdf-docker.log`). Actual WeasyPrint70 rendering produced
PDF bytes; LinuxPython3.13.15/Django5.2.17/pytest9.1.1. One HarfBuzz-Subset deprecation
warning does not fail tests. The complete backend result follows.

**Final full backend:1184 passed, zero failed, zero skipped in153.94s.**
Evidence: `tmp/parent-final-full-docker.log`; disposable Docker container exit0.
The first full Windows pass attempt identified two real compatibility failures
(redundant `/me` context queries and retained contact-review reconciliation), both
corrected and verified by the115-case focused run and final full Docker suite.
The first full Docker attempt found only two root-blueprint tests unable to read
`render.scalable.yaml`, because Compose mounts just `backend` at `/app`. A read-only
mount of that existing root file corrected the test harness; no blueprint/source
change or test exclusion was used. The final command from the repository root was:

```powershell
docker compose run --rm --no-deps --user root --volume "C:/Users/manso/Desktop/projects/xmansx/render.scalable.yaml:/render.scalable.yaml:ro" -e POSTGRES_DB=parent_portal_pdf_test -e DJANGO_SETTINGS_MODULE=config.settings.test -e GENERATED_DOCUMENTS_ROOT=/tmp/parent-portal-full-private backend pytest --create-db --reuse-db -q -rs
```

Django used the isolated `test_parent_portal_pdf_test` database and Redis test db2;
local application data was not the test database. All105 new parent feature cases
and existing regressions ran, including private-file backup/restore and actual PDF.

`ruff check .`, `manage.py check` and `makemigrations --check --dry-run` succeeded.
Local `showmigrations parents students` confirms all five additive migrations
applied. `git diff --check` found no whitespace errors. OpenAPI generation/validation
completed; **46 parent/staff-parent paths / 51 operations** have typed success
responses, including private binaries, and parent-specific schema tests pass.
The whole legacy schema still reports18 warnings and520 diagnostics (97 unique)
from other APIViews/enum/operation collisions; parent views emit no such diagnostics.
It is not accurate to call the entire pre-existing API schema clean.

## RLS, concurrency and performance

Tests create actual PostgreSQL `NOSUPERUSER NOBYPASSRLS` roles and execute the
real policies, including authenticated HTTP and existing foreign private file IDs.
Concurrent activation consumes once; duplicate registrations produce one pending
request; actual Noor import races staff relationship review under independent
connections. A 2000-other-guardian dataset measures five owned child polls and
query counts. Final measured five polls: **125 SQL queries total**, local durations
**[38.62,33.95,44.09,50.32,71.58]ms**, while the real browser journey was also active.
Actual Noor commit vs relationship review completed in**145.58ms**, preserved
the new contact/revision and denied the old relationship. Earlier local samples
are not production throughput evidence. Account `/me` now uses one additional owned
relationship lookup: budget8 without an active school,11 with its existing school
membership context, independent of1/4/20 schools. Redundant nested RLS context
round trips were removed; the restricted-role HTTP test also verifies `/me`.

Deadlock verification established the shared school→student→relation/source order.
Parent operations use school KEY SHARE; the existing Noor writer keeps FOR UPDATE.
Document production acquires its existing school capacity lock before warning/file;
private attachment capacity uses NO KEY UPDATE, avoiding competing lock upgrades
without weakening quota serialization. Actual concurrent PDF generation/acknowledgement
and two-child attachment quota tests pass. PostgreSQL INERROR cleanup preserves the
original error rather than replacing it with a context-restore exception.

## Existing Absence SMS Regression Verification

The passing1184-case final command includes `test_school_sms.py` and all five
`test_parent_sms_regression.py` cases.
No portal registration prerequisite, altered candidate/eligible/completeness rules,
new absence retry policy or settings/template change was introduced. Explicit
student+number recipient blocks are the narrowly documented safety exception.
All provider interactions in tests are mocked; no real SMS was sent.

## Existing Student Leave & Gate Workflow Verification

The passing1184-case final backend regression includes the existing eleven
`test_student_leaves.py` cases and their gate operations. Actual E2E checks that
parent-only auth receives403 from leave
creation and gate routes. No parent electronic leave/early-release API, model,
form, gate permission or SMS was added.

## Issues corrected during verification

- Approval must be persisted before its activation insert to satisfy the exact-child
  database guard. Both writes remain in one locked transaction.
- Comparison-only normalization preserves legacy absence-SMS invalid-number behavior.
- Historical incomplete/missing-summary days must remain visible; unknown expected
  period counts cannot certify a complete day. Own marks are batched/minimized.
- Prepared UPCOMING enrollment cannot replace today's class or saved attendance year.
  Saved summary/context and matched year/section win; unique historical own-roster
  sessions retain their year when the date-covered calendar is ambiguous.
- Duplicate reconciliation retains only contact-review evidence on archived sources.
  It still refuses to move any guardian grant/request/publication to another student.
- Account query verification compares both selected/unselected-school contexts and
  stays constant across1/4/20 schools rather than confusing automatic selection with N+1.
- School/global account resets and contact writes cannot bypass guardian ownership.
- Family publication revocation must close/scrub copied notifications and serialize
  acknowledgements/downloads with current publication/source state.
- Parent-only auth avoids the staff school-picker loop; shared-space cache cleanup,
  multipart headers, keyboard tabs and delivery failure/unknown states have tests.

## Debt, skips and remaining operational work

The Docker runs execute PDF cases omitted on Windows. Whole-schema legacy diagnostics
remain explicit above. Coordinated future HMAC rotation must include additive parent
lookup/contact/recipient hashes; retain the existing key until then. Multiple recorded
years for one historical day without saved context/summary cannot safely be merged
by a single-day DTO; unknown expected counts remain incomplete. Local tests do not prove real SMS
inbox receipt, production capacity, deployed SHA or production recovery. Global
mobile requests remain pending for a separately approved ownership process.
The production origin, deployment/migrations, school enablement and provider smoke
delivery are operational tasks requiring explicit authorization. No such action
was performed by this implementation.

## Required reporting coverage

| Required topic | Evidence in this report |
| --- | --- |
| 1. Actual implementation | Final delivered scope; linked A–E behavior |
| 2. New files | Exact 63-file list below |
| 3. Modified files | Exact 41-file list below |
| 4. Models | Seven foundation models in Stage A; seven request/publication/acknowledgement/notification models in D/E |
| 5. Migrations | students0007, parents0001–0004; local applied and no missing migrations |
| 6. APIs | 46 typed parent/staff-parent paths, 51 operations; architecture and A–E contracts |
| 7. Frontend pages | Registration, activation, children/date/history/requests/notifications/account; school settings and management |
| 8. Permissions | Owned active relation/subscription, manager/vice-principal review, counselor assigned-case publication; no staff/gate authority for parents |
| 9. Executed tests | Verification record and coordinated commands |
| 10. Test results | Measured focused, frontend, E2E, PDF and final full regression results |
| 11. RLS tests | Actual NOSUPERUSER NOBYPASSRLS SQL and authenticated HTTP |
| 12. Regression results | Mandatory absence SMS and leave/gate sections; full backend/frontend runs |
| 13. Issues | Issues corrected during verification and original error/lock ordering evidence |
| 14. Technical debt | Whole-schema diagnostics, future HMAC rotation, ambiguous legacy historical facts |
| 15. Remaining work | Separately authorized production origin/release/migrations/enablement/smoke delivery |

## Exact file inventory

Initial tree was clean. The following are the delivered working-tree changes;
no package dependency or lockfile change was made. Runtime screenshots, private
synthetic fixture metadata and test logs are ignored artifacts, not source files.

New files:

```text
backend/parents/__init__.py
backend/parents/access.py
backend/parents/api.py
backend/parents/apps.py
backend/parents/contact_api.py
backend/parents/contact_security.py
backend/parents/contact_urls.py
backend/parents/management/__init__.py
backend/parents/management/commands/__init__.py
backend/parents/management/commands/seed_parent_e2e.py
backend/parents/migrations/0001_initial.py
backend/parents/migrations/0002_contact_security_and_rls.py
backend/parents/migrations/0003_exact_family_identity_guards.py
backend/parents/migrations/0004_durable_contact_resolution.py
backend/parents/migrations/__init__.py
backend/parents/models.py
backend/parents/purge_integration.py
backend/parents/rate_limit.py
backend/parents/request_api.py
backend/parents/request_models.py
backend/parents/request_serializers.py
backend/parents/request_services.py
backend/parents/request_urls.py
backend/parents/security.py
backend/parents/selectors.py
backend/parents/serializers.py
backend/parents/services.py
backend/parents/urls.py
backend/students/migrations/0007_guardian_contact_revision.py
backend/tests/test_parent_concurrency_performance.py
backend/tests/test_parent_contact_security.py
backend/tests/test_parent_enrollment_years.py
backend/tests/test_parent_http_rls.py
backend/tests/test_parent_noor_concurrency.py
backend/tests/test_parent_portal.py
backend/tests/test_parent_requests.py
backend/tests/test_parent_sms_regression.py
backend/tests/test_parent_sql_context_errors.py
docs/PARENT_PORTAL_ARCHITECTURE.md
docs/PARENT_PORTAL_CONTACT_SECURITY.md
docs/PARENT_PORTAL_OPERATIONS.md
docs/PARENT_PORTAL_STAGE_A_REPORT.md
docs/PARENT_PORTAL_STAGE_B_REPORT.md
docs/PARENT_PORTAL_STAGE_C_REPORT.md
docs/PARENT_PORTAL_STAGE_D_REPORT.md
docs/PARENT_PORTAL_STAGE_E_REPORT.md
docs/PARENT_PORTAL_STAGE_F_REPORT.md
docs/adr/ADR-012-guardian-access-independent-of-imported-contact.md
frontend/e2e/parent-portal.spec.ts
frontend/playwright.parent.config.ts
frontend/src/features/auth/destination.ts
frontend/src/features/parent/ActivationDelivery.tsx
frontend/src/features/parent/ActivationPage.tsx
frontend/src/features/parent/ChildPage.tsx
frontend/src/features/parent/ParentManagementPage.tsx
frontend/src/features/parent/ParentPages.tsx
frontend/src/features/parent/ParentSettingsTab.tsx
frontend/src/features/parent/ParentShell.tsx
frontend/src/features/parent/RegistrationPage.tsx
frontend/src/features/parent/SpaceSwitchButton.tsx
frontend/src/features/parent/api.ts
frontend/src/features/parent/parent.test.tsx
frontend/src/features/parent/shared.tsx
```

Modified existing files:

```text
.env.example
.gitignore
backend/accounts/admin.py
backend/accounts/api/serializers.py
backend/common/tenant_rls.py
backend/config/settings/base.py
backend/config/settings/production.py
backend/config/urls.py
backend/documents/services/generation.py
backend/operations/storage_integrity.py
backend/school_sms/services.py
backend/school_sms/tasks.py
backend/staff/services/management.py
backend/students/admin.py
backend/students/api/views.py
backend/students/models.py
backend/students/services/imports/commit.py
backend/students/services/imports/comparison.py
backend/students/services/manual.py
backend/students/services/manual_merge.py
backend/students/services/reconciliation.py
backend/subscriptions/services/school_accounts.py
backend/subscriptions/services/school_purge.py
backend/subscriptions/usage.py
backend/tests/test_queries.py
backend/tests/test_student_reconciliation_audit.py
docs/SCHOOL_SMS.md
frontend/src/api/client.test.ts
frontend/src/api/client.ts
frontend/src/app/AppShell.tsx
frontend/src/components/Tabs.tsx
frontend/src/features/auth/ChangeInitialPasswordPage.tsx
frontend/src/features/auth/LoginPage.tsx
frontend/src/features/auth/SelectSchoolPage.tsx
frontend/src/features/auth/guards.tsx
frontend/src/features/auth/returnTo.test.ts
frontend/src/features/auth/returnTo.ts
frontend/src/features/public/PublicRootPage.tsx
frontend/src/features/settings/SettingsPage.tsx
frontend/src/routes/index.tsx
frontend/src/types/auth.ts
```
