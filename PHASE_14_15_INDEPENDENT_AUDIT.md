# PHASE 14 + PHASE 15 — Independent Audit & Release Gate

**Verdict: READY FOR PHASE 16**

Every number below comes from a command executed during this audit on the release tree.
No result is carried over from an earlier agent's report.

---

## Git

| Item | Value |
|---|---|
| Audit started on | `integration/phase-12-13` @ `864b780` |
| Release branch | `release/pre-phase-16` |
| Phase 14 source commit | `bd784e4` (`feature/phase-14-counseling`) |
| Phase 15 source commit | `691dc5b` (`feature/phase-15-school-dashboard`) |
| Merge commit | `85a7ccb` |
| Final commit | `abdb866` |
| Rescue points (kept) | `rescue/pre-phase-14-15-final-audit`, `rescue/pre-phase-16-integration` |

No history was rewritten. No force push. Nothing was pushed.

---

## What Phase 14 already had

A complete counseling implementation existed but **was never committed** —
`git log --all --oneline -- backend/counseling` returned empty before this audit.

- Models: `CounselorCase`, `CounselorSession`, `CounselorFollowUpPlan`, `FollowUpGoal`,
  `FollowUpActivity`, `TeacherFollowUpRequest`, `TeacherFollowUpResponse`, `CounselorCaseEvent`
- Services for open / close / reopen / sessions / plans / goals / activities / teacher requests
- Role-scoped selectors, API layer, purge integration, Arabic RTL counselor UI

### What Phase 14 was missing
- Not under version control (loss risk only; the code itself was complete)

### Phase 14 bugs found
- None in the product. Its focused suite passed unchanged: **42 passed**.

---

## What Phase 15 already had

Also **uncommitted**, living in a separate worktree (`xmansx-phase-15`):

- `school_dashboard` read/query layer: `selectors/attendance.py`, `selectors/followup.py`,
  `selectors/attention.py`, `ranges.py`, `cache.py`, `api/views.py`
- React dashboard: `DashboardPage.tsx`, `TrendChart.tsx`, `api.ts`, plus its own Vitest file
- **No migrations** — confirming Dashboard is a pure read layer with no duplicate source of truth

### What Phase 15 was missing — and the integration bug this audit found

Phase 15 was developed in isolation from Phase 14 and called a seam that **did not exist**:

```
ImportError: cannot import name 'counseling_bridge' from 'school_dashboard.selectors'
```

Every dashboard endpoint crashed once both phases coexisted — **9 failing tests**.
This defect could only appear after integration, which is exactly why the merge was required.

### What was fixed

`backend/school_dashboard/selectors/counseling_bridge.py` implements the seam:

- Aggregates only: open / under-assessment / follow-up-active / resolved / closed,
  opened-in-range, closed-in-range, waiting teacher responses, overdue activities
- Reuses Phase 14 models directly — no recomputation of attendance, excuse or warning logic
- No counselor notes, no referral text, no performance score, no risk score
- Respects grade/section scope through the same student-scoping helper as the rest of the dashboard

Two tests asserting `available: false` were updated to the post-integration contract
(`available: true` with real counts). That is a contract change caused by integration,
not a weakened assertion — the "module not installed" branch is still covered by a Vitest case.

---

## Metric-definition verification

| Rule | Verified by |
|---|---|
| Referral ≠ Counselor Case | `test_case_and_teacher_request_move_dashboard_counters` asserts both independently |
| Warning Due ≠ Warning Issued | `warning_metrics` keeps `due` (point-in-time) separate from `issued` (in-range) |
| Morning late ≠ Period late | separate keys; E2E `morning late warning is independent from period late` |
| FULL / PARTIAL / UNDETERMINED / NONE | `test_school_dashboard.py` attendance KPI cases |
| Case status transitions | `ALLOWED_STATUS_FLOW` enforced in model **and** UI (`NEXT_STATUSES`) |
| Dashboard = read layer | Phase 15 ships zero migrations |

---

## Cross-phase integration test added

`test_case_and_teacher_request_move_dashboard_counters` proves the Phase 14 → Phase 15 chain:

```
open case            → open_cases +1
teacher request      → waiting_teacher_responses +1
teacher response     → waiting_teacher_responses -1
referral count stays independent of case count
```

