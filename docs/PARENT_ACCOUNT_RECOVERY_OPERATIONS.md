# Parent account recovery — operating gate and review procedure

Date: 2026-10-08. Read the [architecture](PARENT_ACCOUNT_RECOVERY_ARCHITECTURE.md)
and [release report](PARENT_PORTAL_RELEASE_READINESS_REPORT.md) before enabling any
public parent onboarding.

## Phase 1 update: personal verified-email password recovery

The owner has approved the distinct email/password policy documented in
[email recovery architecture](PARENT_EMAIL_RECOVERY_ARCHITECTURE.md) and
[Resend setup](RESEND_PARENT_RECOVERY_SETUP.md). School staff still cannot reset a
guardian password, verify or replace a recovery address, or change the global login
number. Central case execution below remains disabled.

1. New applicants must provide a valid recovery email. School approval and the
   existing SMS activation remain required. A new account must then explicitly
   verify its email before reading child data. Provider acceptance alone is not
   ownership verification.
2. Existing owners log in with their existing mobile/password. In the parent space,
   they personally enter their current password and recovery address, then verify
   the emailed link. Existing staff email is never automatically trusted. Staff
   workspace access remains available while parent email verification is pending.
3. An eligible owner who forgets the password enters the **login mobile** on the
   forgot-password page. The response is generic. A verified-email bearer lets the
   owner personally choose a new password, expires in 15 minutes by default, is
   single use, and invalidates existing password-derived sessions. There is no
   automatic login, new account, number change or relationship reactivation.
4. Platform/non-teacher privileged accounts are excluded from email-only recovery.
   An owner without a verified address and without the password still lacks an
   approved recovery route. Record the unresolved case under the review-only
   process below; do not create a duplicate account or let an employee select a
   password. A verified email cannot recover or replace the global mobile number.
5. Before public rollout, configure a verified Resend sender and least-privilege
   sending key, explicitly authorize a designated-address smoke test, and define
   the existing-parent enrollment rollout. Synthetic staging uses `.invalid`
   addresses and a private fake mailbox; it never calls Resend or sends SMS.

## Central review foundation: current status

For central identity/mobile recovery, no approved policy currently exists. The
separate verified-email password-only policy above is the subsequent Phase 1 approval.
School intake and central review preparation are implemented. **Recovery execution
is disabled.** Phase 1 public rollout has the separate email gates above. There is no approved original-account
ownership proof, implemented independent number verification or personal recovery
credential-delivery channel in the repository. An administrator cannot resolve
these gaps by switching an environment flag, choosing a temporary password or
recording two recommendations. No recovery SMS or OTP is available.

## Receiving a request

1. If the owner knows the old login number and password, use ordinary password
   login. Losing the SIM does not by itself invalidate those credentials. Use the
   current-password personal change route if a password change is needed.
2. If the password is also lost, or a global number change is requested, a school
   manager/vice principal may record an intake against an existing relationship.
   Keep the login number and school contact number separate. Updating Noor or the
   school contact may suspend that school's relationship; it does not replace the
   login number, migrate ownership or reactivate the relationship.
3. Record the operation, reason and a concise school verification note. Do not
   copy identity-photo content, raw identity numbers or a password into any note.
   The school must not receive an intake for the employee's own global account.
4. The same transaction creates an immutable source and a 30-day review case.
   School responses contain its case, status/version and a masked proposed number.
   A password-only request must not include a new number.
5. Give the owner an honest response: the request has been recorded for central
   review; global recovery is unavailable until verification prerequisites exist.
   Do not suggest creating a duplicate global account as the recovery workaround.

School APIs use the existing authenticated session, CSRF and selected-school
context. They are `POST /api/v1/staff/parents/students/{student_id}/recovery/`,
`GET /api/v1/staff/parents/recovery-cases/`, and
`POST /api/v1/staff/parents/recovery-cases/{case_id}/cancel/`.
Intake accepts `relation_id`, operation, required existing verified-contact fields
and optional `new_mobile` for mobile operations. Cancel accepts `expected_version`.
The legacy global-mobile-change intake opens a mobile-change case as well.

## Assigning central review authority

Central reviewers must have individually controlled active platform identities,
completed initial password setup, and a separately provisioned expiring grant for
exactly `FIRST` or `SECOND`. Owner/team-management capability is insufficient.
There is no application grant-provisioning API. Do not use a school account,
shared operator account or the target/requester to perform review.

