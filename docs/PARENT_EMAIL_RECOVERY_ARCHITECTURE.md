# Parent recovery email — Phase 1 architecture

Policy approved on 2026-10-08; implementation extends the local release
`010961953e63e91040428de3f5849d6ecd863f69`. This document describes email ownership
and password recovery, independent of the review-only central recovery foundation.
Actual execution results and final SHA belong in
[verification](PARENT_EMAIL_RECOVERY_VERIFICATION.md).

## Product boundary

New parent registration requires a valid email on both frontend and backend.
It has exactly two delivery purposes: `RECOVERY_EMAIL_VERIFICATION` and
`PASSWORD_RESET`. It is not a school notification channel. Attendance, morning
arrival, excuses, warnings, counseling, billing and marketing never use this
transport. Dreams/Msegat remain the absence and parent activation SMS providers.

Login stays mobile/password. `Student.guardian_mobile` remains a school contact.
Neither a verified email nor a password reset changes `User.mobile`, transfers a
child, alters employment or restores suspended/revoked relations. There is no
parent leave/early-release API or interface. School approval remains necessary.

## Existing sources and new data

The existing `accounts.User` is the sole global account. `User.email` is neither
overwritten nor treated as verified. Separate `AccountRecoveryEmail` stores one
current verified primary address, an independent pending candidate, verification
time and current/pending revisions. Addresses reuse existing Fernet encryption
and a purpose-separated HMAC using `NATIONAL_ID_HMAC_KEY`. Only the current
verified HMAC is unique; multiple unverified candidates never prove ownership.

Normalization trims surrounding whitespace, normalizes Unicode NFC and case-folds
the address. Dots and plus suffixes are preserved; no Gmail/provider alias rules
are guessed. Django email validation and a254-character limit apply. Case-folding
the local part is this product's intentional identifier policy; rare mail systems
with case-sensitive local parts must use a different recovery address.

Registration stores encrypted email, HMAC and a masked projection. Existing rows
receive blank additive fields; no old address is backfilled as verified. The
registration email is immutable after submission. Staff APIs expose its masked
projection, not the raw address or any recovery bearer.

`AccountRecoveryEmailDelivery` is a UUID outbox and a hash-only bearer credential.
It contains purpose, account/email/revision bindings, current password and mobile
fingerprints, expiry, attempt time, one-way consumption/revocation, bounded
provider reference and error code. Raw tokens are never persisted in the database.

## Registration, approval and enrollment

1. The public form requires name/mobile/email/student identifier. Valid unmatched,
   duplicate or existing-account submissions receive the same opaque202 receipt.
   Email/account/student existence is not disclosed by submission responses.
2. Manager/vice-principal reviews the same school-scoped request and approves one
   child. School approval does not verify email or authorize a global credential.
3. Existing SMS activation proves the existing authenticated account or creates a
   new global account with a validated password. The approval and relation remain
   recorded while email verification is pending.
4. A newly created account enrolls the registration email as a pending candidate.
   Only an explicit authenticated confirmation using the emailed bearer verifies
   it. Until then, all parent data APIs and parent service scopes reject access.
5. Existing accounts must sign in and personally enroll using their current
   password. An attacker-supplied registration email is never automatically made
   a recovery credential for an existing account. Existing verified email remains
   unchanged when another school/child is linked.

The parent shell checks credential readiness before mounting child pages. Pending
state, failed/unknown delivery, resend and enrollment are visible in Arabic. Staff
workspace access and existing authenticated current-password change are unaffected.
Temporary delivery failure preserves the same account, approval and relation.

## Email verification and change

Authenticated enrollment/change locks and freshly checks the global user and
current password. A new candidate remains separate from the verified primary.
Changes revoke affected outstanding bearers. A new address becomes primary only
after explicit proof, with unique-HMAC conflict handling that exposes no other
account. A previous employee email has no implied trust.

Verification tokens are256-bit random values generated in worker memory. Only a
SHA256 digest is stored. They bind the exact account, pending address/revision,
current password fingerprint and mobile fingerprint. Default TTL24h is configurable
within production bounds. GET navigation cannot consume a token. The API requires
an authenticated matching account, Session/CSRF and an explicit POST.

Changing a candidate, password or binding, revoking a bearer, consuming it or
passing expiry makes an old link unusable. First verification or a verified-email
change revokes affected deliveries. An existing primary stays verified during a
pending change; school authority cannot perform either operation.

## Forgotten password

The public form accepts the registered mobile, not an email login identifier.
It always gives the approved generic202 message for a syntactically valid mobile,
including missing users, missing verified emails and ineligible privileged users.
IP/mobile counters apply regardless of existence. A minimum response interval
with bounded jitter reduces the measured fast-path timing difference; it is not
a proof against every timing side channel under infrastructure delays.

Eligibility is checked at request, delivery and completion: active account, usable
password, completed initial-password change, an existing guardian relation or retained
parent recovery credential, and a currently
verified recovery email. A teacher/parent can recover. `is_staff`, `is_superuser`,
any platform-team membership or any school role other than teacher blocks this
path, even when a membership is suspended. Additional privileged proof is not
invented. A suspended guardian relation remains suspended but does not destroy the
owner's ability to recover their account.

