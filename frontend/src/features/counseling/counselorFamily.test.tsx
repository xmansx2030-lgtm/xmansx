import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { queryClient } from "@/app/queryClient";
import { buildMe, membership, mockApi } from "@/test/mockApi";
import { renderApp } from "@/test/renderApp";

const studentCase = {
  id: 7, student_id: 5, student_name: "محمد أحمد", grade_name: "الأول", section_name: "2",
  status: "OPEN", status_label: "مفتوحة", referral_category_label: "المواظبة",
  referral_reason_label: "غياب متكرر", opened_at: "2026-10-09T08:00:00Z",
  counselor_name: "مرشد الاختبار", can_manage: true, snapshot_at_opening: {}, current_metrics: {},
  referral: { category_label: "المواظبة", reason_label: "غياب متكرر", description: "" },
};
const publication = {
  id: 19, student_id: 5, student_name: "محمد أحمد", case_id: 7,
  title: "تنظيم النوم", body: "نص مصرح للأسرة", required_action: "متابعة النوم",
  published_at: "2026-10-09T08:00:00Z", due_at: "2026-10-10T20:59:00Z",
  revoked_at: null, document: null, ack_count: 1, acknowledgements: [],
  action_count: 2, completed_action_count: 1, action_overdue: true,
  action_completed_at: "2026-10-09T09:00:00Z",
};
function me(role = "COUNSELOR") {
  return buildMe({ active_school: { id: 10, name: "مدرسة الاختبار", slug: "audit" },
    roles: [role] as Parameters<typeof membership>[3],
    memberships: [membership(1, 10, "مدرسة الاختبار", [role] as Parameters<typeof membership>[3])],
  });
}
describe("counselor family integration", () => {
  beforeEach(() => { queryClient.clear(); document.cookie = "csrftoken=test-token"; });
  it("publishes from the case with fixed student identity and refreshes its timeline", async () => {
    let published = false;
    const { calls } = mockApi({
      "/auth/me/": { body: me() },
      "/counselor/cases/7/timeline/": { body: [{ id: 1, event_type: "FAMILY_CONTENT_PUBLISHED", event_type_label: "نشر توصية للأسرة", metadata: { title: "تنظيم النوم" }, actor_name: "مرشد الاختبار", created_at: "2026-10-09T08:00:00Z" }] },
      "/counselor/cases/7/": { body: studentCase },
      "/staff/parents/publications/": (init) => {
        if (init?.method === "POST") { published = true; return { status: 201, body: publication }; }
        return { body: { count: published ? 1 : 0, items: published ? [publication] : [], next: null, previous: null } };
      },
    });
    renderApp("/counselor/cases/7?tab=family");
    expect(await screen.findByText("الأسرة المستهدفة: محمد أحمد")).toBeVisible();
    expect(screen.queryByLabelText("رقم سجل الطالب للنشر")).toBeNull();
    expect(screen.queryByLabelText("رقم الحالة الإرشادية المسندة")).toBeNull();
    expect(screen.queryByLabelText("رقم المستند المصرح (اختياري)")).toBeNull();
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("عنوان الرسالة للأسرة"), "تنظيم النوم");
    await user.type(screen.getByLabelText("المحتوى المصرح بنشره"), "نص مصرح للأسرة");
    await user.type(screen.getByLabelText("الإجراء المطلوب من الأسرة (اختياري)"), "متابعة النوم");
    await user.click(screen.getByRole("button", { name: "نشر المحتوى للأسرة" }));
    expect(await screen.findByText("تم نشر المحتوى داخل بوابة الأسرة")).toBeVisible();
    const posted = calls.find((call) => call.init?.method === "POST" && call.url.includes("/publications/"));
    const postedBody = JSON.parse(String(posted?.init?.body ?? "{}"));
    expect(postedBody).toMatchObject({ student_id: 5, case_id: 7, title: "تنظيم النوم", body: "نص مصرح للأسرة", required_action: "متابعة النوم" });
    expect(postedBody).not.toHaveProperty("document_id");
    expect(calls.some((call) => new URL(call.url, "https://app.example.test").searchParams.get("case_id") === "7")).toBe(true);
    expect(await screen.findByText("تأكيدات تنفيذ الإجراء: 1 من 2")).toBeVisible();
    expect(screen.getByText(/بانتظار تنفيذ الأسرة.*تجاوز الموعد/)).toBeVisible();
    await user.click(screen.getByRole("tab", { name: "الخط الزمني" }));
    expect(await screen.findByText("نشر توصية للأسرة")).toBeVisible();
    expect(within(screen.getByTestId("case-timeline")).getByText("تنظيم النوم")).toBeVisible();
  });
  it("shows the family history without a publishing form for a read-only case", async () => {
    mockApi({ "/auth/me/": { body: me("VICE_PRINCIPAL") },
      "/counselor/cases/7/": { body: { ...studentCase, can_manage: false } },
      "/staff/parents/publications/": { body: { items: [{ ...publication, revoked_at: "2026-10-09T09:00:00Z" }], count: 1 } },
    });
    renderApp("/counselor/cases/7?tab=family");
    expect(await screen.findByText("تنظيم النوم")).toBeVisible();
    expect(screen.queryByLabelText("عنوان الرسالة للأسرة")).toBeNull();
    expect(screen.getByText("مسحوب")).toBeVisible();
    expect(screen.queryByRole("button", { name: "سحب المحتوى المنشور" })).toBeNull();
  });
  it("keeps the administrative document field for managers", async () => {
    mockApi({ "/auth/me/": { body: me("SCHOOL_MANAGER") },
      "/staff/parents/publications/": { body: { items: [], count: 0 } },
    });
    renderApp("/parent-management?tab=publications");
    expect(await screen.findByLabelText("رقم المستند المصرح (اختياري)")).toBeVisible();
    expect(screen.getByLabelText("رقم سجل الطالب للنشر")).toBeVisible();
  });
  it("searches cases on the server and resets pagination before linking to the family tab", async () => {
    const { calls } = mockApi({ "/auth/me/": { body: me() },
      "/counselor/cases/": { body: { count: 30, next: "next", previous: null, results: [studentCase] } },
      "/staff/parents/publications/": { body: { items: [], count: 0 } },
    });
    renderApp("/parent-management");
    const input = await screen.findByLabelText("البحث باسم الطالب في حالاتي");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "التالي" }));
    await waitFor(() => expect(calls.some((call) => new URL(call.url, "https://app.example.test").searchParams.get("page") === "2")).toBe(true));
    await user.type(input, "محمد");
    await waitFor(() => expect(calls.some((call) => { const url = new URL(call.url, "https://app.example.test"); return url.searchParams.get("search") === "محمد" && url.searchParams.get("page") === "1"; })).toBe(true));
    expect(screen.getByRole("link", { name: /محمد أحمد.*فتح متابعة الأسرة/ })).toHaveAttribute("href", "/counselor/cases/7?tab=family");
    expect(screen.queryByLabelText("رقم الحالة الإرشادية المسندة")).toBeNull();
  });
});
