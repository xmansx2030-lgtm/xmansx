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

Local validation: nine focused provider regression cases passed on Python 3.13
and Django 5.2.18 with an isolated Redis instance; Ruff and `git diff --check`
passed. Only one real diagnostic SMS was attempted. Existing invitation records
were not rewritten and no activation invitation was resent.

Read-only provider checks returned valid account and active sender (`999`), with
14,047 credits before the diagnostic test. Original invitation delivery status
alone cannot establish whether that earlier message reached the handset.
