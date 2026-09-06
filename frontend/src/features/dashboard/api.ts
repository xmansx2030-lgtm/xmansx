import { apiRequest } from "@/api/client";

/** الفترات الجاهزة — نفس أسماء الخادم حرفيًا؛ الواجهة لا تحسب تواريخ بنفسها. */
export type DashboardPreset =
  | "TODAY"
  | "LAST_7_DAYS"
  | "LAST_30_DAYS"
  | "THIS_WEEK"
  | "THIS_MONTH"
  | "CURRENT_SEMESTER"
  | "CUSTOM";

export interface DashboardFilters {
  preset: DashboardPreset;
  fromDate?: string;
  toDate?: string;
  gradeId?: number | "";
  sectionId?: number | "";
}

export interface RangeInfo {
  from_date: string;
  to_date: string;
  days: number;
  preset: DashboardPreset;
}

/** أساس صفري ⇒ `change_pct = null` و`is_new = true`: لا نسبة بلا مقام (بند 57). */
export interface Comparison {
  current: number;
  previous: number;
  delta: number;
  change_pct: number | null;
  is_new: boolean;
}

export interface AttendanceKpis {
  unit: "STUDENT_DAYS";
  student_days: number;
  distinct_students: number;
  full_absence_days: number;
  partial_absence_days: number;
  no_absence_days: number;
  undetermined_days: number;
  unexcused_full_absence_days: number;
  excused_full_absence_days: number;
  mixed_full_absence_days: number;
  absent_periods: number;
  unexcused_absent_periods: number;
  excused_absent_periods: number;
  period_late_occurrences: number;
  period_late_minutes: number;
  morning_late_occurrences: number;
  morning_late_minutes: number;
  morning_arrivals: number;
  completeness: {
    complete_student_days: number;
    incomplete_student_days: number;
    incomplete_pct: number;
    is_significant: boolean;
  };
}

export interface TodayOperations {
  school_time: string;
  date: string;
  period: { sequence: number; name: string; start_time: string; end_time: string } | null;
  alert: { minutes: number; alert_at: string } | null;
  summary: {
    total: number;
    submitted: number;
    in_progress: number;
    not_started: number;
    overdue_total: number;
  } | null;
  submission_completion_pct: number | null;
  has_active_period: boolean;
  operational_state?: "IDLE" | "IN_PROGRESS" | "ON_TRACK" | "ACTION_REQUIRED";
  headline?: string;
  updated_at?: string;
  live_attendance?: {
    status: "AVAILABLE" | "NO_ACTIVE_PERIOD";
    total_students: number;
    covered_students: number;
    pending_students: number;
    present_students: number;
    absent_students: number;
    leave_students: number;
    late_students: number;
    morning_late_students: number;
    daily_absent_students: number;
    daily_covered_students: number;
    daily_pending_sections: number;
    covered_sections: number;
    pending_sections: number;
    current_period_sequence: number | null;
  };
}

export interface OverviewResponse {
  context: {
    academic_year: { id: number; name: string } | null;
    semester: { id: number; name: string } | null;
    timezone: string;
    today: string;
    range: RangeInfo;
    previous_range: RangeInfo;
    scope: { grade_id: number | null; section_id: number | null };
  };
  today_operations: TodayOperations;
  attendance: AttendanceKpis;
  comparison: Record<string, Comparison>;
  warnings: {
    academic_year: unknown;
    due_is_point_in_time: boolean;
    due_students_by_type: Record<string, number>;
    issued_students_by_type: Record<string, number>;
    issued_in_range: {
      total: number;
      level_1: number;
      level_2: number;
      level_3: number;
      by_type: Record<string, number>;
    };
  };
  actions: { total: number; by_type: Record<string, number> };
  documents: {
    ready: number;
    pending: number;
    failed: number;
    by_type: Record<string, number>;
  };
  referrals: {
    created_in_range: {
      total: number;
      new: number;
      acknowledged: number;
      closed: number;
      cancelled: number;
    };
    by_category: Record<string, number>;
    by_source: Record<string, number>;
    open_now: number;
    unassigned_now: number;
  };
  counseling: {
    available: boolean;
    reason?: string;
    open_cases: number | null;
    waiting_teacher_responses: number | null;
    overdue_activities: number | null;
  };
}

export interface TrendPoint {
  date: string;
  full_absence: number;
  partial_absence: number;
  unexcused_full_absence: number;
  undetermined: number;
  morning_late: number;
}

export interface TrendResponse {
  unit: "STUDENT_DAYS";
  granularity: "DAY" | "WEEK";
  points: TrendPoint[];
  context: { range: RangeInfo; scope: unknown };
}

export interface SectionRow {
  section_id: number;
  section_name: string;
  grade_name: string;
  students: number;
  student_days: number;
  full_absence_days: number;
  partial_absence_days: number;
  unexcused_full_absence_days: number;
  period_late_occurrences: number;
  morning_late_occurrences: number;
}

export interface SectionsResponse {
  unit: "STUDENT_DAYS";
  sections: SectionRow[];
  context: { range: RangeInfo; scope: unknown };
}

export interface AttentionItem {
  kind: string;
  entity_type: string;
  entity_id: number;
  reason_code: string;
  display_text: string;
  priority: "HIGH" | "NORMAL";
  target_url: string;
  occurred_at: string | null;
}

export interface AttentionResponse {
  total: number;
  counts: Record<string, number>;
  items: AttentionItem[];
  item_cap_per_kind: number;
}

/** يبني query string واحدًا لكل نقاط اللوحة — النطاق والفلاتر مصدرها واحد. */
export function dashboardQuery(filters: DashboardFilters): string {
  const query = new URLSearchParams();
  if (filters.preset === "CUSTOM") {
    if (filters.fromDate) query.set("from_date", filters.fromDate);
    if (filters.toDate) query.set("to_date", filters.toDate);
  } else {
    query.set("preset", filters.preset);
  }
  if (filters.gradeId) query.set("grade", String(filters.gradeId));
  if (filters.sectionId) query.set("section", String(filters.sectionId));
  return query.toString();
}

export const getOverview = (filters: DashboardFilters, signal?: AbortSignal) =>
  apiRequest<OverviewResponse>(`/dashboard/overview/?${dashboardQuery(filters)}`, { signal });

export const getTrend = (filters: DashboardFilters, signal?: AbortSignal) =>
  apiRequest<TrendResponse>(`/dashboard/attendance-trend/?${dashboardQuery(filters)}`, {
    signal,
  });

export const getSections = (filters: DashboardFilters, signal?: AbortSignal) =>
  apiRequest<SectionsResponse>(`/dashboard/sections/?${dashboardQuery(filters)}`, { signal });

export const getAttention = (signal?: AbortSignal) =>
  apiRequest<AttentionResponse>("/dashboard/attention/", { signal });

export const getToday = (signal?: AbortSignal) =>
  apiRequest<TodayOperations>("/dashboard/today/", { signal });
