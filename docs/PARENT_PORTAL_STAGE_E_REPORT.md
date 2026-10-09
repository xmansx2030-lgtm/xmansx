# Parent Portal Stage E — Family Communication

## Implemented behavior

- Issued/voided `StudentWarning` records are read through the active guardian relationship. Eligibility candidates are never presented as issued warnings.
- `WarningAcknowledgement` is an explicit idempotent action, separate from reading a warning/document/notification and explicitly does not mean acceptance of the warning contents.
- `FamilyPublication` contains only the title/body/action/date/document that an authorized staff member explicitly chooses to publish. Internal counselor case/session/plan/referral contents are never automatically copied.
- A counselor can publish for an assigned case only; a manager/vice-principal can publish permitted student content and explicitly authorize a generated document. A counselor cannot publish an administrative document through this endpoint.
- Published document downloads require the active relation, unretracted publication and `READY` document. When a warning is linked it must be issued; permitted READY documents without a warning do not require an artificial warning. Downloads reuse the original immutable stored file and reject voided access. This wording was clarified during independent verification without a runtime policy change.
- Publication acknowledgement (`FamilyPublicationAcknowledgement`) is explicit and distinct from completing a requested action. Revocation removes parent content/download access while retaining publication history and actor/time/reason.
- Publication/download/acknowledgement operations lock the current publication and linked warning/document state. Critical operations acquire the shared school key lock before student locks; linked documents retain the warning-before-document order. Publishing and revoking recheck the current locked case assignment. Revocation atomically clears the matching notification body and outstanding action, so old notifications cannot expose withdrawn content.
- `ParentNotification` tracks read time and action-completion time independently. Explicit warning acknowledgement closes its warning notification action; catch-up respects an earlier acknowledgement. Publication acknowledgement remains separate from completing the physical action requested by the school. Explicit action completion verifies the current issued/unrevoked target; generic relationship-review notices can be resolved by school review rather than by parent self-approval. A voided warning notice no longer requires acknowledgement and reflects its cancellation. Notification mutation re-fetches locked state before returning a response.
- Request decisions and explicit publications create notifications. An idempotent batched inbox catch-up reads submitted absences and recorded morning lateness from the preceding 30 days, plus issued warnings; older already-created notices remain paginated history. It neither creates nor sends absence SMS. Pending/draft attendance cannot generate a confirmed absence notice.
- Relationship-status notifications contain generic text and remain visible when a relation is suspended; student/request/publication/file details remain blocked.
- Permitted active notifications include child and school names. Optional `relation_id` filtering checks only the caller's owned relation index; foreign and absent relation IDs return the same empty envelope. Generic unavailable-relation notices expose null names.
- Staff publication responses include `ack_count` and the latest 20 acknowledgements with masked guardian labels. Manager/vice-principal acknowledgement review is paginated and school-scoped; counselors receive acknowledgement detail only on their own assigned-case publications.

## Files, models, migrations, frontend

Backend implementation shares the Stage D new files (`request_models.py`, `request_services.py`, `request_api.py`, `request_serializers.py`, `request_urls.py`, `purge_integration.py`, and `test_parent_requests.py`). Modified integrations are subscription storage usage, private object inventory, foundation model/AppConfig imports, and school-first document capacity locking. Additional models are `FamilyPublication`, `FamilyPublicationAcknowledgement`, `WarningAcknowledgement`, and `ParentNotification` in shared `parents/0001_initial`; contact/RLS `0002`, exact identity `0003`, and durable contact resolution `0004` protect their scope. Contact revision uses shared `students/0007`.

Frontend warning/publication/acknowledgement cards and notifications use `ChildPage.tsx`, `ParentPages.tsx`, and `ParentShell.tsx`; school publication/revocation and acknowledgement review use `ParentManagementPage.tsx`. Shared types/contracts are in `api.ts`, frontend regression coverage in `parent.test.tsx`, and the real browser journey in `e2e/parent-portal.spec.ts`. Shared frontend/auth/routing changes are inventoried in [Stage F](PARENT_PORTAL_STAGE_F_REPORT.md).

