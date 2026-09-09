import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import { queryClient } from "@/app/queryClient";
import { buildMe, membership, mockApi } from "@/test/mockApi";
import { renderApp } from "@/test/renderApp";

const GUARD_ME = buildMe({
  name: "ناصر الحارس",
  active_school: { id: 10, name: "ثانوية الأندلس", slug: "andalus", school_type: "BOYS" },
  roles: ["GATE_GUARD"],
  memberships: [membership(1, 10, "ثانوية الأندلس", ["GATE_GUARD"])],
});

const PENDING = {
  id: 81,
  student: { id: 5, full_name: "محمد أحمد", student_number: "1001" },
  leave_date: "2026-09-09",
  leave_time: "10:35",
  grade_name: "الأول الثانوي",
  section_name: "2",
  recorded_by_name: "سعد الوكيل",
  recipient_name: "أحمد عبدالله",
  recipient_relationship: "والد",
  recipient_id_last4: "4321",
  gate_release: null,
};

describe("GatePage", () => {
  beforeEach(() => {
    queryClient.clear();
    document.cookie = "csrftoken=test-token";
  });

  it("shows the shared minimal queue and confirms a release", async () => {
    const api = mockApi({
      "/auth/me/": { body: GUARD_ME },
      "/gate/student-leaves/81/release/": {
        status: 201,
        body: {
          ...PENDING,
          gate_release: {
            released_at: "2026-09-09T10:37:00+03:00",
            released_by_name: "ناصر الحارس",
          },
        },
      },
      "/gate/student-leaves/": {
        body: {
          date: "2026-09-09",
          summary: { total: 1, pending: 1, released: 0 },
          results: [PENDING],
        },
      },
    });
    renderApp("/gate");
    const user = userEvent.setup();

    expect(await screen.findByRole("heading", { name: "خروج الطلاب" })).toBeInTheDocument();
    const card = await screen.findByTestId("gate-leave-81");
    expect(card).toHaveTextContent("محمد أحمد");
    expect(card).toHaveTextContent("1001");
    expect(card).toHaveTextContent("الأول الثانوي · فصل 2");
    expect(card).toHaveTextContent("أحمد عبدالله");
    expect(card).toHaveTextContent("4321");
    expect(screen.queryByText("موعد طبي لدى المستشفى")).not.toBeInTheDocument();

    await user.click(within(card).getByRole("button", { name: "تحقق واسمح بخروج الطالب" }));
    await user.click(screen.getByRole("button", { name: "تم التحقق والسماح بالخروج" }));

    await waitFor(() => expect(api.calls.some(
      (call) => call.url.includes("/gate/student-leaves/81/release/") && call.init?.method === "POST",
    )).toBe(true));
  });

  it("redirects a guard away from the administrative leave screen", async () => {
    mockApi({
      "/auth/me/": { body: GUARD_ME },
      "/gate/student-leaves/": {
        body: {
          date: "2026-09-09",
          summary: { total: 0, pending: 0, released: 0 },
          results: [],
        },
      },
    });
    renderApp("/student-leaves");

    expect(await screen.findByTestId("gate-page")).toBeInTheDocument();
    expect(screen.queryByTestId("student-leaves-page")).not.toBeInTheDocument();
  });
});
