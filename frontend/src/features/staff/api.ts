import { apiRequest, getCookie } from "@/api/client";
import type { Paginated } from "@/features/students/api";

const IMPORT_COMMIT_TIMEOUT_MS = 120_000;

export interface StaffMember {
  id: number;
  display_name: string;
  employee_number: string | null;
  job_title: string;
  mobile: string; // مقنع في القائمة — كامل في التفاصيل (مدير فقط)
  roles: string[];
  capabilities?: string[];
  membership_status: string;
  joined_at: string;
  is_active: boolean;
  is_current_user?: boolean;
  counselor_sections?: CounselorSection[];
  counselor_section_count?: number;
  vice_principal_scopes?: VicePrincipalScope[];
  vice_principal_scope_count?: number;
}

export interface CounselorSection {
  id: number;
  name: string;
  code: string;
  grade: { id: number; name: string };
}

export type VicePrincipalScope =
  | { kind: "GRADE"; id: number; name: string }
  | { kind: "SECTION"; id: number; name: string; grade: { id: number; name: string } };

export interface ManualStaffInput {
  display_name: string;
  mobile: string;
  employee_number?: string;
  job_title?: string;
  role: string;
  counselor_section_ids?: number[];
  confirm_section_reassignment?: boolean;
  vice_principal_grade_ids?: number[];
  vice_principal_section_ids?: number[];
  confirm_scope_reassignment?: boolean;
}

export interface StaffUpdateInput {
  display_name?: string;
  employee_number?: string;
  job_title?: string;
}

export interface ManualStaffResult extends StaffMember {
  temporary_password: string | null;
  invitation_sent: boolean;
}

export interface StaffImportJob {
  id: number;
  status:
    | "UPLOADED"
    | "PROCESSING"
    | "READY_FOR_REVIEW"
    | "IMPORTING"
    | "COMPLETED"
    | "FAILED"
    | "CANCELLED";
  original_filename: string;
  headers: string[];
  header_row?: number;
  suggested_mapping: Partial<Record<string, number | null>> | null;
  total_rows: number;
  invalid_rows: number;
  duplicate_rows: number;
  summary: {
    new?: number;
    invite?: number;
    add_role?: number;
    profile_update?: number;
    unchanged?: number;
    invitation_pending?: number;
    manual?: number;
    errors?: number;
    duplicates?: number;
    created?: number;
    invited?: number;
    roles_added?: number;
    profiles_updated?: number;
  };
  error_code: string;
  new_credentials?: { name: string; mobile_masked: string; temporary_password: string }[];
}

export interface StaffPreviewRow {
  row_number: number;
  status: string;
  data: {
    full_name?: string;
    mobile_masked?: string;
    employee_number?: string | null;
    job_title?: string;
  };
  error_codes: string[];
  error_message: string;
}

export function getStaff(
  params: { page?: number; search?: string; role?: string; status?: string },
  signal?: AbortSignal,
): Promise<Paginated<StaffMember>> {
  const query = new URLSearchParams();
  if (params.page) query.set("page", String(params.page));
  if (params.search) query.set("search", params.search);
  if (params.role) query.set("role", params.role);
  if (params.status) query.set("status", params.status);
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiRequest<Paginated<StaffMember>>(`/staff/${suffix}`, { signal });
}

export const createStaff = (input: ManualStaffInput) =>
  apiRequest<ManualStaffResult>("/staff/", { method: "POST", body: input });

export const getStaffDetail = (id: number) => apiRequest<StaffMember>(`/staff/${id}/`);

export const updateStaff = (id: number, input: StaffUpdateInput) =>
  apiRequest<StaffMember>(`/staff/${id}/`, { method: "PATCH", body: input });

export const updateCounselorSections = (
  id: number,
  counselorSectionIds: number[],
  confirmSectionReassignment = false,
) =>
  apiRequest<StaffMember>(`/staff/${id}/counselor-sections/`, {
    method: "PATCH",
    body: {
      counselor_section_ids: counselorSectionIds,
      confirm_section_reassignment: confirmSectionReassignment,
    },
  });

export const updateVicePrincipalScopes = (
  id: number,
  gradeIds: number[],
  sectionIds: number[],
  confirmScopeReassignment = false,
) =>
  apiRequest<StaffMember>(`/staff/${id}/vice-principal-scopes/`, {
    method: "PATCH",
    body: {
      vice_principal_grade_ids: gradeIds,
      vice_principal_section_ids: sectionIds,
      confirm_scope_reassignment: confirmScopeReassignment,
    },
  });

