import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import { queryClient } from "@/app/queryClient";
import { buildMe, membership, mockApi } from "@/test/mockApi";
import { renderApp } from "@/test/renderApp";

const SECTIONS = [
  { id: 11, name: "أ", code: "A", grade: { id: 1, name: "الأول الثانوي" } },
  { id: 12, name: "ب", code: "B", grade: { id: 1, name: "الأول الثانوي" } },
];

const MANAGER = buildMe({
  active_school: { id: 10, name: "ثانوية الأندلس", slug: "andalus" },
  roles: ["SCHOOL_MANAGER"],
  memberships: [membership(1, 10, "ثانوية الأندلس", ["SCHOOL_MANAGER"])],
});

const COUNSELOR = {
  id: 2,
  display_name: "فهد المرشد",
  employee_number: null,
  job_title: "مرشد طلابي",
  mobile: "+9665****0004",
  roles: ["COUNSELOR"],
  membership_status: "ACTIVE",
  joined_at: "2026-08-18",
  is_active: true,
  counselor_sections: [SECTIONS[0]],
  counselor_section_count: 1,
};

describe("Counselor section assignments", () => {
  beforeEach(() => {
    queryClient.clear();
    document.cookie = "csrftoken=test-token";
  });

  it("selects specific sections while adding a counselor", async () => {
    const api = mockApi({
      "/auth/me/": { body: MANAGER },
      "/sections/": { body: SECTIONS },
      "/staff/": (init) => init?.method === "POST"
        ? { status: 201, body: { ...COUNSELOR, id: 9, temporary_password: "0557771000", invitation_sent: false } }
        : { body: { count: 0, next: null, previous: null, results: [] } },
    });
    renderApp("/staff");
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "إدخال يدوي" }));
    await user.type(screen.getByLabelText("اسم الموظف الكامل *"), "مرشد جديد");
    await user.type(screen.getByLabelText("رقم الجوال *"), "0557771000");
    await user.selectOptions(screen.getByLabelText("الدور الأول في المنصة *"), "COUNSELOR");
    await user.click(await screen.findByLabelText(/فصول محددة/));
    await user.click(screen.getByLabelText("الأول الثانوي / أ"));
    await user.click(screen.getByRole("button", { name: "إضافة الموظف" }));

    await screen.findByText("0557771000");
    const createCall = api.calls.find((call) => call.url.includes("/staff/") && call.init?.method === "POST");
    expect(JSON.parse(String(createCall?.init?.body))).toMatchObject({
      role: "COUNSELOR",
      counselor_section_ids: [11],
      confirm_section_reassignment: false,
    });
  });

  it("lets the manager edit a counselor's sections", async () => {
    const api = mockApi({
      "/auth/me/": { body: MANAGER },
      "/sections/": { body: SECTIONS },
      "/staff/2/counselor-sections/": { body: { ...COUNSELOR, counselor_sections: SECTIONS, counselor_section_count: 2 } },
      "/staff/": { body: { count: 1, next: null, previous: null, results: [COUNSELOR] } },
    });
    renderApp("/staff");
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "إدارة" }));
    const editor = await screen.findByTestId("counselor-sections-2");
    await user.click(within(editor).getByLabelText("الأول الثانوي / ب"));
    await user.click(within(editor).getByRole("button", { name: "حفظ توزيع الفصول" }));

    await waitFor(() => {
      const call = api.calls.find((item) => item.url.includes("/staff/2/counselor-sections/") && item.init?.method === "PATCH");
      expect(JSON.parse(String(call?.init?.body))).toEqual({
        counselor_section_ids: [11, 12],
        confirm_section_reassignment: false,
      });
    });
  });
});
