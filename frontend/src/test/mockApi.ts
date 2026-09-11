import { vi } from "vitest";

import type { Me, MembershipSummary } from "@/types/auth";

export interface MockRoute {
  status?: number;
  body: unknown;
}

/** يركب fetch وهمي يطابق المسارات بالاحتواء — آخر تعريف مطابق يفوز. */
export function mockApi(
  routes: Record<string, MockRoute | ((init?: RequestInit) => MockRoute)>,
) {
  const calls: { url: string; init?: RequestInit }[] = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    calls.push({ url, init });
    for (const [pattern, route] of Object.entries(routes)) {
      if (url.includes(pattern)) {
        const resolved = typeof route === "function" ? route(init) : route;
        return new Response(JSON.stringify(resolved.body), {
          status: resolved.status ?? 200,
          headers: { "Content-Type": "application/json", "X-Request-ID": "test-req-id" },
        });
      }
    }
    return new Response(
      JSON.stringify({ code: "NOT_FOUND", message: "المورد المطلوب غير موجود.", details: {} }),
      { status: 404 },
    );
  });
  vi.stubGlobal("fetch", fetchMock);
  return { fetchMock, calls };
}

export function membership(
  id: number,
  schoolId: number,
  schoolName: string,
  roles: MembershipSummary["roles"],
): MembershipSummary {
  return {
    id,
    school: { id: schoolId, name: schoolName, slug: `school-${schoolId}` },
    roles,
    status: "ACTIVE",
  };
}

export function buildMe(overrides: Partial<Me> = {}): Me {
  return {
    id: 1,
    mobile: "+966550000001",
    name: "أحمد المعلم",
    is_platform_admin: false,
    is_platform_owner: false,
    platform_role: null,
    platform_role_label: "",
    platform_capabilities: [],
    must_change_password: false,
    active_school: null,
    roles: [],
    capabilities: [],
    memberships: [],
    invitations: [],
    ...overrides,
  };
}

export const UNAUTHENTICATED: MockRoute = {
  status: 403,
  body: { code: "AUTHENTICATION_REQUIRED", message: "يجب تسجيل الدخول أولاً.", details: {} },
};
