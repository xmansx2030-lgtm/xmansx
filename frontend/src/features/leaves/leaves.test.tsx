import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import { queryClient } from "@/app/queryClient";
import { buildMe, membership, mockApi } from "@/test/mockApi";
import { renderApp } from "@/test/renderApp";

type Role = "SCHOOL_MANAGER" | "VICE_PRINCIPAL" | "COUNSELOR" | "TEACHER";

function roleMe(roles: Role[]) {
  return buildMe({
    active_school: { id: 10, name: "ثانوية الأندلس", slug: "andalus" },
    roles,
    memberships: [membership(1, 10, "ثانوية الأندلس", roles)],
  });
}

const LEAVE = {
  id: 81,
  student: {
    id: 5,
    full_name: "محمد أحمد",
    student_number: "1001",
    national_id_masked: "******5678",
  },
  leave_date: "2026-09-06",
  leave_time: "10:35",
  weekday_label: "الأحد",
  reason: "موعد طبي لدى المستشفى",
  recipient_name: "",
  recipient_relationship: "",
  recipient_id_last4: "",
  grade_name: "الأول الثانوي",
  section_name: "2",
  status: "ACTIVE",
  status_label: "ساري",
  recorded_by_name: "سعد الوكيل",
  created_at: "2026-09-06T10:30:00+03:00",
  cancelled_by_name: null,
  cancelled_at: null,
  cancellation_reason: "",
  gate_release: null,
};

const EMPTY_PAGE = {
  count: 0,
  next: null,
  previous: null,
  summary: { total: 0, active: 0, cancelled: 0 },
  results: [],
};

describe("StudentLeavesPage", () => {
  beforeEach(() => {
    queryClient.clear();
    document.cookie = "csrftoken=test-token";
  });

  it("vice principal records a structured leave and receives confirmation", async () => {
    const api = mockApi({
      "/auth/me/": { body: roleMe(["VICE_PRINCIPAL"]) },
      "/students/?": {
        body: {
          count: 1,
          next: null,
          previous: null,
          results: [{
            id: 5,
            full_name: "محمد أحمد",
            national_id_masked: "******5678",
            student_number: "1001",
            status: "ACTIVE",
            guardian_name: "",
            grade: { id: 1, name: "الأول الثانوي" },
            section: { id: 2, name: "2" },
          }],
        },
      },
      "/student-leaves/": (init) => init?.method === "POST"
        ? { status: 201, body: LEAVE }
        : { body: EMPTY_PAGE },
    });
    renderApp("/student-leaves");
    const user = userEvent.setup();

    expect(await screen.findByRole("heading", { name: "استئذانات الطلاب" })).toBeInTheDocument();
    expect(screen.getByText("مساحة الوكيل")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "تسجيل استئذان" }));
    await user.type(screen.getByLabelText("بحث عن الطالب"), "محمد");
    await user.click(await screen.findByTestId("leave-pick-student-5"));
    await user.clear(screen.getByLabelText("سبب الاستئذان"));
    await user.type(screen.getByLabelText("سبب الاستئذان"), "موعد طبي لدى المستشفى");
    await user.type(screen.getByLabelText("اسم المستلم"), "أحمد عبدالله");
    await user.type(screen.getByLabelText("صفة المستلم"), "والد");
    await user.type(screen.getByLabelText("آخر أربعة أرقام من هوية المستلم"), "٤٣٢١");
    await user.click(screen.getByRole("button", { name: "اعتماد الاستئذان" }));

    expect(await screen.findByText(/تم تسجيل استئذان محمد أحمد/)).toBeInTheDocument();
    const post = api.calls.find(
      (call) => call.url.includes("/student-leaves/") && call.init?.method === "POST",
    );
    expect(post).toBeDefined();
    expect(JSON.parse(String(post?.init?.body))).toMatchObject({
      student_id: 5,
      reason: "موعد طبي لدى المستشفى",
      recipient_name: "أحمد عبدالله",
      recipient_relationship: "والد",
      recipient_id_last4: "4321",
    });
  });

  it("shows the daily record and cancels with a required reason", async () => {
    const cancelled = {
      ...LEAVE,
      status: "CANCELLED",
      status_label: "ملغى",
      cancellation_reason: "لم يغادر الطالب المدرسة",
    };
    const api = mockApi({
      "/auth/me/": { body: roleMe(["SCHOOL_MANAGER"]) },
      "/student-leaves/81/cancel/": { body: cancelled },
      "/student-leaves/": {
        body: {
          count: 1,
          next: null,
          previous: null,
          summary: { total: 1, active: 1, cancelled: 0 },
          results: [LEAVE],
        },
      },
    });
    renderApp("/student-leaves");
    const user = userEvent.setup();
    const row = await screen.findByTestId("student-leave-81");
    expect(row).toHaveTextContent("الأحد");
    expect(row).toHaveTextContent("10:35");
    await user.click(within(row).getByRole("button", { name: "إلغاء الاستئذان" }));
    const confirm = screen.getByRole("button", { name: "تأكيد الإلغاء" });
    expect(confirm).toBeDisabled();
    await user.type(screen.getByLabelText("سبب إلغاء الاستئذان"), "لم يغادر الطالب المدرسة");
    await user.click(confirm);
    await waitFor(() => expect(api.calls.some(
      (call) => call.url.includes("/student-leaves/81/cancel/") && call.init?.method === "POST",
    )).toBe(true));
  });

  it("teacher cannot see the leave navigation or open its page", async () => {
    mockApi({ "/auth/me/": { body: roleMe(["TEACHER"]) } });
    renderApp("/student-leaves");
    await screen.findByTestId("active-school-name");
    expect(screen.queryByRole("link", { name: "الاستئذانات" })).not.toBeInTheDocument();
    expect(screen.queryByTestId("student-leaves-page")).not.toBeInTheDocument();
  });
});