---

## Playwright investigation (root causes)

### 1. CSRF trusted origin — configuration, not a product defect
Login returned 200 but `POST /api/v1/session/active-school/` returned **403**. The audit stack
serves the frontend on port 5373, which was not in `CSRF_TRUSTED_ORIGINS`. The `DEV_EXTRA_ORIGINS`
mechanism already existed but compose never forwarded it. Added one env line; verified inside the
container that the origin list now includes 5373.

### 2. `counseling.spec.ts:349` — test contradicted the real workflow
The test clicked `status-RESOLVED` while the case was `OPEN`. `ALLOWED_STATUS_FLOW` permits
`OPEN → UNDER_ASSESSMENT | FOLLOW_UP_ACTIVE` only, and plan activation deliberately does **not**
change case status. **The product was right; the test was wrong.** The spec now walks the legal
path `OPEN → FOLLOW_UP_ACTIVE → RESOLVED → CLOSED → REOPEN`, which is what E2E 14.7 requires.

### 3. `counseling.spec.ts:116` 409 — test-state contamination
The `serial` group was retried against a database still holding the referral from attempt 1.
Fixed by selecting a distinct fixture student per attempt via `testInfo.retry`. Duplicate-referral
protection was left untouched.

Independence evidence: 3 consecutive clean-state runs (6/6, 6/6, 6/6) plus a dirty-DB run with
`--retries=1` (6/6).

### 4. `lifecycle-purge` — a genuine product defect (fixed)
The purge confirmation dialog was a `fixed inset-0` centred overlay with **no height cap and no
scrolling**. When Phase 14 added 8 counseling steps to the purge summary, the dialog outgrew the
viewport and the confirm button became **unreachable** — a real defect a manager would hit.
Fixed by capping the panel at `calc(100vh - 2rem)` with internal scrolling and top-aligning the
overlay. Regression guard added: `await expect(confirmButton).toBeInViewport()`.

> Note: a stale Vite module in the container initially masked the fix. It was detected by fetching
> the served module directly and resolved by restarting the container — worth remembering for any
> future container-based UI debugging.

---

## Evidence Summary

```
Backend pytest:            600 passed, 29 skipped
Focused Phase 14:           42 passed
Focused Phase 15:           25 passed
Bridge:                      9 passed

Frontend Vitest:           175 passed (21 files)
Playwright (full):          58 passed, 0 failed, 0 flaky (9.7m)

ruff:                      All checks passed
typecheck:                 PASS
lint:                      PASS
build:                     PASS
Django check:              no issues
makemigrations --check:    No changes detected
Fresh migrate (zero → head): PASS
Docker (xmansx-pre16):     postgres/redis/backend/worker healthy, beat+frontend up
```

`check --deploy` reports 72 warnings when run against **local** settings (DEBUG=True).
`config/settings/production.py` sets `DEBUG=False`, `SECURE_SSL_REDIRECT`, `SECURE_HSTS_SECONDS`,
`SESSION_COOKIE_SECURE` and `CSRF_COOKIE_SECURE`. Documented non-blocker; drf-spectacular
warnings are legacy and explicitly out of scope.

### Performance (no N+1)

| Students | Duration | Queries |
|---|---|---|
| 500 | 45.9 ms | 20 |
| 1000 | 36.0 ms | 17 |
| 3000 | 25.1 ms | 17 |
| 5000 | **26.7 ms** | **17** |

Query count is constant from 1000 → 5000 students. Target (<1s at 5000) met with wide margin.
Reproduce with `backend/benchmark_dashboard.py`.

### Security / privacy

| Gate | Result | Evidence |
|---|---|---|
| Teacher privacy | PASS | teacher sees only own request; no case, sessions or counselor notes |
| Counselor case IDOR | PASS | other counselor gets 404; teacher gets 403 |
| Tenant isolation | PASS | foreign school manager gets 404 on case and empty listing |
| Dashboard cache isolation | PASS | cache key is `dash:<school_id>:<section>:<hash>` — school first |
| School-switch isolation | PASS | `test_school_switch_shows_no_previous_school_numbers` |
| Mass assignment | PASS | client-supplied `school`/`created_by`/`status` ignored |
| Executive dashboard privacy | PASS | asserts no `description`/`notes`/`national_id`/`guardian` |
| No risk/performance score | PASS | bridge exposes counts only |

