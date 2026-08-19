import { apiRequest } from "@/api/client";

export type WarningType = "UNEXCUSED_FULL_DAY_ABSENCE" | "MORNING_LATE_OCCURRENCES";
export type WarningLevel = "LEVEL_1" | "LEVEL_2" | "LEVEL_3";
export type LevelState = "DUE" | "NOT_DUE" | "ISSUED";

export const WARNING_TYPE_LABELS: Record<WarningType, string> = {
  UNEXCUSED_FULL_DAY_ABSENCE: "غياب يوم كامل بدون عذر",
  MORNING_LATE_OCCURRENCES: "التأخر عن الدوام الصباحي",
};
export const WARNING_TYPE_UNITS: Record<WarningType, string> = {
  UNEXCUSED_FULL_DAY_ABSENCE: "أيام",
  MORNING_LATE_OCCURRENCES: "مرات",
};
export const LEVEL_LABELS: Record<WarningLevel, string> = {
  LEVEL_1: "الإنذار الأول",
  LEVEL_2: "الإنذار الثاني",
  LEVEL_3: "الإنذار الثالث",
};
export const LEVELS: WarningLevel[] = ["LEVEL_1", "LEVEL_2", "LEVEL_3"];

export interface RuleTypeConfig {
  is_enabled: boolean;
  levels: Record<WarningLevel, number>;
}
export type RulesMap = Record<WarningType, RuleTypeConfig>;

export interface EligibilityRow {
  student_id: number;
  full_name: string;
  grade_id: number;
  grade_name: string;
  section_name: string;
  warning_type: WarningType;
  is_enabled: boolean;
  current_value: number;
  highest_reached_level: WarningLevel | null;
  highest_due_level: WarningLevel | null;
  issued_levels: WarningLevel[];
  levels: Record<WarningLevel, { threshold: number; state: LevelState }>;
}

export interface EligibilityResponse {
  academic_year: { id: number; name: string };
  summary: Record<WarningType, { due_students: number; issued_students: number }>;
  results: EligibilityRow[];
  count: number;
  page: number;
  page_size: number;
}

export interface WarningRow {
  id: number;
  student_id: number;
  student_name: string;
  grade_name: string;
  section_name: string;
  warning_type: WarningType;
  warning_type_label: string;
  level: WarningLevel;
  level_label: string;
  status: "ISSUED" | "VOIDED";
  threshold_at_issue: number;
  metric_value_at_issue: number;
  issued_at: string;
  issued_by: string | null;
  notes: string;
  voided_at: string | null;
  voided_by: string | null;
  void_reason: string;
}

export interface WarningDetail extends WarningRow {
  academic_year: string;
  current_metric_value: number;
  metric_drifted: boolean;
  snapshot: Record<string, number | string>;
}

export interface Paginated<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export const getWarningRules = (signal?: AbortSignal) =>
  apiRequest<RulesMap>("/warning-rules/", { signal });

export const patchWarningRules = (payload: Partial<RulesMap>) =>
  apiRequest<RulesMap>("/warning-rules/", { method: "PATCH", body: payload });

export const getEligibility = (
  params: {
    warning_type?: WarningType | "";
    grade?: number | "";
    status?: "due" | "issued" | "all";
    page?: number;
  },
  signal?: AbortSignal,
) => {
  const query = new URLSearchParams();
  if (params.warning_type) query.set("warning_type", params.warning_type);
  if (params.grade) query.set("grade", String(params.grade));
  if (params.status) query.set("status", params.status);
  if (params.page) query.set("page", String(params.page));
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiRequest<EligibilityResponse>(`/warnings/eligibility/${suffix}`, { signal });
};

/** الإصدار: الخادم يعيد حساب الاستحقاق ويبني كل Snapshot — لا قيم موثوقة من العميل. */
export const issueWarning = (payload: {
  student_id: number;
  warning_type: WarningType;
  level: WarningLevel;
  notes?: string;
}) => apiRequest<WarningRow>("/warnings/issue/", { method: "POST", body: payload });

export const getStudentWarnings = (studentId: number, signal?: AbortSignal) =>
  apiRequest<Paginated<WarningRow>>(`/warnings/?student=${studentId}`, { signal });

export const getWarningDetail = (warningId: number, signal?: AbortSignal) =>
  apiRequest<WarningDetail>(`/warnings/${warningId}/`, { signal });

export const voidWarning = (warningId: number, reason: string) =>
  apiRequest<WarningRow>(`/warnings/${warningId}/void/`, {
    method: "POST",
    body: { reason },
  });
