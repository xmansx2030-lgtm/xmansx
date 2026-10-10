import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import { queryClient } from "@/app/queryClient";
import { buildMe, membership, mockApi, UNAUTHENTICATED } from "@/test/mockApi";
import { renderApp } from "@/test/renderApp";
import type { SchoolRole } from "@/types/auth";

const SCHOOL = { id: 10, name: "ثانوية الأندلس", slug: "andalus" };
const account = (roles: SchoolRole[] = ["SCHOOL_MANAGER"], recovery = true) => buildMe({
  name: "أحمد عبدالله مدير المدرسة", active_school: SCHOOL, roles,
  memberships: [membership(1, 10, SCHOOL.name, roles)], school_recovery_email_enabled: recovery,
});
const postPassword = (calls: { url: string; init?: RequestInit }[]) => calls.filter(call => call.url.endsWith("/auth/change-password/") && call.init?.method === "POST");

describe("إدارة الحساب المدرسي", () => {
  beforeEach(() => { queryClient.clear(); document.cookie = "csrftoken=test-token"; });

  it.each<SchoolRole>(["SCHOOL_MANAGER", "VICE_PRINCIPAL", "COUNSELOR", "TEACHER", "GATE_GUARD"])("يتيح الحساب الشخصي للدور %s ويحافظ على صلاحية إعدادات المدرسة", async role => {
    mockApi({ "/auth/me/": { body: account([role]) } });
    renderApp("/account");
    const main = await screen.findByRole("main");
    expect(await within(main).findByRole("heading", { name: "إدارة الحساب", level: 1 })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "إدارة الحساب" })).toHaveAttribute("aria-current", "page");
    expect(within(main).getByRole("link", { name: "إدارة بريد الاسترداد" })).toHaveAttribute("href", "/account/recovery-email?returnTo=%2Faccount");
    expect(within(main).getByText("أحمد عبدالله مدير المدرسة")).toBeInTheDocument();
    const nav = screen.getByRole("navigation", { name: "التنقل الرئيسي" });
    if (role === "SCHOOL_MANAGER") expect(within(nav).getByRole("link", { name: "الإعدادات" })).toBeInTheDocument();
    else expect(within(nav).queryByRole("link", { name: "الإعدادات" })).not.toBeInTheDocument();
  });

  it("يبقى الحساب متاحًا دون تفعيل بريد الاسترداد ولا يطلب API البريد", async () => {
    const { calls } = mockApi({ "/auth/me/": { body: account(["TEACHER"], false) } });
    renderApp("/account");
    expect(await screen.findByRole("heading", { name: "إدارة الحساب", level: 1 })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "إدارة بريد الاسترداد" })).not.toBeInTheDocument();
    expect(calls.some(call => call.url.includes("/recovery-email/"))).toBe(false);
    expect(screen.getByLabelText("كلمة المرور الحالية")).toBeInTheDocument();
  });

  it("يتيح الحساب لصاحب تكليف صباحي دون أدوار إدارية", async () => {
    mockApi({ "/auth/me/": { body: { ...account([]), capabilities: ["MORNING_ATTENDANCE"] } } });
    renderApp("/account");
    expect(await screen.findByRole("heading", { name: "إدارة الحساب", level: 1 })).toBeInTheDocument();
    const nav = screen.getByRole("navigation", { name: "التنقل الرئيسي" });
    expect(within(nav).getByRole("link", { name: "التأخر الصباحي" })).toBeInTheDocument();
    expect(within(nav).queryByRole("link", { name: "الإعدادات" })).not.toBeInTheDocument();
  });

  it("يبقي تغيير الكلمة المؤقتة قبل الوصول إلى الحساب", async () => {
    mockApi({ "/auth/me/": { body: { ...account(), must_change_password: true } } });
    renderApp("/account");
    expect(await screen.findByText("يجب تغيير كلمة المرور المؤقتة قبل متابعة استخدام المنصة.")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "إدارة الحساب" })).not.toBeInTheDocument();
  });

  it("يبقي جمع بريد الحساب المطلوب قبل صفحة الحساب", async () => {
    mockApi({ "/auth/me/": { body: { ...account(), school_email_completion_required: true } },
      "/parent/recovery-email/": { body: { enabled: true, verified: false, verification_required: true, email_masked: "", pending_email_masked: "", delivery_status: null } } });
    renderApp("/account");
    expect(await screen.findByLabelText("البريد الإلكتروني")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "إدارة الحساب" })).not.toBeInTheDocument();
  });

  it("يفتح الحساب من قائمة الجوال ويغلق الدرج", async () => {
    mockApi({ "/auth/me/": { body: account() } });
    const user = userEvent.setup();
    renderApp("/workspace");
    await user.click(await screen.findByRole("button", { name: "فتح قائمة التنقل" }));
    const drawer = screen.getByRole("dialog", { name: "التنقل الرئيسي" });
    expect(within(drawer).getByTestId("user-name-mobile")).toHaveTextContent(account().name);
    await user.click(within(drawer).getByRole("link", { name: "إدارة الحساب" }));
    expect(await screen.findByRole("heading", { name: "إدارة الحساب", level: 1 })).toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "التنقل الرئيسي" })).not.toBeInTheDocument();
  });

  it("يتيح الرجوع إلى إدارة الحساب بعد فتح بريد الاسترداد", async () => {
    mockApi({ "/auth/me/": { body: account() }, "/parent/recovery-email/": { body: {
      enabled: true, verified: true, verification_required: false, email_masked: "a***@example.invalid", pending_email_masked: "", delivery_status: null,
    } } });
    const user = userEvent.setup();
    renderApp("/account");
    await user.click(await screen.findByRole("link", { name: "إدارة بريد الاسترداد" }));
    await user.click(await screen.findByRole("link", { name: "العودة إلى إدارة الحساب" }));
    expect(await screen.findByRole("heading", { name: "إدارة الحساب", level: 1 })).toBeInTheDocument();
  });

  it("يرفض التأكيد المختلف قبل إرسال الطلب، ثم يحفظ ويمسح الحقول", async () => {
    const { calls } = mockApi({ "/auth/me/": { body: account() }, "/auth/change-password/": { body: { detail: "تم تغيير كلمة المرور وإنهاء الجلسات الأخرى." } } });
    const user = userEvent.setup();
    renderApp("/account");
    await user.type(await screen.findByLabelText("كلمة المرور الحالية"), "Current-Password!");
    await user.type(screen.getByLabelText("كلمة المرور الجديدة"), "Next-Password-Safe!");
    await user.type(screen.getByLabelText("تأكيد كلمة المرور الجديدة"), "Different-Password!");
    await user.click(screen.getByRole("button", { name: "حفظ كلمة المرور" }));
    expect(await screen.findByText("تأكيد كلمة المرور غير مطابق.")).toBeInTheDocument();
    expect(postPassword(calls)).toHaveLength(0);
    await user.clear(screen.getByLabelText("تأكيد كلمة المرور الجديدة"));
    await user.type(screen.getByLabelText("تأكيد كلمة المرور الجديدة"), "Next-Password-Safe!");
    await user.click(screen.getByRole("button", { name: "حفظ كلمة المرور" }));
    expect(await screen.findByText("تم تغيير كلمة المرور وإنهاء الجلسات الأخرى.")).toBeInTheDocument();
    expect(JSON.parse(String(postPassword(calls)[0]?.init?.body))).toEqual({ current_password: "Current-Password!", new_password: "Next-Password-Safe!", confirm_password: "Next-Password-Safe!" });
    expect(screen.getByLabelText("كلمة المرور الحالية")).toHaveValue("");
    expect(screen.getByLabelText("كلمة المرور الجديدة")).toHaveValue("");
    expect(screen.getByLabelText("تأكيد كلمة المرور الجديدة")).toHaveValue("");
    expect(calls.some(call => call.url.includes("change-initial-password"))).toBe(false);
  });

  it("يعرض رفض الخادم دون نجاح وهمي ويتيح إعادة المحاولة", async () => {
    const { calls } = mockApi({ "/auth/me/": { body: account() }, "/auth/change-password/": { status: 400, body: { code: "INVALID_CURRENT_PASSWORD", message: "كلمة المرور الحالية غير صحيحة.", details: {} } } });
    const user = userEvent.setup();
    renderApp("/account");
    await user.type(await screen.findByLabelText("كلمة المرور الحالية"), "Wrong-Password!");
    await user.type(screen.getByLabelText("كلمة المرور الجديدة"), "Next-Password-Safe!");
    await user.type(screen.getByLabelText("تأكيد كلمة المرور الجديدة"), "Next-Password-Safe!");
    await user.click(screen.getByRole("button", { name: "حفظ كلمة المرور" }));
    expect(await screen.findByText("كلمة المرور الحالية غير صحيحة.")).toBeInTheDocument();
    expect(screen.queryByText("تم تغيير كلمة المرور وإنهاء الجلسات الأخرى.")).not.toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("button", { name: "حفظ كلمة المرور" })).toBeEnabled());
    expect(postPassword(calls)).toHaveLength(1);
  });

  it("يحمي المسار دون جلسة", async () => {
    mockApi({ "/auth/me/": UNAUTHENTICATED });
    renderApp("/account");
    expect(await screen.findByRole("button", { name: "تسجيل الدخول" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "إدارة الحساب" })).not.toBeInTheDocument();
  });
});
