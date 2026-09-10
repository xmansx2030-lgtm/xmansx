import { apiRequest } from "@/api/client";
import type { SchoolType } from "@/types/auth";

export type SubscriptionStatus =
  | "TRIAL"
  | "ACTIVE"
  | "GRACE_PERIOD"
  | "EXPIRED"
  | "SUSPENDED"
  | "CANCELLED";

export interface EntitlementValue {
  numeric: number | null;
  enabled: boolean;
}

export type Entitlements = Record<string, EntitlementValue>;

export interface Plan {
  id: number;
  code: string;
  name_ar: string;
  name_en: string;
  description: string;
  is_active: boolean;
  is_public: boolean;
  billing_period: "MONTHLY" | "SEMI_ANNUAL" | "ANNUAL" | "CUSTOM";
  price_amount: string;
  currency: string;
  trial_days_default: number;
  entitlements: Record<string, number | boolean | null>;
}

export interface UsageEntry {
  used: number;
  limit: number | null;
  over_limit: boolean;
  near_limit?: boolean;
  remaining: number | null;
}

export interface Usage {
  students: UsageEntry;
  staff: UsageEntry;
  devices: UsageEntry;
  storage: UsageEntry & { used_gb: number; limit_gb: number | null };
}

export interface SubscriptionState {
  has_subscription: boolean;
  status: SubscriptionStatus | null;
  status_label?: string;
  access_mode: "FULL" | "READ_ONLY" | "BLOCKED";
  plan: { code: string; name: string; billing_period: string } | null;
  starts_at: string | null;
  ends_at: string | null;
  days_remaining: number | null;
  grace_ends_at: string | null;
  trial_ends_at: string | null;
}

export interface SchoolRow {
  id: number;
  name: string;
  slug: string;
  school_type: SchoolType;
  school_status: string;
  subscription_status: SubscriptionStatus | null;
  plan: string | null;
  plan_name: string | null;
  starts_at: string | null;
  ends_at: string | null;
  manager: { id: number; name: string } | null;
  usage: Usage;
}

export interface Paginated<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface SchoolDetail extends SchoolRow {
  created_at: string;
  updated_at: string;
  managers: SchoolManagerAccount[];
  subscription: SubscriptionState;
  usage: Usage;
  entitlements: Entitlements;
}

export interface SchoolManagerAccount {
  membership_id: number;
  user_id: number;
  name: string;
  mobile: string;
  membership_status: "ACTIVE" | "INVITED" | "DECLINED" | "SUSPENDED" | "LEFT";
  account_active: boolean;
  must_change_password: boolean;
  last_login: string | null;
  joined_at: string;
  shared_with_other_schools: boolean;
}

export interface ManagerCredentialResponse {
  manager: SchoolManagerAccount;
  temporary_password: string | null;
}

export interface SubscriptionRow {
  id: number;
  plan: string;
  plan_name: string;
  status: SubscriptionStatus;
  effective_status: SubscriptionStatus;
  starts_at: string;
  ends_at: string;
  trial_ends_at: string | null;
  grace_ends_at: string | null;
  suspension_reason: string;
  cancel_reason: string;
}

export interface SubscriptionHistory {
  current: SubscriptionRow | null;
  history: SubscriptionRow[];
}

