# Parent Portal Stage D — Family Requests

## Implemented behavior

- A verified active guardian submits a distinct `ParentExcuseRequest` in `PENDING` state. Submission does not create an administrative excuse or change attendance.
- School manager/vice-principal decisions support approval, rejection, and requesting more information. A guardian can supply additional information or cancel an open request.
- Approval calls the existing `excuses.services.excuses.create_excuse(..., approve_immediately=True)` using the reviewing staff membership. The existing coverage/recalculation services remain authoritative. Recorded `ABSENT` truth remains unchanged.
- `AttendanceCorrectionRequest` accepts only a submitted absence belonging to the linked student. A reviewed approval calls `attendance.services.sessions.correct_student_attendance` and retains `AttendanceChange`, actor, reason, excuse reconciliation, summaries, warning reconciliation, and cache invalidation.
- Requests and reviews use transactions/row locks; open-request uniqueness and terminal-state checks prevent duplicate submissions and double approval. Critical operations acquire a shared school key lock before student, relation and request locks, matching the school-first import order. Joined row locks target only the requested row. Attachment quota writes use a mutually exclusive `NO KEY UPDATE` school lock compatible with the already-held parent key locks.
- Direct family service calls enter a fresh locked `parent_scope`; stale in-memory relations cannot bypass suspension, contact revision, ownership or subscription checks. Excuse review locks relevant sessions and revalidates every stored target against current submitted absence truth. Correction approval rechecks that the authoritative submitted absence still exists before invoking the existing correction service.
- Attachments use existing content validation, a five-file limit, explicit private storage, checksum/size metadata, school storage-capacity locking, and authenticated downloads. Suspended/revoked relations cannot list requests or download files.
- Parent attachments participate in subscription storage usage, private object backup/restore inventory, and student/school purge. Parent accounts consume no staff membership seat.

## Files, models, migrations, pages

- New backend files: `parents/request_models.py`, `parents/request_services.py`, `parents/request_api.py`, `parents/request_serializers.py`, `parents/request_urls.py`, `parents/purge_integration.py`, and `tests/test_parent_requests.py`.
- Updated integration files: `subscriptions/usage.py`, `operations/storage_integrity.py`, and the school-first capacity lock order in `documents/services/generation.py`; the foundation imports request models and registers purge integration from `ParentsConfig.ready`.
- New stage documentation: this report and [Stage E](PARENT_PORTAL_STAGE_E_REPORT.md). Shared frontend/auth/routing changes are inventoried in [Stage F](PARENT_PORTAL_STAGE_F_REPORT.md).
- Request models: `ParentExcuseRequest`, `ParentExcuseAttachment`, `AttendanceCorrectionRequest`. Family communication models are described in the Stage E report.
- Migrations are shared with the foundation: `parents/0001_initial`, contact/RLS migration `0002`, exact relationship identity guards `0003`, and durable contact resolution `0004`. Contact revision uses shared `students/0007`. No separate parallel attendance or excuse tables were created for administrative truth.
- Frontend request forms/history/reviews live in `frontend/src/features/parent/ChildPage.tsx`, `ParentPages.tsx`, and `ParentManagementPage.tsx`; shared parent API types live in `api.ts`. Frontend verification is tracked by the final report.

## APIs and permissions

Base prefix: `/api/v1/`.

