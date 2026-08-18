import { apiRequest, getCookie } from "@/api/client";
import type { Me, MembershipSummary } from "@/types/auth";

/** يضمن وجود CSRF cookie قبل أول عملية معدلة (login). */
export async function ensureCsrfCookie(): Promise<void> {
  if (!getCookie("csrftoken")) {
    await apiRequest<{ detail: string }>("/auth/csrf/");
  }
}

export async function login(mobile: string, password: string): Promise<Me> {
  await ensureCsrfCookie();
  return apiRequest<Me>("/auth/login/", {
    method: "POST",
    body: { mobile, password },
  });
}

export function logout(): Promise<{ detail: string }> {
  return apiRequest<{ detail: string }>("/auth/logout/", { method: "POST" });
}

export function getMe(signal?: AbortSignal): Promise<Me> {
  return apiRequest<Me>("/auth/me/", { signal });
}

export function getMySchools(
  signal?: AbortSignal,
): Promise<{ memberships: MembershipSummary[] }> {
  return apiRequest<{ memberships: MembershipSummary[] }>("/auth/schools/", { signal });
}

export function switchActiveSchool(schoolId: number): Promise<Me> {
  return apiRequest<Me>("/session/active-school/", {
    method: "POST",
    body: { school_id: schoolId },
  });
}