export interface SubscriptionEvent {
  id: number;
  event_type: string;
  reason: string;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface Overview {
  schools_total: number;
  subscriptions: Record<string, number>;
  usage_totals: {
    active_students: number;
    active_staff: number;
    active_devices: number;
  };
  expiring_soon: {
    school_id: number;
    school_name: string;
    plan: string;
    ends_at: string;
    days_remaining: number;
  }[];
}

export interface SchoolFilters {
  search?: string;
  status?: string;
  plan?: string;
  expires_soon?: boolean;
  over_limit?: boolean;
}

export interface PlanChangePreview {
  plan: { id: number; code: string; name: string };
  impact: {
    students: { used: number; new_limit: number | null; over_limit: boolean };
    staff: { used: number; new_limit: number | null; over_limit: boolean };
    devices: { used: number; new_limit: number | null; over_limit: boolean };
    storage: { used_gb: number; new_limit_gb: number | null; over_limit: boolean };
  };
  deletes_data: false;
}

export interface CreateSchoolInput {
  school_name: string;
  school_type: SchoolType;
  manager_name: string;
  manager_mobile: string;
  plan_id?: number;
  subscription_mode: "TRIAL" | "ACTIVE";
  trial_days?: number | null;
  months?: number;
}

export interface CreateSchoolResponse extends SchoolRow {
  manager_membership_id: number;
  temporary_password: string | null;
}

export interface DeleteSchoolResponse {
  deleted: true;
  school_id: number;
  school_name: string;
  database_records_deleted: number;
  user_accounts_deleted: number;
  storage_objects_deleted: number;
  storage_objects_failed: number;
}

export interface PlanInput {
  code?: string;
  name_ar: string;
  name_en?: string;
  description?: string;
  billing_period?: Plan["billing_period"];
  price_amount?: string;
  currency?: string;
  trial_days_default?: number;
  is_public?: boolean;
  is_active?: boolean;
  entitlements?: Record<string, number | boolean | null>;
}

export const getPlatformOverview = (signal?: AbortSignal) =>
  apiRequest<Overview>("/platform/overview/", { signal });

export const getPlatformSchools = (filters: SchoolFilters = {}, signal?: AbortSignal) => {
  const query = new URLSearchParams();
  if (filters.search) query.set("search", filters.search);
  if (filters.status) query.set("status", filters.status);
  if (filters.plan) query.set("plan", filters.plan);
  if (filters.expires_soon) query.set("expires_soon", "1");
  if (filters.over_limit) query.set("over_limit", "1");
  const suffix = query.size ? `?${query.toString()}` : "";
  return apiRequest<Paginated<SchoolRow>>(`/platform/schools/${suffix}`, { signal });
};

export const createPlatformSchool = (body: CreateSchoolInput) =>
  apiRequest<CreateSchoolResponse>("/platform/schools/", { method: "POST", body });

export const getSchoolDetail = (schoolId: number, signal?: AbortSignal) =>
  apiRequest<SchoolDetail>(`/platform/schools/${schoolId}/`, { signal });

export const updatePlatformSchool = (
  schoolId: number,
  body: { name?: string; school_status?: string; school_type?: SchoolType },
) => apiRequest<SchoolDetail>(`/platform/schools/${schoolId}/`, { method: "PATCH", body });

export const deletePlatformSchool = (schoolId: number, confirmationName: string) =>
  apiRequest<DeleteSchoolResponse>(`/platform/schools/${schoolId}/`, {
    method: "DELETE",
    body: {
      confirmation_name: confirmationName,
      acknowledge_permanent_deletion: true,
    },
    timeoutMs: 60_000,
  });

export const addSchoolManager = (
  schoolId: number,
  body: { name: string; mobile: string },
) =>
  apiRequest<ManagerCredentialResponse>(`/platform/schools/${schoolId}/managers/`, {
    method: "POST",
    body,
  });

export const updateSchoolManager = (
  schoolId: number,
  membershipId: number,
  body: { name?: string; mobile?: string },
) =>
  apiRequest<SchoolManagerAccount>(
    `/platform/schools/${schoolId}/managers/${membershipId}/`,
    { method: "PATCH", body },
  );

export const runSchoolManagerAction = (
  schoolId: number,
  membershipId: number,
  action: "reset-password" | "suspend" | "reactivate",
) =>
  apiRequest<SchoolManagerAccount | ManagerCredentialResponse>(
    `/platform/schools/${schoolId}/managers/${membershipId}/${action}/`,
    { method: "POST" },
  );

export const getSubscriptionHistory = (schoolId: number, signal?: AbortSignal) =>
  apiRequest<SubscriptionHistory>(`/platform/schools/${schoolId}/subscription/`, { signal });

export const getSubscriptionEvents = (schoolId: number, signal?: AbortSignal) =>
  apiRequest<SubscriptionEvent[]>(
    `/platform/schools/${schoolId}/subscription/events/`,
    { signal },
  );

export const getPlanChangePreview = (
  schoolId: number,
  planId: number,
  signal?: AbortSignal,
) =>
  apiRequest<PlanChangePreview>(
    `/platform/schools/${schoolId}/subscription/plan-preview/?plan_id=${planId}`,
    { signal },
  );

export const runSubscriptionAction = (
  schoolId: number,
  action: string,
  body: Record<string, unknown>,
) =>
  apiRequest<SubscriptionRow>(`/platform/schools/${schoolId}/subscription/${action}/`, {
    method: "POST",
    body,
  });

export const getPlans = (signal?: AbortSignal) =>
  apiRequest<Plan[]>("/platform/plans/", { signal });

export const createPlan = (body: PlanInput) =>
  apiRequest<Plan>("/platform/plans/", { method: "POST", body });

export const updatePlan = (planId: number, body: Partial<PlanInput>) =>
  apiRequest<Plan>(`/platform/plans/${planId}/`, { method: "PATCH", body });

export const disablePlan = (planId: number) =>
  apiRequest<Plan>(`/platform/plans/${planId}/`, { method: "DELETE" });

export const getSchoolSubscription = (signal?: AbortSignal) =>
  apiRequest<{ subscription: SubscriptionState; usage: Usage }>("/school/subscription/", {
    signal,
  });
