import { apiRequest } from "@/api/client";

// ---- الأنواع ----

export type ReferralStatus = "NEW" | "ACKNOWLEDGED" | "CLOSED" | "CANCELLED";
export type ReferralSourceType = "TEACHER" | "VICE_PRINCIPAL" | "SCHOOL_MANAGER";

export const STATUS_LABELS: Record<ReferralStatus, string> = {
  NEW: "جديدة",
  ACKNOWLEDGED: "تم الاستلام",
  CLOSED: "مغلقة",
  CANCELLED: "ملغاة",
};

export interface ReferralOption {
  value: string;
  label: string;
}

export interface ReferralCategoryOption extends ReferralOption {
  reasons: ReferralOption[];
}

export interface ReferralOptions {
  source_type: ReferralSourceType;
  can_assign: boolean;
  categories: ReferralCategoryOption[];
  observation_types: ReferralOption[];
}

export interface ReferralStudent {
  id: number;
  full_name: string;
  grade_name: string | null;
  section_name: string | null;
}

export interface ReferralCandidate {
  id: number;
  full_name: string;
  grade: { id: number; name: string };
  section: { id: number; name: string };
}

export interface ReferralRow {
  id: number;
  student: ReferralStudent;
  source_type: ReferralSourceType;
  source_type_label: string;
  category: string;
  category_label: string;
  reason_code: string;
  reason_label: string;
  status: ReferralStatus;
  status_label: string;
  priority: string;
  priority_label: string;
  created_at: string;
  created_by_name: string | null;
  assigned_counselor_id: number | null;
  assigned_counselor_name: string | null;
  counseling_case_id: number | null;
}

export interface ReferralContribution {
  id: number;
  observation_type: string;
  observation_type_label: string;
  notes: string;
  created_at: string;
  created_by_name: string | null;
}

export interface ReferralEvent {
  id: number;
  event_type: string;
  event_type_label: string;
  actor_name: string | null;
  created_at: string;
  metadata: Record<string, unknown>;
}

/** مؤشرات المواظبة — نفس الشكل للقطة الإحالة وللقيمة الحالية. */
export interface ReferralMetrics {
  student_name?: string;
  grade_name?: string | null;
  section_name?: string | null;
  full_absence_days?: number;
  unexcused_full_absence_days?: number;
  partial_absence_days?: number;
  absent_periods?: number;
  morning_late_occurrences?: number;
  morning_late_minutes?: number;
  highest_absence_warning_level?: string | null;
  highest_late_warning_level?: string | null;
}

export interface ReferralDetail extends ReferralRow {
  /** يحسبه الخادم: المنشئ قبل الاستلام أو الإدارة في أي وقت. */
  can_cancel: boolean;
  description: string;
  snapshot_at_referral: ReferralMetrics;
  current_metrics: ReferralMetrics | null;
  source_warning: {
    id: number;
    warning_type: string;
    level: string;
    issued_at: string;
  } | null;
  accepted_at: string | null;
  closed_at: string | null;
  closed_by_name: string | null;
  closure_reason: string;
  contributions: ReferralContribution[];
  events: ReferralEvent[];
}

export interface ReferralKpis {
  new_count: number;
  acknowledged_count: number;
  unassigned_count: number;
}

export interface Paginated<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface ReferralFilters {
  status?: string;
  category?: string;
  reason_code?: string;
  source_type?: string;
  counselor?: string;
  grade?: number;
  section?: number;
  student?: number;
  page?: number;
}

export interface DuplicateDetails {
  existing_referral_id: number;
  recommended_action: string;
}

// ---- الطلبات ----

function query(filters: ReferralFilters): string {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== undefined && value !== "" && value !== null) {
      params.set(key, String(value));
    }
  });
  const search = params.toString();
  return search ? `?${search}` : "";
}

export const getReferrals = (filters: ReferralFilters = {}, signal?: AbortSignal) =>
  apiRequest<Paginated<ReferralRow>>(`/referrals/${query(filters)}`, { signal });

export const getMyReferrals = (filters: ReferralFilters = {}, signal?: AbortSignal) =>
  apiRequest<Paginated<ReferralRow>>(`/referrals/mine/${query(filters)}`, { signal });

export const getReferralCandidates = (
  filters: { search?: string; grade?: number; section?: number; page?: number } = {},
  signal?: AbortSignal,
) => apiRequest<Paginated<ReferralCandidate>>(`/referrals/students/${query(filters)}`, { signal });

export const getReferralKpis = (signal?: AbortSignal) =>
  apiRequest<ReferralKpis>("/referrals/kpis/", { signal });

export const getReferralOptions = (signal?: AbortSignal) =>
  apiRequest<ReferralOptions>("/referrals/options/", { signal });

export const getCounselors = (signal?: AbortSignal) =>
  apiRequest<{ counselors: { id: number; name: string }[]; has_counselors: boolean }>(
    "/referrals/counselors/",
    { signal },
  );

export const getReferral = (id: number, signal?: AbortSignal) =>
  apiRequest<ReferralDetail>(`/referrals/${id}/`, { signal });

export const getStudentReferrals = (studentId: number, signal?: AbortSignal) =>
  apiRequest<{ results: ReferralRow[] }>(`/students/${studentId}/referrals/`, { signal });

export const createReferral = (body: {
  student_id: number;
  category: string;
  reason_code: string;
  description: string;
  priority?: string;
  source_warning_id?: number | null;
  assigned_counselor_id?: number | null;
  allow_duplicate?: boolean;
}) => apiRequest<ReferralDetail>("/referrals/", { method: "POST", body });

export const assignCounselor = (id: number, counselorMembershipId: number) =>
  apiRequest<ReferralDetail>(`/referrals/${id}/assign/`, {
    method: "POST",
    body: { counselor_membership_id: counselorMembershipId },
  });

export const acknowledgeReferral = (id: number) =>
  apiRequest<ReferralDetail>(`/referrals/${id}/acknowledge/`, { method: "POST" });

export const closeReferral = (id: number, reason: string) =>
  apiRequest<ReferralDetail>(`/referrals/${id}/close/`, {
    method: "POST",
    body: { reason },
  });

export const cancelReferral = (id: number, reason: string) =>
  apiRequest<ReferralDetail>(`/referrals/${id}/cancel/`, {
    method: "POST",
    body: { reason },
  });

export const addContribution = (
  id: number,
  body: { observation_type: string; notes: string },
) =>
  apiRequest<ReferralContribution>(`/referrals/${id}/contributions/`, {
    method: "POST",
    body,
  });

/** ملاحظة على الحالة المفتوحة لـ(طالب، فئة) — الخادم يحلها بنفسه.
 *  يُستخدم في مسار التكرار حيث لا يملك المُرسل رؤية الحالة القائمة بعد. */
export const contributeToOpenCase = (body: {
  student_id: number;
  category: string;
  observation_type: string;
  notes: string;
}) =>
  apiRequest<{ referral_id: number; contribution: ReferralContribution }>(
    "/referrals/contribute/",
    { method: "POST", body },
  );
