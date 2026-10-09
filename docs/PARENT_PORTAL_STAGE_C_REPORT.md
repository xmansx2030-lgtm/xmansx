# Parent Portal Stage C — Live Attendance

## Implemented scope, models and files

`parents/selectors.py` projects existing attendance/day/session snapshots,
dated student enrollments, active excuse coverage, daily summaries and morning
arrival. It creates no attendance model and performs no read-time attendance writes.
Frontend child cards, date detail, bounded history and summaries live in
`ChildPage.tsx`, `ParentPages.tsx`, `shared.tsx` and the parent API module.
No additional migration is needed for the projections.

## APIs, pages and permissions

`GET parent/children/` is paginated; `children/{relation}/` supports a selected
date; `children/{relation}/history/` validates a maximum 366-day range.
Every detail uses a fresh active owned relationship, exact school/student,
contact revision, school availability and subscription policy. Inactive/unavailable
cards reveal no student details. Scoped query keys, foreground-only 30-second
polling and query cancellation/cache clearing protect shared devices and spaces.

Future period: not started. Missing session: not recorded. Draft: awaiting
submission. Only SUBMITTED sessions confirm PRESENT/ABSENT; marks are prefetched
only for the linked student. Real snapshot period names/times are used without
invented subjects or period lateness. Historical expected counts use saved context
or daily summary; unknown expectation never becomes a confirmed complete day.

Morning absence is not inferred from a missing arrival. Lateness displays only
existing `counted_late_minutes`. History batches contexts/sessions/own marks/
coverage, retains unfinished days and submitted facts without a cached summary,
and uses date-effective enrollments in the authoritative academic year. The header
uses the current ACTIVE year; detail/history prefer saved summary year, then saved
day-context year, then ACTIVE year for today. Historical days without either saved
record use a unique recorded own-roster year before date-covered-year fallback.
Prepared UPCOMING enrollments cannot replace today's class or hide an old roster.
Only sessions matching the selected year and section contribute attendance.
FULL+INCOMPLETE stays visibly incomplete and is
excluded from confirmed full-day totals. Draft/pending excuses do not excuse absence.

## Executed verification and RLS

Real E2E observed draft labels, submitted attendance through the existing staff
API, subsequent 30-second polling, complete absence and counted morning lateness.
Actual desktop1366px/tablet768px/mobile390px screenshots were inspected; no horizontal page
overflow or browser page error was observed. API tests cover submitted/draft/future,
raw incomplete FULL, missing morning arrival, revoked/foreign relationships and
bounded history. Missing-summary/historical-expectation regressions were added after
the independent audit. Six additional year-selection tests cover prepared upcoming
years, frozen contexts, no-context today, summary precedence and historical transfers.
The final focused verification ran **115 tests successfully in32.89s**. The final
real browser lifecycle ran **1 test successfully in54.2s** (journey44.7s).
Final results, restricted PostgreSQL HTTP role tests and
measured polling workload are in [Stage F](PARENT_PORTAL_STAGE_F_REPORT.md).

## Existing Absence SMS Regression Verification

These family display labels do not modify the existing SMS definition of FULL,
candidate/eligible counts or incomplete-day sending behavior. No parent registration
prerequisite was added. Actual final SMS regression is recorded in Stage F.

## Existing Student Leave & Gate Workflow Verification

The parent child page contains no leave/release/early-exit request or gate actions.
No existing administrative workflow was replaced. Existing backend suites and
parent negative E2E checks verify the boundary; Stage F contains final counts.

## Required reporting coverage

| Required topic | Evidence in this report |
| --- | --- |
| 1. Actual implementation | Live attendance and bounded history projections |
| 2. New files | selectors.py, child pages/API and tests; final Stage F inventory |
| 3. Modified files | Shared auth/routing and typed parent API; final Stage F inventory |
| 4. Models | Existing attendance, arrivals, dated enrollment and excuse coverage |
| 5. Migrations | No new stage-specific migration; shared foundation |
| 6. APIs | Children index/date detail and history |
| 7. Frontend pages | ChildPage and ParentPages child/attendance views |
| 8. Permissions | Active exact relation, school availability, subscription and RLS |
| 9. Executed tests | Executed verification and RLS; final Stage F commands |
| 10. Test results | Real browser and final Stage F backend/frontend totals |
| 11. RLS tests | Foreign-child/private-file HTTP under a restricted PostgreSQL role |
| 12. Regression results | Mandatory SMS and leave/gate sections |
| 13. Issues | Missing summaries, unknown expected counts and academic-year preparation |
| 14. Technical debt | Unrecorded historical facts are not invented |
| 15. Remaining work | Separately authorized rollout and production monitoring |

## Issues, debt and remaining work

A historical day with no saved context, session, summary or arrival has no
authoritative recorded facts and is not invented from today's timetable. Opening
the selected date still reports missing information. Multiple recorded years for one
historical student/day without a saved summary or context remain ambiguous; unique
recorded-year fallback does not merge unlike rosters, and absent expected-count
evidence cannot certify a complete day. Performance measurements are
local PostgreSQL samples, not production capacity guarantees. Production rollout
and monitoring remain separately authorized operational work.
