# Parent Portal — implementation reference

Arabic-first family workspace in the existing Django/React modular monolith. One
`accounts.User` follows explicitly approved children in independently approving
schools. A parent is not a school employee and consumes no `MAX_STAFF` capacity.

## Scope and invariants

- School-approved registration, single-use activation, multiple children/schools,
  submitted period attendance, morning arrival, history, excuse/correction requests,
  issued warnings, explicitly published documents/counseling text, and notifications.
- No parent leave request, early-release approval, guard access, or electronic
  authorization to collect a student. Existing `student_leaves` and
  `StudentGateRelease` retain their staff permissions and behavior.
- Imported `Student.guardian_mobile` is a school contact, never an access grant.
  It never overwrites `User.mobile`. School approval grants one specific relation.
- Only `ACTIVE` relations permit student data or writes. Suspension/revocation
  affects that relation, not the global account, employment, or other children.
- No production deployment or real SMS is part of development verification.

## Phase 0 source audit

Baseline: clean `main`, `286c7163b57686575f4cb3785532c239fa338624`, remote
`xmansx2030-lgtm/xmansx`; work branch `feature/parent-portal-20261008`.
Existing migrations have no ungenerated changes. Docker was initially stopped;
local PostgreSQL 18 and Redis were started before baseline testing.
Test evidence and actual outcomes are recorded in the stage reports.

| Existing source of truth | Reuse and boundary |
|---|---|
| `accounts.User`, session auth, CSRF, Argon2, rate limits | Same global account; never reset an existing user's password during activation |
| Memberships and school roles/capabilities | Staff management only; no fabricated parent memberships |
| Student and dated `StudentEnrollment` | Restricted family identity/grade/section projections and dated roster |
| AttendanceSession/Mark/DayContext/DailyAttendanceSummary | Read submitted facts, immutable day schedule, completeness separately |
| SchoolArrival | Morning arrival and `counted_late_minutes`; missing arrival is not absence |
| Existing excuse services and Coverage | Staff approval creates the administrative excuse; raw absence remains |
| `correct_student_attendance` / AttendanceChange | Authorized staff correction with actor/reason/history |
| StudentWarning and GeneratedDocument | Issued/void status; private download service; explicit family publication |
| CounselorCase/referrals | Internal notes remain internal; only new explicitly authored family content is published |
| School SMS providers/integration | Reuse Dreams/Msegat transport for activation only; separate delivery lifecycle |
| Subscriptions access/usage and private storage | Respect blocked/read-only schools and storage limits |
| Audit, purge registries, storage integrity, backup | Safe identifiers in audit; purge registrations and files; shared accounts survive |

Code and tests override stale documentation. In particular, current daily summaries
can be `FULL` when every **submitted** period is absent and remaining periods are
unsubmitted. `completeness_status` independently indicates completion. Existing
`candidate_absences()` requires `FULL`; `eligible_absences()` additionally requires
`unexcused_absent_periods > 0` and `submitted_periods > 0`. Parent work does not alter
these conditions, templates, timing, deduplication, or retry policy. The family UI
must not describe an incomplete day as a confirmed complete-day absence.

## Module and data boundaries

New `parents` app owns relation/account approval, registration, family requests and
projections. Business services call existing attendance/excuse/document services;
API views are thin, serializers whitelist inputs and outputs.

- `ParentRegistrationConfig`: public random school registration identifier, enabled
  flag, school identity only. Knowing the link does not disclose student matches.
- `GuardianRegistrationRequest`: encrypted mobile/student identifier, HMAC lookup
  keys/masked mobile, request state, one explicitly selected student after review,
  approving staff, verification note, decision reason, and contact revision.
- `GuardianActivation`: token hash only, expiry, school/request/student/revision,
  usage/revocation and separate provider outcome. Tokens never appear in audit.
- `GuardianStudentRelation`: global User + school + student, relationship, state,
  approving actor/time/revision, contact-bound flag/contact fingerprint, suspension
  and revocation history. Independently verified other guardians are not suspended
  just because the imported school contact changes.
