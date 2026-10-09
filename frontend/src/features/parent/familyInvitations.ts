import { apiRequest } from "@/api/client";
import type { Me } from "@/types/auth";

export interface SchoolFamilyChild { id: number; name: string; revision: number }
export interface FamilyInvitation {
  id: string;
  name: string;
  mobile_masked: string;
  delivery_status: "PENDING" | "SENDING" | "SENT" | "FAILED" | "UNKNOWN";
  lifecycle: "OPEN" | "ACTIVATED" | "REVOKED" | "EXPIRED" | "NEEDS_REVIEW";
  created_at: string;
  expires_at: string;
  consumed_at: string | null;
  failure_code: string;
  student_ids: number[];
  partial: boolean;
}
export interface SchoolFamily {
  key: string;
  name: string;
  names: string[];
  mobile: string;
  mobile_masked: string;
  needs_review: boolean;
  child_count: number;
  children: SchoolFamilyChild[];
  invitation: FamilyInvitation | null;
}
export interface SchoolFamiliesPage {
  count: number; next: string | null; previous: string | null;
  results: SchoolFamily[]; sms_enabled: boolean; sms_configured: boolean;
}
export interface FamilyInvitationInput {
  mobile: string; name: string; relationship_type: string; verification_note: string;
  children: Array<{ id: number; revision: number }>; reissue: boolean;
}
export interface FamilyInvitationMetadata {
  school_name: string; children_count: number; account_exists: boolean;
  requires_login: boolean; email_verified: boolean;
}
export function getSchoolFamilies(page = 1, signal?: AbortSignal, search = "") {
  const params = new URLSearchParams({ page: String(page) });
  if (search.trim()) params.set("search", search.trim());
  return apiRequest<SchoolFamiliesPage>(`/staff/parents/families/?${params}`, { signal });
}
export function sendFamilyInvitations(invitations: FamilyInvitationInput[]) {
  return apiRequest<{ invitations: FamilyInvitation[] }>("/staff/parents/families/", {
    method: "POST", body: { invitations },
  });
}
export function checkFamilyInvitation(token: string, signal?: AbortSignal) {
  return apiRequest<FamilyInvitationMetadata>("/parent/family-invitation/check/", {
    method: "POST", body: { token }, signal,
  });
}
export function activateFamilyInvitation(data: {
  token: string; email?: string; new_password?: string;
  confirm_password?: string; current_password?: string;
}) {
  return apiRequest<Me>("/parent/family-invitation/activate/", { method: "POST", body: data });
}