A reset token binds current verified address/revision and credential fingerprints,
has default15-minute TTL and is one-time. The check endpoint grants no session.
Completion validates the project's password policy and confirmation, rechecks
current eligibility under locks, updates the same user's Django password hash,
consumes the bearer and revokes outstanding email bearers in one transaction.
No automatic login follows. Old sessions fail Django's current session-auth hash
comparison; the reset owner must log in afresh. The UI rechecks and preserves an
unrelated valid session, such as another teacher using the same browser. Session rows need
not be globally scanned to make their previous authentication invalid.

The existing initial-password endpoint also locks and freshly checks the global
user, session hash, password snapshot and initial-password flag. A request that
began with an old temporary password cannot overwrite a subsequently completed
owner recovery or revive its invalidated session. Password and Audit writes are
atomic; session rotation occurs only after successful completion.

SMS activation links remain conditional on current account authentication for an
existing user; changing the password invalidates their old authenticated proof.
Central `execute_recovery()` stays closed and is not reused by email recovery.

## Delivery, idempotency and privacy

Celery receives only the outbox UUID, never a token, address or secret link. The
worker claims one pending attempt, checks current bindings, creates the token in
memory and rechecks under locks immediately before sending. Resend uses its fixed
HTTPS endpoint and an attempt UUID idempotency header. No SMTP fallback or general
email API is added. Safe Arabic templates contain no student/school/account secrets.

States distinguish `PENDING`, `SENDING`, `SUBMITTED_TO_PROVIDER`, `FAILED`, `UNKNOWN`
and `CANCELLED`. Provider acceptance is not delivery or ownership verification.
Timeout/network/5xx/ambiguous409 failures are uncertain. No automatic blind retry
reconstructs a lost secret or sends twice. Duplicate jobs skip a claimed attempt;
a stale in-flight attempt becomes UNKNOWN when revisited. Owner resend, after
cooldown/rate limits, creates a fresh attempt and invalidates old links. Broker
failure is diagnosed with a bounded code. An indefinitely unprocessed pending job
requires worker/queue operational monitoring; no delivery is assumed.

Links use URL fragments. The React page transfers the token to component memory
and clears the fragment with replacement history; it never stores it in browser
storage or TanStack Query. No analytics or third-party scripts are added. API
responses use private/no-store and no-referrer. Sentry parent-context scrubbing
removes credential request data, locals and sensitive email/token fields. Audit
contains action/account identifiers without email, password, token or link.

## RLS, transactions and operational rollout

The additive parents0007 migration creates two global FORCE RLS tables. Their
policies use exact global owner, bearer or worker-attempt scope. School and general
platform bypass do not authorize these tables. Invoker/fixed-search-path guards
enforce binding immutability, legal verified transitions and one-way bearer state.
Existing school/attendance RLS remains intact. Parent service/API readiness gates
operate in addition to existing exact-child and school/subscription checks.

Parents0008 extends the existing database mobile guard to retained recovery-email
bindings. The exact account remains protected even after the last guardian
relationship is purged. It clears/restores the school context for its subject-only
existence check and never introduces a school/platform bypass. Existing Admin,
school and platform credential-write guards use the same retained-binding rule.
Reversing this guard with recovery data present is refused; use a forward fix or
a compatible application rollback that retains the new credential tables and guards.

Lock order starts with User, then owned membership/role rows for reset eligibility,
then email and delivery rows. School activation keeps its existing school/student
ordering before User; email worker/reset never acquires a school lock in reverse.
The bounded provider request holds the account locks to prevent a candidate or
credential change between final validation and send; this is a deliberate latency
tradeoff. Concurrency tests must prove current-role checks and single consumption.

Authorized school purge locks the school and then its member users in sorted ID
order before removing employment rows. Orphan cleanup checks only the existence
of recovery bindings/deliveries under each exact subject's global scope; it never
decrypts or returns credentials or grants a platform bypass. Recovery-bound users
are preserved, while ordinary never-parent orphan deletion keeps its policy.
Administrative credential guards must also protect retained recovery bindings
after the last school relationship has been physically purged. Retention alone
does not authorize that school to choose the global account's password or mobile.
A retained parent recovery credential preserves personal recovery after the last
school relationship is removed: the same verified-email proof and privilege
exclusions still apply. It creates no child permission, employment or new account.

No migration marks legacy users verified or makes staff-only accounts invalid.
Existing parents without verified recovery credentials must enroll in parent space;
staff space stays usable. A user lacking both password and previously verified
email still has no automated proof: central review remains blocked. No school reset
or account duplication substitutes for ownership.

Before public rollout: migrate with the owner role, grant the existing restricted
application role access to the new tables, deploy compatible app/worker/frontend,
configure a sending-only domain-restricted Resend key and approved verified sender,
then perform an explicitly authorized synthetic inbox smoke. Recovery delivery
defaults off; the parent readiness gate remains enforced. Do not deploy this gate
to public parent traffic before delivery and legacy enrollment rollout are ready.
Back up the database and encryption/HMAC keys. Forward-fix retains prior credential
guards; no rollback may reintroduce school/platform parent-password resets.

The synthetic adapter is limited to the isolated test/staging profiles, localhost,
`.invalid` recipients, no Resend key and a dedicated private0700/0600 mailbox.
Its secret-link files exist only as synthetic test evidence, not a production
outbox or database token store. Public registration remains closed after acceptance.
External sender configuration/receipt is separate from automated mock proof; see
[Resend setup](RESEND_PARENT_RECOVERY_SETUP.md).