## APIs, authorization, audit

Base prefix: `/api/v1/`.

- `parent/children/{relation_id}/warnings/` and `warnings/{id}/acknowledge/`.
- `parent/children/{relation_id}/publications/`, publication `download/`, and `acknowledge/`.
- `parent/notifications/`, notification `read/`, and `complete-action/`.
- `staff/parents/publications/` supports create/list and an optional safe `case_id` filter. Non-administrative counselors see their assigned cases only. `staff/parents/publications/{id}/revoke/` verifies current responsibility.
- `staff/parents/acknowledgements/` lists warning/publication acknowledgements for manager/vice-principal review, without full guardian mobile numbers or unrelated-school records.
- All family student reads/downloads are scoped to an active owned relationship, the correct school, and permitted subscription state. Aggregate lists enter one verified tenant context at a time.
- Publication, revocation, explicit acknowledgements, and file access are audited without copying counseling contents or credentials into audit metadata.
- Private responses prohibit caching; private document storage exposes no permanent public URL. Existing PWA API network-only policy remains authoritative.
- `parents/request_serializers.py` declares narrow typed response DTOs and paginated OpenAPI envelopes. All lists include `items/count/next/previous`; the default page size is 25, maximum 100, with page numbers capped at 1000. Aggregate notifications count and merge school-scoped windows while excluding sensitive rows from unavailable subscriptions/relations.
- Family POST operations use the same per-user atomic Redis limiter (120 per hour); GET polling remains unaffected.

## Verification evidence

The initial Stage D/E targeted backend command ran **14 tests successfully in 3.25 seconds**. It verified explicit/idempotent warning acknowledgement, text publication/revocation, explicit document publication/voided access denial, notification-read separation, private downloads, and generic-only notifications after suspension.

The final **30-case** family suite includes added counselor ownership/internal-text and multi-school tests, stale case/document/relation rejection, withdrawn notification body/action clearing, cancellation/action semantics, pagination beyond 100 historical rows, blocked-subscription minimization, explicit OpenAPI outputs, actual private-object backup/restore, rate limiting, concurrent document generation/acknowledgement and storage quota enforcement, child notification filtering, warning-ack catch-up, and masked school acknowledgement review. Completed coordinated results are:

- Final coordinated focused suite: **115 passed in 32.89 seconds**, including all **30 family cases**, restricted-role HTTP/raw-SQL isolation, real Noor/review concurrency, academic-year, authentication-query and warning-reconciliation regressions.
- Full Docker backend regression: **1184 passed, 0 failed, 0 skipped in 153.94 seconds**, including all 105 parent-feature cases and the existing SMS/leave/gate suites. WeasyPrint was available; one non-failing HarfBuzz-Subset warning was emitted. The fresh run used isolated `POSTGRES_DB=parent_portal_pdf_test`, `config.settings.test`, `/tmp/parent-portal-full-private`, `pytest --create-db --reuse-db -q -rs`, and a read-only repository-root `render.scalable.yaml` mount. The initial missing-root-file container setup was corrected without source changes. [Stage F](PARENT_PORTAL_STAGE_F_REPORT.md) records the complete command and evidence.
- Frontend regression: **43 test files / 405 tests passed**; TypeScript typecheck, ESLint and production/PWA build completed successfully.
- Docker PDF/document integration regression: **66 passed, 0 skipped in 34.30 seconds**, including all 29 PDF cases skipped on Windows. WeasyPrint 70.0 rendered real PDFs with the repository's container libraries. The four document/integration suites used isolated `test_parent_portal_pdf_test` and disposable `/tmp` private files; the container exited and was removed. Evidence: `tmp/parent-final-pdf-docker.log`. One non-failing HarfBuzz-Subset future-dependency warning was emitted.
- Final fresh Playwright journey: **1 passed in 54.2 seconds** (journey 44.7 seconds), superseding the earlier runs. It exercised real local registration/activation across two schools, live submitted attendance, family requests/decisions, explicit acknowledgements, contextual notifications, safe publication/private download, foreign-file denial, independent suspension, and leave/gate denial. Phone **390×844**, tablet **768×1024**, and desktop **1366×900** passed RTL, overflow, and browser-error assertions. All three screenshots were inspected: `artifacts/parent-portal-desktop.png`, `artifacts/parent-portal-mobile.png`, and `artifacts/parent-portal-tablet.png`.
- Restricted PostgreSQL RLS: actual non-BYPASSRLS HTTP and SQL tests passed in both the coordinated focused run and complete backend regression.
- Performance: notification source synchronization is batched to avoid one upsert per attendance period. No throughput/latency claim is made without a benchmark.

