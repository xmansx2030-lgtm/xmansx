import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { queryClient } from "@/app/queryClient";
import { FamilyInvitationBadge } from "@/features/parent/FamilyInvitationsTab";
import type { FamilyInvitation, SchoolFamily } from "@/features/parent/familyInvitations";
import { buildMe, membership, mockApi, UNAUTHENTICATED } from "@/test/mockApi";
import { renderApp } from "@/test/renderApp";

const FAMILY: SchoolFamily = {
  key: "family-one", name: "محمد ولي الأسرة", names: ["محمد ولي الأسرة"],
  mobile: "+966551900003", mobile_masked: "+96655****003", needs_review: false,
  child_count: 3, children: [1, 2, 3].map((id) => ({ id, name: `ابن صناعي ${id}`, revision: 4 })),
  invitation: null,
};
const INVITATION: FamilyInvitation = {
  id: "11111111-1111-4111-8111-111111111111", name: FAMILY.name,
  mobile_masked: FAMILY.mobile_masked, delivery_status: "SENT", lifecycle: "OPEN",
  created_at: "2026-10-09T08:00:00Z", expires_at: "2026-10-10T08:00:00Z",
  consumed_at: null, failure_code: "", student_ids: [1, 2, 3], partial: false,
};
const PARENT = buildMe({ id: 222, name: "ولي الأسرة", has_parent_portal: true });
function manager(role = "SCHOOL_MANAGER") {
  return buildMe({
    active_school: { id: 10, name: "مدرسة صناعية", slug: "synthetic" },
    roles: [role as "SCHOOL_MANAGER"],
    memberships: [membership(1, 10, "مدرسة صناعية", [role as "SCHOOL_MANAGER"])],
  });
}
function staffApi(role = "SCHOOL_MANAGER", rows = [FAMILY]) {
  return mockApi({
    "/auth/me/": { body: manager(role) },
    "/staff/parents/families/": (init) => ({
      body: init?.method === "POST" ? { invitations: [INVITATION] } : {
        count: rows.length, results: rows, next: null, previous: null,
        sms_enabled: true, sms_configured: true,
      },
    }),
  });
}
describe("reviewed school families and private invitation", () => {
  beforeEach(() => {
    queryClient.clear(); document.cookie = "csrftoken=test-token";
    window.history.replaceState({}, "", "/");
  });

  it.each([
    ["PENDING", "OPEN", "بانتظار الإرسال"],
    ["SENDING", "OPEN", "جارٍ إرسال الدعوة"],
    ["SENT", "OPEN", "دعوة مقبولة لدى مزود SMS"],
    ["FAILED", "OPEN", "فشل إرسال الدعوة"],
    ["UNKNOWN", "OPEN", "نتيجة الإرسال غير مؤكدة"],
    ["SENT", "ACTIVATED", "تم تفعيل الربط"],
    ["SENT", "EXPIRED", "انتهت الدعوة"],
    ["SENT", "REVOKED", "دعوة ملغاة"],
    ["SENT", "NEEDS_REVIEW", "تغيرت البيانات — تحتاج مراجعة"],
  ] as const)("distinguishes %s/%s using visible text", (delivery_status, lifecycle, label) => {
    render(<FamilyInvitationBadge invitation={{ ...INVITATION, delivery_status, lifecycle }} />);
    expect(screen.getByText(label)).toBeVisible();
  });

  it.each(["SCHOOL_MANAGER", "VICE_PRINCIPAL"])("%s reviews exact children before one SMS", async (role) => {
    const api = staffApi(role);
    renderApp("/parent-management?tab=families");
    await userEvent.click(await screen.findByRole("button", { name: `اعتماد وإرسال دعوة ${FAMILY.name}` }));
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByRole("button", { name: "اعتماد وإرسال 1 دعوة" })).toBeDisabled();
    fireEvent.click(within(dialog).getByLabelText("ابن صناعي 2"));
    fireEvent.change(within(dialog).getByLabelText("توثيق التحقق من صفة ولي الأمر والرقم والأبناء"), { target: { value: "تحقق حضوري مستقل من الأبناء المحددين" } });
    fireEvent.click(within(dialog).getByLabelText(/أؤكد أنني تحققت/));
    await userEvent.click(within(dialog).getByRole("button", { name: "اعتماد وإرسال 1 دعوة" }));
    await screen.findByText("تم حفظ اعتماد الدعوات");
    const sent = api.calls.filter((call) => call.url.includes("/staff/parents/families/") && call.init?.method === "POST");
    expect(sent).toHaveLength(1);
    const payload = JSON.parse(String(sent[0]!.init!.body)) as { invitations: Array<{ children: unknown[] }> };
    expect(payload.invitations).toHaveLength(1);
    expect(payload.invitations[0]!.children).toEqual([{ id: 1, revision: 4 }, { id: 3, revision: 4 }]);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("marks the invited family and explains partial grants", async () => {
    staffApi("VICE_PRINCIPAL", [{ ...FAMILY, invitation: { ...INVITATION, partial: true, student_ids: [1] } }]);
    renderApp("/parent-management?tab=families");
    expect(await screen.findByText("دعوة مقبولة لدى مزود SMS")).toBeVisible();
    expect(screen.getByText(/الدعوة السابقة لا تشمل كل الأبناء/)).toBeVisible();
    expect(screen.getByRole("button", { name: `مراجعة وإعادة دعوة ${FAMILY.name}` })).toBeEnabled();
  });

  it("searches across pages, clears selection, and restores the full list", async () => {
    const api = staffApi();
    renderApp("/parent-management?tab=families");
    await screen.findByRole("heading", { name: FAMILY.name });
    await userEvent.click(screen.getByLabelText(`اختيار ${FAMILY.name}`));
    expect(screen.getByRole("button", { name: "مراجعة وإرسال للمحدد (1)" })).toBeEnabled();
    const search = screen.getByRole("searchbox", { name: "البحث عن ولي الأمر" });
    fireEvent.change(search, { target: { value: "  ابن صناعي 3  " } });
    await waitFor(() => expect(api.calls.some(call => new URL(call.url, "http://localhost").searchParams.get("search") === "ابن صناعي 3")).toBe(true));
    await screen.findByText("1 أسرة مطابقة للبحث");
    expect(screen.getByText("ابن صناعي 1")).toBeVisible();
    expect(screen.getByRole("button", { name: "مراجعة وإرسال للمحدد (0)" })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "مسح البحث" }));
    expect(search).toHaveValue("");
    await screen.findByText("1 أسرة مقترحة");
  });

  it("explains empty search results and allows clearing the search", async () => {
    staffApi("SCHOOL_MANAGER", []);
    renderApp("/parent-management?tab=families");
    await screen.findByText("لا توجد أسر مقترحة");
    fireEvent.change(screen.getByRole("searchbox", { name: "البحث عن ولي الأمر" }), { target: { value: "غير موجود" } });
    await screen.findByText("لا توجد أسر مطابقة للبحث");
    await userEvent.click(screen.getByRole("button", { name: "مسح البحث" }));
    await screen.findByText("لا توجد أسر مقترحة");
  });

  it("requires a verified name for ambiguous contact groups", async () => {
    staffApi("SCHOOL_MANAGER", [{ ...FAMILY, name: "تحتاج مراجعة الأسماء", names: ["أحمد", "محمد"], needs_review: true }]);
    renderApp("/parent-management?tab=families");
    await userEvent.click(await screen.findByRole("button", { name: "اعتماد وإرسال دعوة تحتاج مراجعة الأسماء" }));
    expect(within(screen.getByRole("dialog")).getByLabelText("اسم ولي الأمر المعتمد")).toHaveValue("");
  });

  it("counselor cannot open the family invitation tab", async () => {
    const api = staffApi("COUNSELOR");
    renderApp("/parent-management?tab=families");
    await screen.findByRole("heading", { name: "إدارة أولياء الأمور" });
    expect(screen.queryByRole("button", { name: "الأسر والدعوات" })).not.toBeInTheDocument();
    expect(api.calls.some((call) => call.url.includes("/staff/parents/families/"))).toBe(false);
  });

  it("removes cached child cards after staff permission is withdrawn", async () => {
    let denied = false;
    mockApi({
      "/auth/me/": { body: manager() },
      "/staff/parents/families/": () => denied
        ? { status: 403, body: { code: "PERMISSION_DENIED", message: "سحبت صلاحية المراجعة", details: {} } }
        : { body: { count: 1, results: [FAMILY], next: null, previous: null, sms_enabled: true, sms_configured: true } },
    });
    renderApp("/parent-management?tab=families");
    await screen.findByRole("heading", { name: FAMILY.name });
    denied = true;
    await queryClient.invalidateQueries({ queryKey: ["school", 10, "parents", "families"] });
    await screen.findByText("سحبت صلاحية المراجعة");
    expect(screen.queryByRole("heading", { name: FAMILY.name })).not.toBeInTheDocument();
    expect(screen.queryByText("ابن صناعي 1")).not.toBeInTheDocument();
  });

  it("new invitation collects email only, never student identifiers", async () => {
    window.history.replaceState({}, "", "/parent/invitation#token=private-family-test-token");
    const api = mockApi({
      "/auth/me/": UNAUTHENTICATED, "/auth/csrf/": { body: {} },
      "/parent/family-invitation/check/": { body: { school_name: "مدرسة صناعية", children_count: 3, account_exists: false, requires_login: false, email_verified: false } },
      "/parent/family-invitation/activate/": { body: PARENT },
      "/parent/recovery-email/": { body: { verified: false, verification_required: true, email_masked: "", pending_email_masked: "f***@parent.invalid", delivery_status: "PENDING", enabled: true } },
    });
    renderApp("/parent/invitation");
    await screen.findByLabelText("البريد الإلكتروني");
    expect(window.location.hash).toBe("");
    expect(screen.queryByLabelText(/معرف الطالب/)).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("كلمة المرور الجديدة"), { target: { value: "New-Family-Password-2026!" } });
    fireEvent.change(screen.getByLabelText("تأكيد كلمة المرور الجديدة"), { target: { value: "New-Family-Password-2026!" } });
    await userEvent.click(screen.getByRole("button", { name: "تفعيل الربط والمتابعة" }));
    expect(screen.getByText("البريد الإلكتروني مطلوب.")).toBeVisible();
    expect(api.calls.some((call) => call.url.includes("/family-invitation/activate/"))).toBe(false);
    fireEvent.change(screen.getByLabelText("البريد الإلكتروني"), { target: { value: "family@parent.invalid" } });
    await userEvent.click(screen.getByRole("button", { name: "تفعيل الربط والمتابعة" }));
    await waitFor(() => expect(api.calls.filter((call) => call.url.includes("/family-invitation/activate/"))).toHaveLength(1));
  });
});
