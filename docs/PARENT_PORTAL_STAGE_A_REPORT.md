# Parent Portal Stage A — Foundation & Security

Implementation date: 2026-10-08. Local branch: `feature/parent-portal-20261008`.
Baseline: `286c7163b57686575f4cb3785532c239fa338624` (initial working tree clean).

## Implemented scope

The portal reuses the global `accounts.User` and cookie/session authentication. A
parent has independent, explicitly approved `GuardianStudentRelation` records;
imported Noor contacts are never login authority or an automatic relationship.
Owned relation discovery reads only identifiers/status, then every student read,
write, acknowledgement and private download uses the verified school's RLS context.
Parents receive no staff membership, role or `MAX_STAFF` seat.

Contact changes are protected by PostgreSQL triggers, including direct SQL,
`update`, `bulk_update`, Admin and imports. Meaningful changes advance the revision
once, suspend affected contact-bound grants, invalidate associated activations and
create review/audit records in the same transaction. Equivalent phone formats do
not advance revision. Independently verified relationships remain unaffected.
Returning an old number does not restore access. Global login phone edits are
blocked for guardian accounts; documented change requests stay pending for a
separately approved account ownership process. School employee password resets
cannot take over a guardian account. Purge preserves users required by another school.

## Files, models and migrations

New files: `parents/models.py`, `access.py`, `security.py`, `contact_security.py`,
`contact_api.py`, `contact_urls.py`, `purge_integration.py`, foundation migrations,
contact/isolation/concurrency tests, architecture document and ADR-012.

Modified integrations: student model/Admin/manual/import/merge services; user Admin;
staff and platform-school account reset services; school purge; settings/installed
apps and API routing. See the final Stage F inventory for the exact delivered files.

Models: `ParentRegistrationConfig`, `GuardianStudentRelation`,
`GuardianRegistrationRequest`, `GuardianActivation`, `GuardianContactReview`,
`GlobalMobileChangeRequest`, `RecipientContactBlock`. Family models share the
foundation migration and are described in Stages D/E.

Migrations: `students/0007_guardian_contact_revision`, `parents/0001_initial`,
`0002_contact_security_and_rls`, `0003_exact_family_identity_guards`,
`0004_durable_contact_resolution`. Resolution fields preserve original evidence
and separately retain the resolving employee's reason and verification note.

## APIs, pages and permissions

School API: contact review list/resolution, verified student contact update,
student/recipient-specific SMS block and resolution, documented global-mobile
request/list. Manager and vice-principal authorization uses the existing active
membership and subscription rules. Teachers cannot use these operations.
The Arabic school management page exposes these reviewed operations without
granting parents access to staff routes.

## Executed verification and regressions

Before changes: backend **1043 passed, 29 skipped**; frontend **373 passed**.
Intermediate integrated feature/regression run: **162 passed in 37.15s**.
It included contact direct/bulk/SQL protection, rollback, account reset/purge,
student merging, family requests, SMS and administrative leave flows.
Final post-hardening counts and real `NOSUPERUSER NOBYPASSRLS` HTTP/SQL results
are recorded in [Stage F](PARENT_PORTAL_STAGE_F_REPORT.md), together with commands.
No production checks or real SMS deliveries are inferred from local results.

## Existing Absence SMS Regression Verification

Existing candidate/eligibility rules, incomplete-FULL behavior, provider settings,
templates, deduplication and retry semantics remain authoritative. Registration is
not an SMS eligibility prerequisite. One intermediate test exposed canonicalizing
stored student contacts as a regression; that change was removed. Normalization is
now comparison-only. An explicit documented recipient block applies only to the
affected student/number, including a worker check immediately before delivery.
Actual final SMS suite results are in Stage F.

## Existing Student Leave & Gate Workflow Verification

No parent leave, electronic release, early-exit or gate authority was added.
The existing administrative leave/gate suites are part of the executed integration
and final regression runs. Parent negative permission checks are included.

## Required reporting coverage

| Required topic | Evidence in this report |
| --- | --- |
| 1. Actual implementation | Implemented scope |
| 2. New files | Files, models and migrations; final Stage F inventory |
| 3. Modified files | Modified integrations; final Stage F inventory |
| 4. Models | Seven foundation models; family models in D/E |
| 5. Migrations | students0007 and parents0001–0004 |
| 6. APIs | APIs, pages and permissions |
| 7. Frontend pages | Arabic school management and shared parent space in Stage F |
| 8. Permissions | School roles, independent guardian ownership and RLS |
| 9. Executed tests | Executed verification and regressions |
| 10. Test results | Baseline and intermediate counts; final Stage F record |
| 11. RLS tests | Actual restricted PostgreSQL/HTTP roles in final Stage F record |
| 12. Regression results | Mandatory SMS and leave/gate sections |
| 13. Issues | Contact normalization and protection findings |
| 14. Technical debt | Direct-SQL keyed evidence and global ownership process |
| 15. Remaining work | Authorized production operations in Operations/Stage F |

## Issues, debt and remaining work

Direct SQL has no application HMAC secret; its review record retains revision,
source and available actor context without inventing mobile hashes. Documented
application write contexts provide keyed hashes. Account mobile changes require
an independently approved ownership procedure and are intentionally pending.
Production migration/deployment, school enablement and provider smoke delivery
require separate authorization. These are operational steps, not local test claims.
