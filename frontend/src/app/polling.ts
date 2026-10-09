/** Shared high-scale polling policy.
 *
 * One randomized phase per browser tab avoids synchronized request waves when
 * schools open dashboards at the start of a period. Failed requests back off
 * independently, while focus/reconnect still triggers React Query refreshes.
 */

import { ApiError } from "@/api/client";

const TAB_JITTER_FACTOR = 0.85 + Math.random() * 0.3;
const MAX_FAILURE_BACKOFF_MS = 5 * 60_000;

function configuredMs(raw: string | undefined, fallback: number, minimum: number): number {
  const parsed = Number(raw);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.max(Math.round(parsed), minimum);
}

export const POLLING = {
  monitoring: configuredMs(import.meta.env.VITE_MONITORING_POLL_MS, 10_000, 5_000),
  teacherPeriod: configuredMs(import.meta.env.VITE_TEACHER_PERIOD_POLL_MS, 15_000, 5_000),
  teacherAttention: configuredMs(
    import.meta.env.VITE_TEACHER_ATTENTION_POLL_MS,
    30_000,
    10_000,
  ),
  dashboardLive: configuredMs(import.meta.env.VITE_DASHBOARD_LIVE_POLL_MS, 15_000, 5_000),
  dashboardAttention: configuredMs(
    import.meta.env.VITE_DASHBOARD_ATTENTION_POLL_MS,
    60_000,
    15_000,
  ),
  dashboardOverview: configuredMs(
    import.meta.env.VITE_DASHBOARD_OVERVIEW_POLL_MS,
    120_000,
    30_000,
  ),
  dashboardAnalytics: configuredMs(
    import.meta.env.VITE_DASHBOARD_ANALYTICS_POLL_MS,
    300_000,
    60_000,
  ),
  counselorDashboard: configuredMs(
    import.meta.env.VITE_COUNSELOR_DASHBOARD_POLL_MS,
    30_000,
    10_000,
  ),
  counselorCases: configuredMs(
    import.meta.env.VITE_COUNSELOR_CASES_POLL_MS,
    60_000,
    15_000,
  ),
  attendanceAnalytics: configuredMs(
    import.meta.env.VITE_ATTENDANCE_ANALYTICS_POLL_MS,
    30_000,
    10_000,
  ),
  gate: configuredMs(import.meta.env.VITE_GATE_POLL_MS, 15_000, 5_000),
  morning: configuredMs(import.meta.env.VITE_MORNING_POLL_MS, 30_000, 10_000),
  deviceStatus: configuredMs(import.meta.env.VITE_DEVICE_STATUS_POLL_MS, 30_000, 10_000),
  jobStatus: configuredMs(import.meta.env.VITE_JOB_STATUS_POLL_MS, 5_000, 3_000),
} as const;

interface PollingQueryState {
  state: {
    fetchFailureCount?: number;
    errorUpdateCount?: number;
    dataUpdatedAt?: number;
    status?: string;
  };
}

const failureStreaks = new WeakMap<PollingQueryState, {
  errors: number; updatedAt: number; failures: number;
}>();

export function adaptivePollingInterval(baseMs: number) {
  const staggeredBase = Math.max(1_000, Math.round(baseMs * TAB_JITTER_FACTOR));
  return (query: PollingQueryState): number => {
    const errors = query.state.errorUpdateCount ?? 0;
    const updatedAt = query.state.dataUpdatedAt ?? 0;
    let streak = failureStreaks.get(query);
    if (!streak) {
      streak = { errors, updatedAt, failures: query.state.status === "error" ? 1 : 0 };
      failureStreaks.set(query, streak);
    } else {
      if (updatedAt !== streak.updatedAt) streak.failures = 0;
      if (errors > streak.errors) streak.failures += errors - streak.errors;
      streak.errors = errors;
      streak.updatedAt = updatedAt;
    }
    const failures = Math.min(Math.max(streak.failures, query.state.fetchFailureCount ?? 0), 5);
    const delay = Math.min(staggeredBase * 2 ** failures, MAX_FAILURE_BACKOFF_MS);
    const error = (query.state as { error?: unknown }).error;
    return Math.max(delay, error instanceof ApiError ? error.retryAfterMs : 0);
  };
}

/** Job polling stops on terminal states and shares the same failure/visibility policy. */
export function activeJobPollingInterval(statuses: readonly string[]) {
  const interval = adaptivePollingInterval(POLLING.jobStatus);
  return (query: PollingQueryState & { state: { data?: { status: string } } }): number | false =>
    !query.state.data || statuses.includes(query.state.data.status) ? interval(query) : false;
}