- `GuardianContactReview`: old/new revision and hashed contact, source, actor,
  reason and resolution. PostgreSQL writes this atomically with meaningful changes.
- `GlobalMobileChangeRequest`: documented staff request only; remains pending until
  an independently approved secure global-account verification procedure exists.
- `ParentExcuseRequest` and private attachments: pending family submission distinct
  from an administrative excuse, linked after approval.
- `AttendanceCorrectionRequest`: objection to a submitted absence; no direct
  parent mutation of marks; staff acceptance delegates to current correction.
- `FamilyPublication`: explicit safe family text and/or approved single-student
  document, actor/time/revocation. No automatic session-note publication.
- `WarningAcknowledgement`: explicit acknowledgement, not consent or document open.
- `ParentNotification`: deduplicated family notification, read state and action
  completion tracked separately.

School/student/relation/session/document/case FKs receive PostgreSQL same-school
guards. Unique constraints handle account identity, one relation per user/student,
activation hash, open duplicate requests, acknowledgement and notification dedupe.
Indexes cover user relation status and school request queues/date ranges.

## Journeys and state machines

Registration: school link → generic receipt → staff verification and explicit child
selection → approve/reject/request information → single-use activation → new User
or authentication of the existing owner → `ACTIVE` child relation. Submission does
not create a User or reveal student/account matches. Sibling candidates are staff
review aids; each child requires independent explicit approval.

Registration states: `PENDING`, `NEEDS_INFO`, `APPROVED`, `REJECTED`, `ACTIVATED`,
`CANCELLED`. Relation states: `PENDING`, `ACTIVE`, `SUSPENDED_CONTACT_REVIEW`,
`REJECTED`, `REVOKED`. Request states: `PENDING`, `NEEDS_INFO`, `APPROVED`,
`REJECTED`, `CANCELLED`. Account activity is independent of all three lifecycles.

Activation tokens use cryptographic randomness, SHA-256 fingerprint, expiry,
one successful POST, revocation and contact revision. Inspection does not consume.
Lock order is school KEY SHARE → student → registration → relation/activation,
matching the existing Noor import's school-first order. Independent parent writes
can share the school lock; imports retain their existing exclusive school lock.
Existing users must authenticate as the approved mobile owner;
a delivered card or token must never reset/recover that account. Manual delivery
requires documented school verification and explicit staff action. URLs carry the
token in the browser fragment, avoiding proxy URL/access-log disclosure; API bodies
are never logged. Only the issuance response/transport sees the clear token.

School-contact change: normalize old/new values; formatting-only is not a change.
Noor blank/invalid values preserve the prior contact. Meaningful name/mobile change
increments the revision exactly once in the database, suspends affected bindings,
revokes unconsumed activations and records a review/audit in the same transaction.
Manual clearing is meaningful. Restoring an old number does not reactivate access.
Service context supplies actor/source/reason; direct/bulk SQL still invokes the
database safeguard. Merge preview rejects parent-link conflicts rather than
automatically moving grants to another identity.

## Authorization, subscriptions and RLS

Family endpoints authenticate, enforce initial-password policy, locate an owned
relation without joining student tables, enter its verified school RLS context,
recheck `ACTIVE` state/student/school, apply subscription access mode, and project
only permitted data. Cross-school discovery uses a small owner-only relation index.
No parent endpoint uses an RLS bypass. Public registration reads a nonsensitive
link directory and stores encrypted submissions within that school's context.
Bearer activation lookup uses a bounded token-hash context policy.

Manager/vice-principal manage registration/contact review/requests in their active
school. Teachers cannot change contacts/approve requests. Counselor publication
requires the counselor's assigned case scope. School managers never see the user's
other-school children. Suspended/archived schools and blocked subscriptions deny
family data; expired/cancelled subscriptions keep allowed reads and forbid writes.
No separate entitlement or plan-name branching is introduced.

## API contracts