Before any non-synthetic grant is provisioned, approve an IAM runbook specifying
who grants/revokes access, two distinct people, authorization records, expiry,
independence checks and access monitoring. The application role cannot provision
its own grants. The fixture uses synthetic owner-side provisioning only; copying
that test provisioning into production is not an approved operational procedure.

## Central review preparation

Central APIs are under `/api/v1/identity-review/parent-recovery/`. A live explicit
grant is required even to list cases. References and decisions are not school APIs.

1. Read the case and verify operation, expiry and version. Reading central detail
   or evidence references creates an access audit event. Responses are no-store.
2. Establish the missing original-owner binding **outside** this unapproved flow
   through a subsequently authorized process. Knowing a child's name/identifier,
   a Noor number, a school's assertion or possession of a new SIM is insufficient.
3. A reviewer may record an opaque UUID referring to an independent source.
   `ORIGINAL_ACCOUNT_BINDING` and, for mobile operations, `NEW_NUMBER_OWNERSHIP`
   are reference kinds. The API labels them unverified; this release cannot attest
   their content, authenticity or number ownership.
4. Reference changes increment the case version and invalidate earlier review
   authority for the new version. Supply the current `expected_version`; reload
   after a conflict. Expired or revoked references cannot support continuation.
5. A `FIRST` reviewer may reject, request further evidence or recommend continuing
   review. A different `SECOND` reviewer, with a separate stage grant and no
   membership at the requesting school, must assess the same version and evidence
   fingerprint. The second continuation reaches `POLICY_BLOCKED`.
6. Do not call `execute/` expecting a credential change. A well-formed, authorized
   request for an existing case returns 423 while the policy remains unapproved;
   permission, validation, missing-case and rate-limit errors can occur earlier.
   Neither reviewer can approve execution in this code.

Cases have no final-approval or execution state. A terminal rejection/cancellation
cannot be reopened by raw update. Timestamp expiry denies review without requiring
a background scheduler to have relabeled the row. Material source/account changes
require a new intake; replacing evidence starts a new version's reviews.

## Multiple schools, employee accounts and conflicts

Recovery intake always targets the existing `User.id`. Other-school relationships,
requests, employment and account history remain on that same user. School employees
cannot transfer children or reset the global password. Team administration also
denies reset if any guardian relationship exists, including suspended/revoked ones.
Admin credential writes and first-child activation serialize on the same global
account row. Activation requires a current authenticated password/session hash;
an earlier authenticated request cannot bypass a password reset that committed
before binding. These safeguards do not authorize administrative recovery.

A proposed number already used by a different global account stops continuation
with a conflict. Do not automatically merge, delete the conflicting account, move
relationships or create a second parent account. Independent central adjudication
requires an approved process. Recovering a credential in a future approved version
must not reactivate a suspended school relationship; the school must review that
relationship separately.

## Requirements before safe execution can be added

- Approve a privacy and identity policy with a trusted binding to the **original**
  account owner, and a means to validate it independently of student data.
- Implement approved new-number verification without adding recovery SMS or
  pretending the existing activation mechanism verifies global recovery.
- Approve distinct-human central IAM assignments and an independent second review.
- Define a secure personal password-enrollment/delivery channel; employees cannot
  choose, receive or log the owner's new password.
- Implement and test atomic execution, conflict checks, session/security-epoch
  invalidation and affected activation/token revocation, with preserved user ID.
- Approve private evidence storage/access logging/retention if documents become
  necessary. Current reference metadata is not a document repository.
- Test successful recovery, concurrent execution, exactly-once behavior, transaction
  rollback, session revocation and actual approved integrations before opening it.

Until these central prerequisites exist, keep central execution unavailable.
Phase 1 public registration stays closed until its Resend delivery and existing-parent
rollout gates are satisfied. Restricted staging uses only synthetic identities and default-disabled
school registration. See the [staging runbook](PARENT_PORTAL_STAGING_READINESS.md).

## Evidence handling, monitoring and rollback

Never paste evidence UUIDs, passwords, complete mobiles or identity details into
audit/log output. Watch denial/conflict rates and grant expiry/revocation. Review
audit case IDs and stage events through authorized tooling. Current metadata is
deleted only through the existing exact authorized student/school purge; approving
a separate retention schedule is still operational work.

Prefer a forward fix. A rollback must retain all global guardian reset guards,
including this release's team-reset guard. Do not return to the unsafe earlier
backend, drop existing relationships, or reverse security migrations on a live
database as a routine application rollback. Local isolated migration reversal
proves mechanics only; it is not permission for production data deletion.
