import { apiRequest } from "@/api/client";
import type { ReferralRow } from "@/features/referrals/api";

const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? "/api/v1";

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
  pageSize?: number;
}

export interface ReportResponse<TSummary, TRow> {
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
  under_vice_review: number;
  referred: number;
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
  if (filters.pageSize) params.set("page_size", String(filters.pageSize));
  Object.entries(extra).forEach(([key, value]) => {
    if (value !== undefined && value !== "") params.set(key, String(value));
  });
  return params.toString();
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

async function downloadReportExcel(
  path: string,
  filters: CommonReportFilters,
  extra: Record<string, string | number | undefined>,
  filename: string,
) {
  const response = await fetch(`${API_BASE_URL}${path}?${query(filters, extra)}`, {
    credentials: "include",
  });
  if (!response.ok) {
    throw new Error("تعذر تصدير ملف Excel.");
  }
  downloadBlob(await response.blob(), filename);
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

export const downloadAbsenceReportExcel = (
  filters: CommonReportFilters,
  extra: { absenceType: string; excuseType: string },
) => downloadReportExcel(
  "/reports/absence/export.xlsx",
  filters,
  { absence_type: extra.absenceType, excuse_type: extra.excuseType },
  "absence-report.xlsx",
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

export const downloadLatenessReportExcel = (
  filters: CommonReportFilters,
  extra: { minOccurrences: number; minMinutes: number },
) => downloadReportExcel(
  "/reports/lateness/export.xlsx",
  filters,
  {
    min_occurrences: extra.minOccurrences || undefined,
    min_minutes: extra.minMinutes || undefined,
  },
  "lateness-report.xlsx",
);

export const getReferralsReport = (
  filters: CommonReportFilters,
  extra: Record<string, string | undefined>,
  signal?: AbortSignal,
) => apiRequest<ReportResponse<ReferralReportSummary, ReferralRow>>(
  `/reports/referrals/?${query(filters, extra)}`,
  { signal },
);

export const downloadReferralsReportExcel = (
  filters: CommonReportFilters,
  extra: Record<string, string | undefined>,
) => downloadReportExcel(
  "/reports/referrals/export.xlsx",
  filters,
  extra,
  "referrals-report.xlsx",
);
