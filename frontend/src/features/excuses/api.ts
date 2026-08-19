import { apiRequest, getCookie } from "@/api/client";

// ---- الأنواع ----

export type ExcuseStatus = "PENDING" | "APPROVED" | "REJECTED" | "CANCELLED";
export type ReasonType =
  | "MEDICAL_REPORT"
  | "MEDICAL_APPOINTMENT"
  | "OFFICIAL"
  | "FAMILY"
  | "OTHER";

export const REASON_LABELS: Record<ReasonType, string> = {
  MEDICAL_REPORT: "تقرير طبي",
  MEDICAL_APPOINTMENT: "موعد طبي",
  OFFICIAL: "عذر رسمي",
  FAMILY: "ظرف أسري",
  OTHER: "أخرى",
};

export const STATUS_LABELS: Record<ExcuseStatus, string> = {
  PENDING: "بانتظار الاعتماد",
  APPROVED: "معتمد",
  REJECTED: "مرفوض",
  CANCELLED: "ملغى",
};

export interface StudentBrief {
  id: number;
  full_name: string;
  grade_name: string | null;
  section_name: string | null;
}

export interface ExcuseRow {
  id: number;
  student: StudentBrief;
  status: ExcuseStatus;
  status_label: string;
  reason_type: ReasonType;
  reason_type_label: string;
  date_from: string | null;
  date_to: string | null;
  targets_count: number;
  active_coverage_count: number;
  attachments_count: number;
  recorded_at: string;
  recorded_by_name: string | null;
  approved_by_name: string | null;
}

export interface ExcuseTarget {
  id: number;
  attendance_date: string;
  period_sequence: number | null;
}

export interface ExcuseCoverage {
  id: number;
  attendance_date: string;
  period_sequence: number;
  status: "ACTIVE" | "VOIDED";
  status_label: string;
  voided_at: string | null;
  void_reason: string;
}

export interface ExcuseAttachment {
  id: number;
  original_filename: string;
  mime_type: string;
  size_bytes: number;
  created_at: string;
  uploaded_by_name: string | null;
}

export interface ExcuseDetail extends Omit<ExcuseRow, "date_from" | "date_to" | "targets_count" | "attachments_count"> {
  notes: string;
  targets: ExcuseTarget[];
  coverages: ExcuseCoverage[];
  attachments: ExcuseAttachment[];
  approved_at: string | null;
  rejected_at: string | null;
  rejected_by_name: string | null;
  rejection_reason: string;
  cancelled_at: string | null;
  cancelled_by_name: string | null;
  cancellation_reason: string;
}

export interface PreviewDay {
  attendance_date: string;
  scope: "FULL_DAY" | number[];
  expected_periods: number;
  scope_periods: number;
  submitted_periods: number;
  missing_periods: number;
  absent_periods: number;
  present_periods: number;
  late_periods: number;
  complete: boolean;
}

export interface ExcusePreview {
  excuse_id: number;
  days: PreviewDay[];
  covered_absent_periods: number;
  already_excused_periods: number;
  already_excused_dates: string[];
  preview_hash: string;
}

export interface ExcuseKpis {
  pending_count: number;
  approved_today_count: number;
  rejected_count: number;
  cancelled_count: number;
}

export interface Paginated<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface ExcuseFilters {
  status?: string;
  reason_type?: string;
  student?: number;
  grade?: number;
  section?: number;
  from_date?: string;
  to_date?: string;
  page?: number;
}

// ---- الطلبات ----

function excusesQuery(filters: ExcuseFilters): string {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== undefined && value !== "" && value !== null) {
      params.set(key, String(value));
    }
  });
  const query = params.toString();
  return query ? `?${query}` : "";
}

export const getExcuses = (filters: ExcuseFilters = {}, signal?: AbortSignal) =>
  apiRequest<Paginated<ExcuseRow>>(`/excuses/${excusesQuery(filters)}`, { signal });

export const getExcuseKpis = (signal?: AbortSignal) =>
  apiRequest<ExcuseKpis>("/excuses/kpis/", { signal });

export const getExcuse = (id: number, signal?: AbortSignal) =>
  apiRequest<ExcuseDetail>(`/excuses/${id}/`, { signal });

export const createExcuse = (body: {
  student_id: number;
  reason_type: ReasonType;
  notes: string;
  targets: { attendance_date: string; period_sequence?: number | null }[];
}) => apiRequest<ExcuseDetail>("/excuses/", { method: "POST", body });

export const updateExcuse = (
  id: number,
  body: { reason_type?: ReasonType; notes?: string; targets?: { attendance_date: string; period_sequence?: number | null }[] },
) => apiRequest<ExcuseDetail>(`/excuses/${id}/`, { method: "PATCH", body });

export const previewExcuse = (id: number) =>
  apiRequest<ExcusePreview>(`/excuses/${id}/preview/`, { method: "POST" });

export const approveExcuse = (id: number, previewHash: string) =>
  apiRequest<ExcuseDetail>(`/excuses/${id}/approve/`, {
    method: "POST",
    body: { preview_hash: previewHash },
  });

export const rejectExcuse = (id: number, reason: string) =>
  apiRequest<ExcuseDetail>(`/excuses/${id}/reject/`, { method: "POST", body: { reason } });

export const cancelExcuse = (id: number, reason: string) =>
  apiRequest<ExcuseDetail>(`/excuses/${id}/cancel/`, { method: "POST", body: { reason } });

/** الرفع بـFormData — خارج apiRequest كنمط رفع الشعار/الاستيراد. */
export async function uploadExcuseAttachment(excuseId: number, file: File) {
  const formData = new FormData();
  formData.append("file", file);
  const response = await fetch(`/api/v1/excuses/${excuseId}/attachments/`, {
    method: "POST",
    credentials: "include",
    headers: { "X-CSRFToken": getCookie("csrftoken") ?? "" },
    body: formData,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.message ?? "تعذر رفع المرفق.");
  }
  return (await response.json()) as ExcuseAttachment;
}

export const attachmentDownloadUrl = (excuseId: number, attachmentId: number) =>
  `/api/v1/excuses/${excuseId}/attachments/${attachmentId}/`;

export const deleteExcuseAttachment = (excuseId: number, attachmentId: number) =>
  apiRequest<void>(`/excuses/${excuseId}/attachments/${attachmentId}/`, {
    method: "DELETE",
  });