export const addStaffRole = (id: number, role: string) =>
  apiRequest<StaffMember>(`/staff/${id}/roles/`, { method: "POST", body: { role } });

export const removeStaffRole = (id: number, role: string) =>
  apiRequest<StaffMember>(`/staff/${id}/roles/${role}/`, { method: "DELETE" });

export const grantMorningAttendance = (id: number) =>
  apiRequest<StaffMember>(`/staff/${id}/morning-attendance/`, { method: "POST" });

export const revokeMorningAttendance = (id: number) =>
  apiRequest<StaffMember>(`/staff/${id}/morning-attendance/`, { method: "DELETE" });

export const suspendStaff = (id: number) =>
  apiRequest<StaffMember>(`/staff/${id}/suspend/`, { method: "POST" });

export const activateStaff = (id: number) =>
  apiRequest<StaffMember>(`/staff/${id}/activate/`, { method: "POST" });

export const reinviteStaff = (id: number) =>
  apiRequest<StaffMember>(`/staff/${id}/reinvite/`, { method: "POST" });

export interface StaffPasswordResetResult {
  temporary_password: string;
  must_change_password: true;
}

export const resetStaffPassword = (id: number) =>
  apiRequest<StaffPasswordResetResult>(`/staff/${id}/reset-password/`, { method: "POST" });

export const deleteStaff = (id: number) =>
  apiRequest<void>(`/staff/${id}/`, { method: "DELETE" });

// ---- الاستيراد ----

export async function uploadStaffImportFile(file: File): Promise<StaffImportJob> {
  const formData = new FormData();
  formData.append("file", file);
  const response = await fetch("/api/v1/staff-imports/", {
    method: "POST",
    credentials: "include",
    headers: { "X-CSRFToken": getCookie("csrftoken") ?? "" },
    body: formData,
  });
  const body = (await response.json()) as StaffImportJob & { message?: string };
  if (!response.ok) throw new Error(body.message ?? "تعذر رفع الملف.");
  return body;
}

export const getStaffImportJob = (jobId: number, signal?: AbortSignal) =>
  apiRequest<StaffImportJob>(`/staff-imports/${jobId}/`, { signal });

export const processStaffImportJob = (
  jobId: number,
  mapping: Partial<Record<string, number>>,
) =>
  apiRequest<StaffImportJob>(`/staff-imports/${jobId}/process/`, {
    method: "POST",
    body: { mapping },
  });

export const getStaffImportPreview = (jobId: number, category: string, page: number) =>
  apiRequest<Paginated<StaffPreviewRow>>(
    `/staff-imports/${jobId}/preview/?category=${encodeURIComponent(category)}&page=${page}`,
  );

export const commitStaffImportJob = (jobId: number) =>
  apiRequest<StaffImportJob>(`/staff-imports/${jobId}/commit/`, {
    method: "POST",
    timeoutMs: IMPORT_COMMIT_TIMEOUT_MS,
  });

export const STAFF_MAPPING_LABELS: Record<string, string> = {
  full_name: "اسم المعلم",
  mobile: "رقم الجوال",
  employee_number: "الرقم الوظيفي",
  job_title: "المسمى الوظيفي",
};

export const STAFF_CATEGORY_LABELS: Record<string, string> = {
  "": "الكل",
  NEW: "معلمون جدد",
  EXISTING_USER_INVITE: "حسابات موجودة — دعوة",
  ADD_TEACHER_ROLE: "إضافة دور معلم",
  PROFILE_UPDATE: "تحديث بيانات",
  EXISTING_UNCHANGED: "بلا تغيير",
  INVITATION_PENDING: "دعوة قائمة",
  NEEDS_MANUAL_ACTION: "يتطلب إجراء",
  ERROR: "أخطاء",
  DUPLICATE_IN_FILE: "تكرارات",
};

export const MEMBERSHIP_STATUS_LABELS: Record<string, string> = {
  ACTIVE: "فعال",
  INVITED: "مدعو",
  DECLINED: "رفض الدعوة",
  SUSPENDED: "موقوف",
  LEFT: "منتهية",
};