Under `/api/v1/parent/`: registration link/read/submit, safe receipt status,
activation inspection/completion, children index, relation-scoped profile/today/
history, excuses/attachments, corrections, issued warnings/acknowledgements,
publications/private documents, requests and notifications/read/action.
Under `/api/v1/staff/parents/`: settings/QR link, registration queue/detail/decision,
relation queue/decision, contact review/global-mobile requests, family request
queues/decisions, publication/revocation and statistics. OpenAPI annotations describe
the whitelisted fields; all errors use the existing `{code,message,details}` shape.

Unknown/foreign relations and files produce the same 404 without confirming
existence. Lost access stops polling and removes cached child payloads. Public
registration returns the same acknowledgement for matched/unmatched/duplicate
identities. Rate limits protect IP and hashed mobile/account identities.

## Attendance projections

No new attendance state or period lateness is stored. Future period: `NOT_STARTED`;
no session: `NOT_RECORDED`; draft: `IN_PROGRESS`; submitted absent mark: `ABSENT`;
submitted without absent mark: `PRESENT`. Dated enrollment in the authoritative
academic year determines scope. Saved summary/context wins; today's ACTIVE year
precedes a prepared UPCOMING year. Historical recorded own-roster facts precede
date-covered-year fallback when their year is unique. Session year and section
must both match, preserving past transfers without exposing unrelated rosters.
Names/times come from actual bell/day/session snapshots, never invented subjects.
Morning arrival is separate and only exposes existing counted lateness.
History shows submitted/expected counts, raw/excused/unexcused absences and
completeness explicitly; incomplete `FULL` is displayed as an incomplete day.

## SMS and notifications

Only existing absence SMS and registration/activation SMS are allowed. No SMS for
lateness, request decisions, warnings, counseling, contact change or recovery.
Activation uses the school's existing encrypted provider configuration but separate
delivery records. Ambiguous acceptance becomes `UNKNOWN` with no blind retry;
explicit reissue revokes prior tokens. Tests mock providers, never send real SMS.
Creating/read-marking a portal notification never sends an absence SMS.
An explicit proven unreliable contact blocks only that student's affected number,
not other recipients and not all students lacking a portal account.

## Files, audit and browser data

Validate real PDF/JPEG/PNG content, size and school quota; private storage outside
public media paths, random names, checksum, no permanent `.url`. Every download
rechecks active relation, exact student, publication and document/warning state.
Audit stores identifiers/status/counts only, never tokens/passwords/complete IDs,
medical text or provider secrets. Student/school purge includes new rows/files,
while global users needed by other schools/relations remain intact. Backup restore
integrity includes new attachments using existing private-store infrastructure.

Frontend lives in existing React application with a distinct Arabic RTL parent
shell outside staff membership guards. Employee parents explicitly switch spaces.
Query keys include account/relation/school; polling defaults to 30s foreground only.
No sensitive persistence/offline caching. Logout/account/space switching cancels
queries and clears sensitive memory/browser caches. Forms support keyboard, labels,
loading/empty/error/success states and mobile layouts.

## Verification, performance, deployment and rollback

Stage A–F reports track actual implemented files/models/migrations/APIs/UI,
authorization, tests, failures, debt and remaining work. Required PostgreSQL tests
use a real `NOSUPERUSER NOBYPASSRLS` role; cover school isolation, file isolation,
suspension, raw/bulk contact changes, replay, existing accounts and concurrent
activation. Existing backend/frontend/SMS/leaves/gate regression suites are run.
RTL/Vitest/Playwright cover journeys and shared-device caches. Performance measures
must use actual recorded workload/query/time; no unmeasured scalability claims.

Deploy only after explicit authorization: backup database/private files/keys,
apply additive migrations, validate application role/RLS/triggers, enable school
registration deliberately, run smoke journeys, monitor errors and provider outcomes.
Rollback first disables registration and family routes. A backend rollback must keep
the guardian credential-reset checks and the installed parents app; the pre-portal
baseline backend is unsafe for existing global guardian accounts even when its
Student INSERTs are schema-compatible. Prefer a forward fix or a compatible frontend
rollback. Do not drop parent tables or contact guards
while active grants exist. Recover from database/private-file backup together when
needed; never revive suspended grants through a down migration or Noor reimport.
