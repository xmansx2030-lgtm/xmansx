import { apiRequest } from "@/api/client";
import type { ReferralRow } from "@/features/referrals/api";

export type ReportPreset =
  | "TODAY"
  | "THIS_WEEK"
  | "LAST_7_DAYS"
  | "LAST_30_DAYS"
  | "THIS_MONTH"
  | "CURRENT_SEMESTER"
  | "CUSTOM";

export interface CommonReportFilters {
  preset: ReportPreset;
  fromDate?: string;
  toDate?: string;
  grade?: number | "";
  section?: number | "";
  student?: number | null;
  page?: number;
}

interface ReportResponse<TSummary, TRow> {
  context: {
    range: { from_date: string; to_date: string; days: number; preset: ReportPreset };
    scope: { grade_id: number | null; section_id: number | null };
  };
  summary: TSummary;
  results: TRow[];
  count: number;
  page: number;
  page_size: number;
}

export interface AbsenceRow {
  student_id: number;
  full_name: string;
  grade_name: string;
  section_name: string;
  full_absence_days: number;
  partial_absence_days: number;
  absent_periods: number;
  excused_absent_periods: number;
  unexcused_absent_periods: number;
  incomplete_days: number;
}

export interface AbsenceSummary {
  students: number;
  student_days: number;
  full_absence_days: number;
  partial_absence_days: number;
  excused_absent_periods: number;
  unexcused_absent_periods: number;
  incomplete_days: number;
}

export interface LatenessRow {
  student_id: number;
  full_name: string;
  grade_name: string | null;
  section_name: string | null;
  morning_occurrences: number;
  morning_minutes: number;
}

export interface LatenessSummary {
  students: number;
  morning_occurrences: number;
  morning_minutes: number;
}

export interface ReferralReportSummary {
  total: number;
  new: number;
  acknowledged: number;
  closed: number;
  unassigned: number;
  high_priority: number;
}

function query(filters: CommonReportFilters, extra: Record<string, string | number | undefined>) {
  const params = new URLSearchParams();
  if (filters.preset === "CUSTOM") {
    if (filters.fromDate) params.set("from_date", filters.fromDate);
    if (filters.toDate) params.set("to_date", filters.toDate);
  } else {
    params.set("preset", filters.preset);
  }
  if (filters.grade) params.set("grade", String(filters.grade));
  if (filters.section) params.set("section", String(filters.section));
  if (filters.student) params.set("student", String(filters.student));
  if (filters.page) params.set("page", String(filters.page));
  Object.entries(extra).forEach(([key, value]) => {
    if (value !== undefined && value !== "") params.set(key, String(value));
  });
  return params.toString();
}

export const getAbsenceReport = (
  filters: CommonReportFilters,
  extra: { absenceType: string; excuseType: string },
  signal?: AbortSignal,
) => apiRequest<ReportResponse<AbsenceSummary, AbsenceRow>>(
  `/reports/absence/?${query(filters, {
    absence_type: extra.absenceType,
    excuse_type: extra.excuseType,
  })}`,
  { signal },
);

export const getLatenessReport = (
  filters: CommonReportFilters,
  extra: { minOccurrences: number; minMinutes: number },
  signal?: AbortSignal,
) => apiRequest<ReportResponse<LatenessSummary, LatenessRow>>(
  `/reports/lateness/?${query(filters, {
    min_occurrences: extra.minOccurrences || undefined,
    min_minutes: extra.minMinutes || undefined,
  })}`,
  { signal },
);

export const getReferralsReport = (
  filters: CommonReportFilters,
  extra: Record<string, string | undefined>,
  signal?: AbortSignal,
) => apiRequest<ReportResponse<ReferralReportSummary, ReferralRow>>(
  `/reports/referrals/?${query(filters, extra)}`,
  { signal },
);
