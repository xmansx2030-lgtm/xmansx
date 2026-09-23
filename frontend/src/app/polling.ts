/** Shared high-scale polling policy.
 *
 * One randomized phase per browser tab avoids synchronized request waves when
 * schools open dashboards at the start of a period. Failed requests back off
 * independently, while focus/reconnect still triggers React Query refreshes.
 */

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
} as const;

interface PollingQueryState {
  state: { fetchFailureCount?: number };
}

export function adaptivePollingInterval(baseMs: number) {
  const staggeredBase = Math.max(1_000, Math.round(baseMs * TAB_JITTER_FACTOR));
  return (query: PollingQueryState): number => {
    const failures = Math.min(query.state.fetchFailureCount ?? 0, 5);
    return Math.min(staggeredBase * 2 ** failures, MAX_FAILURE_BACKOFF_MS);
  };
}