## Security and RLS review

The final bounded review compared the complete user prompt with current warning/publication/notification models and services, output serializers/OpenAPI, scoped staff acknowledgement review, frontend interactions and the actual E2E script. No unresolved Stage E code or schema defect was identified. Passing family and real HTTP `NOSUPERUSER NOBYPASSRLS` tests cover wrong-school existing IDs, private files, suspended grants and scoped acknowledgement history. Raw-SQL context/ownership guards and real Noor/review concurrency also passed. The complete regression roll-up remains in [Stage F](PARENT_PORTAL_STAGE_F_REPORT.md).

## Issues and technical debt

Resolved defects include stale counselor responsibility/document state, withdrawn notification text/action, acknowledgement/download races, missing warning action completion, omitted child context/filtering, blank output-schema fields and School/Warning/document lock ordering. The bounded staff acknowledgement preview exposes total count and latest 20 masked rows; the paginated school review exposes full history. Family text still requires explicit professional approval; no internal case contents are inferred safe automatically. Local mocks cannot demonstrate real SMS delivery, production throughput or production backup recovery.

## Required reporting coverage

| Required topic | Evidence in this report |
| --- | --- |
| 1. Actual implementation | Implemented behavior |
| 2. New files | Shared Stage D files and frontend/E2E inventory |
| 3. Modified files | Integration files and shared Stage F inventory |
| 4. Models | Publication, acknowledgements and notifications |
| 5. Migrations | Shared students0007 and parents0001–0004 |
| 6. APIs | APIs, authorization, audit |
| 7. Frontend pages | ChildPage, ParentPages, ParentShell, ParentManagementPage |
| 8. Permissions | Active relation and current assigned-case/staff authorization |
| 9. Executed tests | Verification evidence |
| 10. Test results | Full backend1184, focused115, PDF66, frontend405 and final Playwright |
| 11. RLS tests | Security and RLS review |
| 12. Regression results | Focused/PDF/frontend results and mandatory SMS/leave sections |
| 13. Issues | Issues and technical debt |
| 14. Technical debt | Publication judgment and local evidence limits |
| 15. Remaining work | Remaining work and limits |

## Existing Absence SMS Regression Verification

This communication layer sends no SMS for excuses, corrections, warnings, lateness, counseling, or relation changes. No provider, template, eligibility, duplicate prevention, retry, or absence-SMS timing was modified. Existing `test_school_sms.py` and parent SMS regression tests passed in the **1184-pass** full Docker run, including school SMS without portal accounts/relations. The original flow remains independent of portal account existence. No real SMS was sent; [Stage F](PARENT_PORTAL_STAGE_F_REPORT.md) records complete evidence and the narrowly scoped recipient-safety exception.

## Existing Student Leave & Gate Workflow Verification

No leave/early-exit communication or workflow was added. Administrative `student_leaves`, `StudentGateRelease`, and guard APIs remain separate staff workflows. Guardian denial passed focused tests and the final fresh browser journey. Existing administrative leave/gate regressions passed in the **1184-pass** full Docker run; [Stage F](PARENT_PORTAL_STAGE_F_REPORT.md) records the complete evidence.

## Remaining work and limits

Full backend, focused family/RLS/PDF tests, the final browser/RTL journey and frontend checks are complete. Central migration/operational evidence is tracked in [Stage F](PARENT_PORTAL_STAGE_F_REPORT.md). No production SMS, production writes, migrations, or deployment were performed by this stage. Published family text remains a professional staff decision; the system does not automatically infer that internal counseling content is safe to share.