### Purge coverage (ordered)

`TeacherFollowUpResponse → TeacherFollowUpRequest → FollowUpActivity → FollowUpGoal →
CounselorFollowUpPlan → CounselorSession → CounselorCaseEvent → CounselorCase`, ahead of referrals.
Staff memberships are not touched by student purge.

---

## Requirement Matrix

| Requirement | Original State | Action Taken | Test | Result |
|---|---|---|---|---|
| Counseling models | Implemented, uncommitted | Committed `bd784e4` | test_counseling.py | PASS |
| Referral → Case | Implemented | none | test_counseling.py | PASS |
| Opening idempotent / concurrency-safe | Implemented (unique constraint) | none | test_counseling.py | PASS |
| Snapshot immutable vs current | Implemented | none | test_counseling.py + E2E 14.6 | PASS |
| Sessions (types, void) | Implemented | none | test_counseling.py | PASS |
| Single active plan | Implemented (DB constraint) | none | test_counseling.py | PASS |
| Goals quantitative + qualitative | Implemented | none | test_counseling_api.py | PASS |
| Activities pending/completed/cancelled | Implemented | none | test_counseling.py | PASS |
| Teacher follow-up request/response | Implemented | none | test_counseling_api.py + E2E 14.4 | PASS |
| Teacher privacy / ID enumeration | Implemented (membership-scoped) | none | test_counseling_api.py + E2E 14.5 | PASS |
| Close requires reason / Reopen | Implemented | E2E now follows legal flow | E2E 14.7 | PASS |
| Case status flow | Implemented | none (test corrected) | model + UI | PASS |
| Counselor dashboard | Implemented | none | counseling.test.tsx | PASS |
| Student profile integration | Implemented | none | E2E integration | PASS |
| Dashboard today operations | Implemented | none | test_school_dashboard.py | PASS |
| FULL/PARTIAL/UNDETERMINED/NONE | Implemented | none | test_school_dashboard.py | PASS |
| Excused / unexcused / mixed | Implemented | none | test_school_dashboard.py | PASS |
| Morning vs period late separation | Implemented | none | E2E warnings | PASS |
| Trends & comparisons (zero baseline) | Implemented | none | test_school_dashboard_api.py | PASS |
| Grade/section historical enrollment | Implemented | none | test_school_dashboard.py | PASS |
| Warning due vs issued | Implemented | none | test_school_dashboard.py | PASS |
| Actions / documents analytics | Implemented | none | test_school_dashboard.py | PASS |
| Referral vs case analytics | Implemented | none | new integration test | PASS |
| Teacher follow-up metrics | **Missing (ImportError)** | **Implemented bridge** | new integration test | PASS |
| Needs Attention queue | Partial (counseling items unreachable) | **Implemented** | test_school_dashboard.py | PASS |
| Cache isolation / school switch | Implemented | none | test_school_dashboard_api.py | PASS |
| Filter IDOR / cross-school | Implemented | none | test_school_dashboard_api.py | PASS |
| Purge covers Phase 14 | Implemented | none | purge tests | PASS |
| Purge dialog reachable | **Defect** | **Fixed + regression guard** | E2E lifecycle-purge | PASS |
| E2E CSRF origin for parallel stack | Missing plumbing | **Added `DEV_EXTRA_ORIGINS`** | E2E auth | PASS |
| Fresh DB migrate | Untested | Executed | migrate from zero | PASS |
| Docker clean stack | Untested | Built `xmansx-pre16` | compose ps | HEALTHY |

---

## Known limitations / technical debt

- `check --deploy` warnings under local settings (production settings hardened) — documented non-blocker
- drf-spectacular `W002` legacy warnings — explicitly out of scope, non-blocking
- `counseling.spec.ts` fixture pool holds 2 students, supporting `retries: 1`; a higher retry count
  would need a larger pool
- Docker bind-mount on Windows can serve stale Vite modules; restart the frontend container after
  UI edits before trusting an E2E result

## Phase 16 readiness

All Phase 14 and Phase 15 acceptance gates pass on `release/pre-phase-16` with a clean working tree.
