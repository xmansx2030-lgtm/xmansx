import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it } from "vitest";

import { queryClient } from "@/app/queryClient";
import { RequireSchoolRoles } from "@/features/auth/guards";
import { buildMe, membership, mockApi } from "@/test/mockApi";
import type { SchoolRole } from "@/types/auth";

function meWithRoles(roles: SchoolRole[]) {
  return buildMe({
    active_school: { id: 10, name: "ثانوية الاختبار", slug: "test-school" },
    roles,
    memberships: [membership(1, 10, "ثانوية الاختبار", roles)],
  });
}

function renderRestrictedRoute(roles: SchoolRole[], allowedRoles: SchoolRole[]) {
  mockApi({ "/auth/me/": { body: meWithRoles(roles) } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/restricted"]}>
        <Routes>
          <Route element={<RequireSchoolRoles allowedRoles={allowedRoles} />}>
            <Route path="/restricted" element={<h1>المسار المحمي</h1>} />
          </Route>
          <Route path="/dashboard" element={<h1>مساحة الإدارة</h1>} />
          <Route path="/counselor" element={<h1>مساحة المرشد</h1>} />
          <Route path="/" element={<h1>مساحة المعلم</h1>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("RequireSchoolRoles", () => {
  beforeEach(() => {
    queryClient.clear();
  });

  it("يعيد المرشد من لوحة الإدارة إلى محطة عمله بدلاً من عرض أخطاء صلاحيات", async () => {
    renderRestrictedRoute(["COUNSELOR"], ["SCHOOL_MANAGER", "VICE_PRINCIPAL"]);

    expect(await screen.findByRole("heading", { name: "مساحة المرشد" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "المسار المحمي" })).toBeNull();
  });

  it("يبقي الوكيل داخل مسارات التشغيل المصرح بها", async () => {
    renderRestrictedRoute(["VICE_PRINCIPAL"], ["SCHOOL_MANAGER", "VICE_PRINCIPAL"]);

    expect(await screen.findByRole("heading", { name: "المسار المحمي" })).toBeInTheDocument();
  });
});