- Family: `parent/children/{relation_id}/excuses/`, excuse `resubmit/`, `cancel/`, attachment upload/download; `corrections/` and correction `cancel/`; aggregate `parent/requests/`.
- School: `staff/parents/requests/`, `excuses/{request_id}/decision/`, `corrections/{request_id}/decision/`, and staff attachment download.
- Guardian access uses owned-relation discovery then `parent_scope` within the verified school RLS context. Family writes require an active relationship and writable school subscription. Staff review uses existing manager/vice-principal authorization and subscription policy.
- Responses contain explicit restricted fields. They expose no permanent file URLs, school-wide student datasets, internal counseling notes, or unrestricted administrative serializers.
- Decisions/uploads/downloads generate audit events with identifiers/counts rather than request contents or contact credentials.
- OpenAPI declares restricted output serializers for the actual request/attachment DTOs, binary download media, and the aggregate `EXCUSE`/`CORRECTION` discriminator.
- Lists preserve `items` and include `count`, `next`, and `previous`. The existing `DefaultPagination` default is 25 rows; `page_size` is 1–100 and `page` is 1–1000. Multi-school aggregates count permitted rows, merge scoped windows, and expose older history through subsequent pages. Staff queues retain compatible typed `excuses`/`corrections` page subsets.
- Family POST requests share an atomic per-account security counter of 120 operations per hour. GET polling does not consume this write allowance.

## Verification evidence

Initial targeted command: `.venv/Scripts/python.exe -m pytest tests/test_parent_requests.py --reuse-db -q`.

Initial observed result: **14 passed in 3.25 seconds** on real PostgreSQL. It covered pending/approval separation, administrative coverage without rewriting absence, duplicate/double decisions, resubmission/rejection, validated/private/quota-counted attachments, suspension denial, correction history, draft/present denial, unauthorized guardian access, staff/leave/gate denial, acknowledgement/publication behavior, notifications, and student purge.

The final family suite contains **30 cases**, including independent multi-school relationships and foreign request/file/warning IDs, counselor ownership/private content, an actual private attachment backup/restore round trip, history beyond 100 records, blocked-subscription aggregate denial, emitted OpenAPI contracts, the bounded write limiter, stale relation/case/document rejection, excuse/correction review after the absence is gone, concurrent document generation/acknowledgement, concurrent two-child storage quota enforcement, notification child filtering, and masked school acknowledgement review. All passed in the focused and complete backend runs below.

- Final coordinated focused suite: **115 passed in 32.89 seconds**, including all **30 family cases**, restricted-role HTTP/raw-SQL isolation, real Noor/review concurrency, academic-year, authentication-query and warning-reconciliation regressions.
- Full Docker backend regression: **1184 passed, 0 failed, 0 skipped in 153.94 seconds**, including all 105 parent-feature cases and the existing SMS/leave/gate suites. WeasyPrint was available; one non-failing HarfBuzz-Subset warning was emitted. The fresh run used `POSTGRES_DB=parent_portal_pdf_test`, `config.settings.test`, `/tmp/parent-portal-full-private`, `pytest --create-db --reuse-db -q -rs`, and a read-only mount of repository-root `render.scalable.yaml`. The initial missing-root-file container setup was corrected without source changes. [Stage F](PARENT_PORTAL_STAGE_F_REPORT.md) records the complete command and evidence.
- Frontend regression: **43 test files / 405 tests passed**. `npm run typecheck`, `npm run lint`, and `npm run build` completed successfully.
- Actual PDF/document integration regression in Docker: **66 passed, 0 skipped in 34.30 seconds** across `test_documents.py`, `test_documents_api.py`, `test_integration_12_13.py`, and `test_integration_12_13_api.py`. This executes all 29 PDF cases skipped on Windows. WeasyPrint 70.0 successfully generated actual PDF bytes; PostgreSQL used isolated `test_parent_portal_pdf_test`, private files stayed under the disposable container's `/tmp`, and no real SMS was sent. Evidence: `tmp/parent-final-pdf-docker.log`. One non-failing HarfBuzz-Subset future-dependency warning was emitted.
- Final fresh Playwright journey (`e2e/parent-portal.spec.ts`): **1 passed in 54.2 seconds** (journey 44.7 seconds), superseding the earlier runs. Real local registration/activation in two schools, submitted attendance, excuse approval without rewriting absence, correction, explicit warning/publication acknowledgement, authenticated publication download/foreign denial, suspension, and leave/gate denial were exercised. Phone **390×844**, tablet **768×1024**, and desktop **1366×900** passed RTL, overflow, and browser-error assertions; all three screenshots were inspected (`artifacts/parent-portal-mobile.png`, `artifacts/parent-portal-tablet.png`, `artifacts/parent-portal-desktop.png`). Provider calls used test fixtures; no real SMS was sent.
- Non-BYPASSRLS verification: the actual PostgreSQL restricted-role HTTP and SQL tests passed in the coordinated focused run.

