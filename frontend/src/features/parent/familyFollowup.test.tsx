import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { queryClient } from "@/app/queryClient";
import type { CorrectionRequest, ExcuseRequest } from "@/features/parent/api";
import { buildMe, membership, mockApi } from "@/test/mockApi";
import { renderApp } from "@/test/renderApp";

const correction: CorrectionRequest = {
  type: "CORRECTION", id: 901, student_id: 5, student_name: "أحمد محمد",
  requester_name: "محمد ولي الأمر", session_id: 55, attendance_date: "2026-10-08",
  period_sequence: 2, status: "PENDING", reason: "الطالب حضر الحصة",
  decision_note: "", created_at: "2026-10-08T05:00:00Z", updated_at: "2026-10-08T06:00:00Z",
  session_updated_at: "2026-10-08T06:00:00Z",
};
const excuse: ExcuseRequest = {
  type: "EXCUSE", id: 902, student_id: 5, student_name: "أحمد محمد",
  requester_name: "محمد ولي الأمر", status: "NEEDS_INFO", reason_type: "MEDICAL_REPORT",
  notes: "تقرير للمراجعة", targets: [
    { attendance_date: "2026-10-07", period_sequence: null },
    { attendance_date: "2026-10-08", period_sequence: 3 },
  ], decision_note: "أرفق توضيحاً", administrative_excuse_id: null,
  created_at: correction.created_at, updated_at: correction.updated_at,
  attachments: [{ id: 31, filename: "تقرير.pdf", mime_type: "application/pdf", size_bytes: 400 }],
};
function routes(role: "SCHOOL_MANAGER" | "VICE_PRINCIPAL", detail = correction) {
  return {
    "/auth/me/": { body: buildMe({ active_school: { id: 10, name: "مدرسة النور", slug: "noor" }, roles: [role], memberships: [membership(1, 10, "مدرسة النور", [role])] }) },
    "/staff/parents/requests/": { body: { count: 0, items: [], excuses: [], corrections: [], next: null, previous: null } },
    // The deep linked request intentionally is not in the visible first page.
    "/staff/parents/corrections/901/": { body: detail },
    "/staff/parents/excuses/902/": { body: excuse },
  };
}
describe("school family request decision context and dashboard deep links", () => {
  beforeEach(() => { queryClient.clear(); document.cookie = "csrftoken=test-token"; });

  it.each(["SCHOOL_MANAGER", "VICE_PRINCIPAL"] as const)("%s opens an older exact correction with all decision context", async (role) => {
    const { calls } = mockApi(routes(role));
    renderApp("/parent-management?tab=requests&type=CORRECTION&request=901");
    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByText("أحمد محمد")).toBeVisible();
    expect(within(dialog).getByText("محمد ولي الأمر")).toBeVisible();
    expect(within(dialog).getByText("2026-10-08")).toBeVisible();
    expect(within(dialog).getByText(/الحصة 2/)).toBeVisible();
    expect(within(dialog).getByText(/تصحح الغياب إلى حاضر/)).toBeVisible();
    expect(within(dialog).getByLabelText("سبب القرار ورد المدرسة")).toBeRequired();
    expect(calls.some(call => call.url.endsWith("/staff/parents/corrections/901/"))).toBe(true);
    expect(calls.some(call => call.init?.method === "POST")).toBe(false);
  });

  it("shows every excuse target, its reason, prior reply and authorized attachment", async () => {
    mockApi(routes("VICE_PRINCIPAL"));
    renderApp("/parent-management?tab=requests&type=EXCUSE&request=902");
    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByText("تقرير للمراجعة")).toBeVisible();
    expect(within(dialog).getByText("2026-10-07")).toBeVisible();
    expect(within(dialog).getByText(/اليوم الدراسي كاملاً/)).toBeVisible();
    expect(within(dialog).getByText(/الحصة 3/)).toBeVisible();
    expect(within(dialog).getByText("أرفق توضيحاً")).toBeVisible();
    expect(within(dialog).getByRole("link", { name: "تقرير.pdf" })).toHaveAttribute("href", "/api/v1/staff/parents/excuses/902/attachments/31/download/");
  });

  it.each(["APPROVED", "REJECTED", "CANCELLED"] as const)("%s requests are readable with no decision form", async (status) => {
    mockApi(routes("SCHOOL_MANAGER", { ...correction, status, decision_note: "قرار سابق محفوظ", reviewer_name: "وكيل المدرسة", reviewed_at: correction.updated_at }));
    renderApp("/parent-management?tab=requests&type=CORRECTION&request=901");
    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByText("قرار سابق محفوظ")).toBeVisible();
    expect(within(dialog).getByText("وكيل المدرسة")).toBeVisible();
    expect(within(dialog).queryByLabelText("قرار الطلب")).toBeNull();
    expect(within(dialog).queryByRole("button", { name: "حفظ قرار الطلب" })).toBeNull();
    expect(within(dialog).getByText(/لا يمكن إصدار قرار جديد/)).toBeVisible();
  });

  it("rechecks a foreign detail and never displays stale first-page data or decision controls", async () => {
    const { calls } = mockApi({ ...routes("VICE_PRINCIPAL"), "/staff/parents/corrections/901/": { status: 404, body: { code: "NOT_FOUND", message: "المورد غير موجود", details: {} } } });
    renderApp("/parent-management?tab=requests&type=CORRECTION&request=901");
    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByText("المورد غير موجود")).toBeVisible();
    expect(within(dialog).queryByText("أحمد محمد")).toBeNull();
    expect(within(dialog).queryByRole("button", { name: "حفظ قرار الطلب" })).toBeNull();
    expect(calls.some(call => call.init?.method === "POST")).toBe(false);
  });

  it("submits the fresh attendance revision once and invalidates the daily queue", async () => {
    let decided = false;
    queryClient.setQueryData(["school", 10, "dashboard", "attention"], { total: 1 });
    const { calls } = mockApi({
      "/staff/parents/corrections/901/decision/": () => { decided = true; return { body: { ...correction, status: "REJECTED" } }; },
      ...routes("VICE_PRINCIPAL"),
      "/staff/parents/corrections/901/": () => ({ body: decided ? { ...correction, status: "REJECTED", decision_note: "القرار بعد التحقق" } : correction }),
    });
    renderApp("/parent-management?tab=requests&type=CORRECTION&request=901");
    const dialog = await screen.findByRole("dialog");
    const note = await within(dialog).findByLabelText("سبب القرار ورد المدرسة");
    fireEvent.change(within(dialog).getByLabelText("قرار الطلب"), { target: { value: "REJECTED" } });
    fireEvent.change(note, { target: { value: "القرار بعد التحقق" } });
    await userEvent.setup().click(within(dialog).getByRole("button", { name: "حفظ قرار الطلب" }));
    await waitFor(() => expect(calls.filter(call => call.init?.method === "POST")).toHaveLength(1));
    expect(JSON.parse(calls.find(call => call.init?.method === "POST")!.init!.body as string)).toMatchObject({ expected_updated_at: correction.session_updated_at, decision: "REJECTED" });
    await waitFor(() => expect(queryClient.getQueryState(["school", 10, "dashboard", "attention"])?.isInvalidated).toBe(true));
    await waitFor(() => expect(within(dialog).queryByRole("button", { name: "حفظ قرار الطلب" })).toBeNull());
  });
});
