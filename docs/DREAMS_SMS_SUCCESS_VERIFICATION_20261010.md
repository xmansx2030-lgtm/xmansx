# Dreams SMS response verification — 2026-10-10

The production provider returned the bare response `Success` for one explicitly
authorized diagnostic SMS. The recipient confirmed receipt. The existing parser
accepted `Result: Success` but classified the bare response as
`DREAMS_RESPONSE_UNKNOWN`, leaving family invitations visibly uncertain.

The observed response was seven bytes. Its SHA-256 was
`c88a0b907419a70c27ab7c1f8e5fb54441a4d9c3567e4c928fa7b2091194aecf`, which exactly
matches `Success`. No credentials, full recipient number, or activation link are
included in this report.

The parser now accepts either exact success form, case-insensitively. It continues
to reject extra text such as `Success pending` and `Not Success`. Numeric error
handling, network uncertainty, and existing Msegat behavior are unchanged.

All application SMS sends use this shared parser:

- Absence notices: `school_sms.tasks.send_absence_notice` records accepted
  responses as `ACCEPTED`, including the acceptance time. The absence preview and
  student SMS history return this persisted outcome.
- Parent registration activation: `parents.services.deliver_activation` records
  accepted responses as `SENT`.
- Family invitations: `parents.family_invitation_services.deliver_invitation`
  sends through `parents.family_invitation_sms.send_family_sms` and records
  accepted responses as `SENT` for the invitation and its child activations.

Workflow regression coverage invokes each real API and delivery service with
only the HTTP transport mocked. Each path exercises bare success, documented
success, numeric reference, explicit rejection, and an uncertain response. It
also checks that repeating the delivery task does not send another message.
Absence interface coverage checks that accepted and uncertain notices cannot
be selected for a new send, including after their checkbox is selected.

The existing labels describe provider acceptance; they do not assert handset
receipt. Email delivery uses a separate transport and does not parse Dreams
responses.

Local validation: 43 backend cases passed on Python 3.13 and Django 5.2.18 with
isolated PostgreSQL and Redis, including 15 real-workflow response cases, the
provider regression cases, existing absence SMS coverage, and parent SMS
regressions. Fourteen frontend cases passed for the absence page and student
profile, using Vitest's thread pool on Windows. Ruff, scoped ESLint, and
`git diff --check` passed. Only one real diagnostic SMS was attempted. Existing
invitation records were not rewritten and no activation invitation was resent.

Read-only provider checks returned valid account and active sender (`999`), with
14,047 credits before the diagnostic test. Original invitation delivery status
alone cannot establish whether that earlier message reached the handset.