## Security and RLS review

The bounded final review compared the full implementation prompt with models/services, private storage, scoped APIs/output schemas, and the real frontend/E2E flow. No unresolved Stage D/E code or serializer defect was identified. The passing family suite covers foreign relation/request/file IDs and unavailable subscriptions; `test_parent_http_rls.py` additionally passed real HTTP requests using a PostgreSQL `NOSUPERUSER NOBYPASSRLS` role. The focused run also passed raw-SQL context/ownership guards and real Noor/review concurrency. The complete regression roll-up remains in [Stage F](PARENT_PORTAL_STAGE_F_REPORT.md).

## Issues and technical debt

Verification corrected stale relation/case/document access, approval of a target whose absence disappeared, copied withdrawn notification content, omitted warning-action completion, blank output-schema fields, and School/Student/document lock inversions. Existing administrative attendance/excuse services remain authoritative. Private attachment backup/restore uses the existing object-copy inventory; a database-only backup cannot recover private objects. No production recovery or provider delivery is claimed by local tests.

## Required reporting coverage

| Required topic | Evidence in this report |
| --- | --- |
| 1. Actual implementation | Implemented behavior |
| 2. New files | Files, models, migrations, pages |
| 3. Modified files | Integration files and shared Stage F inventory |
| 4. Models | Request models and Stage E communication models |
| 5. Migrations | Shared students0007 and parents0001–0004 |
| 6. APIs | APIs and permissions |
| 7. Frontend pages | ChildPage, ParentPages, ParentManagementPage |
| 8. Permissions | Verified relation, subscription and staff roles |
| 9. Executed tests | Verification evidence |
| 10. Test results | Full backend1184, focused115, PDF66, frontend405 and final Playwright results |
| 11. RLS tests | Security and RLS review |
| 12. Regression results | Focused/PDF/frontend results and mandatory SMS/leave sections |
| 13. Issues | Issues and technical debt |
| 14. Technical debt | Private-object recovery and production evidence limits |
| 15. Remaining work | Remaining work and limits |

## Existing Absence SMS Regression Verification

Family request/notification code imports no school SMS sending service and performs no SMS delivery. `candidate_absences`, `eligible_absences`, provider settings/templates, and SMS retry/deduplication policy remain unchanged. Existing `test_school_sms.py` and parent SMS regression tests passed in the **1184-pass** full Docker run, including recipients without portal accounts/relations and provider/retry/deduplication behavior. Provider calls were mocked; no real SMS was sent. [Stage F](PARENT_PORTAL_STAGE_F_REPORT.md) contains the complete regression evidence and recipient-specific safety exception.

## Existing Student Leave & Gate Workflow Verification

No family leave/early-exit model, form, API, approval, or gate permission was added. The focused tests and final fresh browser journey verified that a guardian without school membership cannot create an administrative leave or access the gate route. Existing `test_student_leaves.py`, `StudentGateRelease` and gate regressions passed in the **1184-pass** full Docker run. [Stage F](PARENT_PORTAL_STAGE_F_REPORT.md) records the complete evidence.

## Remaining work and limits

- Full backend, focused family/RLS/PDF tests, final browser/RTL journey and frontend checks are complete. Central migration/operational evidence is tracked in [Stage F](PARENT_PORTAL_STAGE_F_REPORT.md).
- Tests use isolated local data/files and send no real SMS. No production migration or deployment was performed by this stage.
- Backup object inventory is extended; production storage recovery requires the same separate private-object copy process already documented in `BACKUP_RESTORE.md`.
