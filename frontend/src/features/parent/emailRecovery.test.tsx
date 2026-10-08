import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { queryClient } from "@/app/queryClient";
import {
  normalizeRecoveryEmail,
  RECOVERY_EMAIL_DESCRIPTION,
  RECOVERY_REQUEST_MESSAGE,
  recoveryEmailError,
  type RecoveryEmailStatus,
} from "@/features/parent/recoveryEmail";
import { parentKey } from "@/features/parent/api";
import { buildMe, membership, mockApi, UNAUTHENTICATED } from "@/test/mockApi";
import { renderApp } from "@/test/renderApp";
import { mockBrowserStorage } from "@/test/browserStorage";

const PARENT = buildMe({ id: 201, has_parent_portal: true, name: "ولي الأمر الصناعي" });
const STATUS: RecoveryEmailStatus = {
  verified: false,
  verification_required: true,
  email_masked: "",
  pending_email_masked: "",
  delivery_status: null,
  enabled: true,
};
const EMAIL_PATH = "/parent/recovery-email/";
const RESET_PATH = "/auth/parent-password-recovery/";
const REGISTRATION_PATH = "/parent/registration/11111111-1111-4111-8111-111111111111/";
const invalidToken = {
  status: 400,
  body: { code: "RECOVERY_TOKEN_EXPIRED", message: "رابط الاسترداد غير متاح. اطلب رابطاً حديثاً.", details: {} },
};

function fragment(path: string) {
  const token = "secret-test-token-".repeat(3);
  window.history.replaceState({}, "", `${path}#token=${token}`);
  return token;
}

function postCalls(calls: ReturnType<typeof mockApi>["calls"], path: string) {
  return calls.filter((call) => call.url.endsWith(path) && call.init?.method === "POST");
}

describe("verified recovery email and parent-only access", () => {
  beforeEach(() => {
    queryClient.clear();
    mockBrowserStorage();
    document.cookie = "csrftoken=test-token";
    window.history.replaceState({}, "", "/");
  });

  it("normalizes recovery addresses and rejects missing, malformed and oversized input", () => {
    expect(normalizeRecoveryEmail("  Parent@Example.invalid  ")).toBe("parent@example.invalid");
    expect(recoveryEmailError(" ")).toBe("البريد الإلكتروني مطلوب.");
    expect(recoveryEmailError("no-address")).toBe("صيغة البريد الإلكتروني غير صحيحة.");
    expect(recoveryEmailError("x".repeat(255) + "@example.invalid")).toBe("صيغة البريد الإلكتروني غير صحيحة.");
    expect(recoveryEmailError("parent@example.invalid")).toBe("");
  });

  it("requires recovery email before submitting school registration", async () => {
    const { calls } = mockApi({
      "/auth/me/": UNAUTHENTICATED,
      [REGISTRATION_PATH]: { body: { school_name: "مدرسة صناعية", school_id: 10, enabled: true } },
    });
    renderApp("/parent/register/11111111-1111-4111-8111-111111111111");
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("اسم ولي الأمر"), "ولي الأمر");
    await user.type(screen.getByLabelText("رقم الجوال"), "0551234567");
    await user.type(screen.getByLabelText("معرف الطالب المسجل لدى المدرسة"), "synthetic-student");
    const email = screen.getByLabelText("البريد الإلكتروني");
    expect(email).toBeRequired();
    expect(email).toHaveAttribute("type", "email");
    expect(screen.getByText(RECOVERY_EMAIL_DESCRIPTION)).toBeVisible();
    await user.click(screen.getByRole("button", { name: "تقديم طلب تسجيل" }));
    expect(await screen.findByText("البريد الإلكتروني مطلوب.")).toBeVisible();
    await user.type(email, "invalid-address");
    await user.click(screen.getByRole("button", { name: "تقديم طلب تسجيل" }));
    expect(await screen.findByText("صيغة البريد الإلكتروني غير صحيحة.")).toBeVisible();
    expect(postCalls(calls, REGISTRATION_PATH)).toHaveLength(0);
  });

  it("gates child data until email verification without disabling the staff workspace", async () => {
    const staffParent = buildMe({
      ...PARENT,
      active_school: { id: 10, name: "مدرسة صناعية", slug: "synthetic" },
      roles: ["TEACHER"],
      memberships: [membership(1, 10, "مدرسة صناعية", ["TEACHER"])],
    });
    const { calls } = mockApi({
      "/auth/me/": { body: staffParent },
      [EMAIL_PATH]: { body: STATUS },
      "/parent/children/": { body: { results: [{ student: { full_name: "بيانات محجوبة" } }] } },
    });
    renderApp("/parent");
    expect(await screen.findByText("بانتظار توثيق بريد الاسترداد")).toBeVisible();
    expect(screen.getByRole("button", { name: "مساحة العمل" })).toBeVisible();
    expect(screen.queryByTestId("parent-shell")).toBeNull();
    expect(screen.queryByText("بيانات محجوبة")).toBeNull();
    expect(calls.some((call) => call.url.includes("/parent/children/"))).toBe(false);
  });

  it("does not impose email enrollment on the staff school selector", async () => {
    const { calls } = mockApi({
      "/auth/me/": { body: buildMe({ ...PARENT, memberships: [membership(1, 10, "مدرسة صناعية", ["TEACHER"])] }) },
    });
    renderApp("/select-school");
    expect(await screen.findByText("مدرسة صناعية")).toBeVisible();
    expect(calls.some((call) => call.url.includes(EMAIL_PATH))).toBe(false);
  });

  it("preserves the same user's teacher draft and staff query data when parent email enrollment is pending", async () => {
    const staffKey = ["school", 10, "teacher-sessions"];
    const staffState = { items: [{ id: 55, status: "IN_PROGRESS" }] };
    const draftKey = "attendance-draft:v1:201:10:55";
    const draft = JSON.stringify({ version: 1, updatedAt: "2026-10-08T05:00:00Z", date: "2026-10-08", period: 1, expiresAt: Date.now() + 60_000, absentIds: [5] });
    queryClient.setQueryData(staffKey, staffState);
    window.localStorage.setItem(draftKey, draft);
    mockApi({
      "/auth/me/": { body: buildMe({ ...PARENT, memberships: [membership(1, 10, "مدرسة صناعية", ["TEACHER"])] }) },
      [EMAIL_PATH]: { body: STATUS },
    });
    renderApp("/parent");
    expect(await screen.findByText("بانتظار توثيق بريد الاسترداد")).toBeVisible();
    expect(queryClient.getQueryData(staffKey)).toEqual(staffState);
    expect(window.localStorage.getItem(draftKey)).toBe(draft);
    window.localStorage.removeItem(draftKey);
  });

  it("removes cached child data and leaves the parent shell when a poll detects withdrawn email verification", async () => {
    let withdrawn = false;
    const child = { relation_id: 11, school: { id: 10, name: "مدرسة صناعية" }, student: { id: 5, full_name: "الابن الصناعي", grade_name: "أول", section_name: "1" }, status: "ACTIVE", today: null };
    mockApi({
      "/auth/me/": { body: PARENT },
      [EMAIL_PATH]: () => ({ body: withdrawn ? STATUS : { ...STATUS, verified: true, verification_required: false, email_masked: "p***@example.invalid" } }),
      "/parent/children/": () => withdrawn ? { status: 403, body: { code: "EMAIL_VERIFICATION_REQUIRED", message: "أكمل توثيق بريد الاسترداد.", details: {} } } : { body: { results: [child] } },
    });
    renderApp("/parent");
    expect(await screen.findByRole("heading", { name: "الابن الصناعي" })).toBeVisible();
    withdrawn = true;
    await act(async () => { await queryClient.refetchQueries({ queryKey: parentKey(PARENT.id, "children") }); });
    expect(await screen.findByText("بانتظار توثيق بريد الاسترداد")).toBeVisible();
    expect(screen.queryByText("الابن الصناعي")).toBeNull();
    expect(screen.queryByTestId("parent-shell")).toBeNull();
    await waitFor(() => expect(queryClient.getQueryCache().findAll({ queryKey: parentKey(PARENT.id) })).toHaveLength(0));
  });

  it("withholds stale cached child data when the email status request fails", async () => {
    queryClient.setQueryData(parentKey(PARENT.id, "children", 1), { results: [{ student: { full_name: "بيانات حساسة مخزنة" } }] });
    const { calls } = mockApi({
      "/auth/me/": { body: PARENT },
      [EMAIL_PATH]: { status: 503, body: { code: "TEMPORARILY_UNAVAILABLE", message: "الخدمة غير متاحة حالياً.", details: {} } },
    });
    renderApp("/parent");
    expect(await screen.findByText("الخدمة غير متاحة حالياً.")).toBeVisible();
    expect(screen.queryByText("بيانات حساسة مخزنة")).toBeNull();
    expect(calls.some((call) => call.url.includes("/parent/children/"))).toBe(false);
    await waitFor(() => expect(queryClient.getQueryCache().findAll({ queryKey: parentKey(PARENT.id) })).toHaveLength(0));
  });

  it("shows pending delivery and requires an explicit resend", async () => {
    const pending = { ...STATUS, pending_email_masked: "p***@example.invalid", delivery_status: "UNKNOWN" };
    const { calls } = mockApi({
      "/auth/me/": { body: PARENT },
      [`${EMAIL_PATH}resend/`]: { body: { ...pending, delivery_status: "SUBMITTED_TO_PROVIDER" } },
      [EMAIL_PATH]: { body: pending },
    });
    renderApp("/parent/recovery-email");
    expect(await screen.findByText("نتيجة إرسال رسالة التحقق غير مؤكدة")).toBeVisible();
    expect(postCalls(calls, `${EMAIL_PATH}resend/`)).toHaveLength(0);
    await userEvent.setup().click(screen.getByRole("button", { name: "إعادة إرسال رابط التحقق" }));
    expect(await screen.findByText("قُبل طلب إرسال رسالة التحقق")).toBeVisible();
    expect(postCalls(calls, `${EMAIL_PATH}resend/`)).toHaveLength(1);
  });

  it("does not claim provider acceptance or offer another send while delivery is in progress", async () => {
    let sending = true;
    const { calls } = mockApi({
      "/auth/me/": { body: PARENT },
      [EMAIL_PATH]: () => ({ body: { ...STATUS, pending_email_masked: "p***@example.invalid", delivery_status: sending ? "SENDING" : "SUBMITTED_TO_PROVIDER" } }),
    });
    renderApp("/parent/recovery-email");
    expect(await screen.findByText("جارٍ إرسال رسالة التحقق")).toBeVisible();
    expect(screen.queryByText("قُبل طلب إرسال رسالة التحقق")).toBeNull();
    expect(screen.getByRole("button", { name: "إعادة إرسال رابط التحقق" })).toBeDisabled();
    expect(postCalls(calls, `${EMAIL_PATH}resend/`)).toHaveLength(0);
    sending = false;
    await userEvent.setup().click(screen.getByRole("button", { name: "تحديث حالة البريد" }));
    expect(await screen.findByText("قُبل طلب إرسال رسالة التحقق")).toBeVisible();
    expect(screen.getByRole("button", { name: "إعادة إرسال رابط التحقق" })).toBeEnabled();
    expect(postCalls(calls, `${EMAIL_PATH}resend/`)).toHaveLength(0);
  });

  it("reports a cancelled delivery accurately without treating it as provider acceptance", async () => {
    const { calls } = mockApi({
      "/auth/me/": { body: PARENT },
      [EMAIL_PATH]: { body: { ...STATUS, pending_email_masked: "p***@example.invalid", delivery_status: "CANCELLED" } },
    });
    renderApp("/parent/recovery-email");
    expect(await screen.findByText("أُلغيت محاولة إرسال رسالة التحقق")).toBeVisible();
    expect(screen.queryByText("قُبل طلب إرسال رسالة التحقق")).toBeNull();
    expect(screen.getByRole("button", { name: "إعادة إرسال رابط التحقق" })).toBeEnabled();
    expect(postCalls(calls, `${EMAIL_PATH}resend/`)).toHaveLength(0);
  });

  it("requires the current password to enroll a normalized recovery email", async () => {
    const { calls } = mockApi({
      "/auth/me/": { body: PARENT },
      [EMAIL_PATH]: (init) => ({ body: init?.method === "POST" ? { ...STATUS, pending_email_masked: "p***@example.invalid", delivery_status: "PENDING" } : STATUS }),
    });
    renderApp("/parent/recovery-email");
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("البريد الإلكتروني"), "Parent@Example.invalid");
    await user.click(screen.getByRole("button", { name: "إرسال رابط توثيق البريد" }));
    expect(await screen.findByText("أدخل كلمة المرور الحالية لإثبات ملكية حسابك.")).toBeVisible();
    expect(postCalls(calls, EMAIL_PATH)).toHaveLength(0);
    await user.type(screen.getByLabelText("كلمة المرور الحالية"), "Current-Password!");
    await user.click(screen.getByRole("button", { name: "إرسال رابط توثيق البريد" }));
    expect(await screen.findByText("رسالة التحقق بانتظار الإرسال")).toBeVisible();
    expect(JSON.parse(String(postCalls(calls, EMAIL_PATH)[0]?.init?.body))).toEqual({ email: "parent@example.invalid", current_password: "Current-Password!" });
    expect(screen.queryByLabelText("كلمة المرور الحالية")).toBeNull();
    expect(calls.some((call) => call.url.includes("/account/password/"))).toBe(false);
  });

  it("keeps an unavailable email service closed without creating another account", async () => {
    const { calls } = mockApi({
      "/auth/me/": { body: PARENT },
      [EMAIL_PATH]: { body: { ...STATUS, enabled: false } },
    });
    renderApp("/parent/recovery-email");
    expect(await screen.findByText("خدمة بريد الاسترداد غير متاحة حالياً")).toBeVisible();
    expect(screen.getByRole("button", { name: "إرسال رابط توثيق البريد" })).toBeDisabled();
    expect(postCalls(calls, EMAIL_PATH)).toHaveLength(0);
  });

  it("displays a server rejection without falsely marking the address as pending", async () => {
    mockApi({
      "/auth/me/": { body: PARENT },
      [EMAIL_PATH]: (init) => init?.method === "POST" ? { status: 403, body: { code: "RECOVERY_PROOF_REQUIRED", message: "تحقق من كلمة المرور الحالية للحساب.", details: {} } } : { body: STATUS },
    });
    renderApp("/parent/recovery-email");
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("البريد الإلكتروني"), "parent@example.invalid");
    await user.type(screen.getByLabelText("كلمة المرور الحالية"), "Wrong-Password!");
    await user.click(screen.getByRole("button", { name: "إرسال رابط توثيق البريد" }));
    expect(await screen.findByText("تحقق من كلمة المرور الحالية للحساب.")).toBeVisible();
    expect(screen.queryByText("رسالة التحقق بانتظار الإرسال")).toBeNull();
  });

  it.each(["enrollment", "resend"])("does not resurrect an old owner's recovery cache after a late %s response", async (operation) => {
    const other = buildMe({ ...PARENT, id: 202, name: "حساب آخر" });
    const oldPending = { ...STATUS, pending_email_masked: "o***@old.invalid", delivery_status: "PENDING" };
    let switched = false;
    function switchAccount() {
      switched = true;
      queryClient.clear();
      queryClient.setQueryData(["me"], other);
      return { body: oldPending };
    }
    mockApi({
      "/auth/me/": { body: PARENT },
      [`${EMAIL_PATH}resend/`]: switchAccount,
      [EMAIL_PATH]: (init) => init?.method === "POST" ? switchAccount() : { body: !switched && operation === "resend" ? oldPending : STATUS },
    });
    renderApp("/parent/recovery-email");
    const user = userEvent.setup();
    if (operation === "enrollment") {
      await user.type(await screen.findByLabelText("البريد الإلكتروني"), "old@example.invalid");
      await user.type(screen.getByLabelText("كلمة المرور الحالية"), "Current-Password!");
      await user.click(screen.getByRole("button", { name: "إرسال رابط توثيق البريد" }));
    } else {
      await user.click(await screen.findByRole("button", { name: "إعادة إرسال رابط التحقق" }));
    }
    await waitFor(() => expect(queryClient.getQueryData(["me"])).toEqual(other));
    await waitFor(() => expect(queryClient.getQueryData(["parent-recovery-email", PARENT.id])).toBeUndefined());
    expect((queryClient.getQueryData(["parent-recovery-email", other.id]) as RecoveryEmailStatus | undefined)?.pending_email_masked).not.toBe(oldPending.pending_email_masked);
  });

  it("removes a verification secret from the URL, stores no token, and requires explicit confirmation", async () => {
    const token = fragment("/parent/verify-email");
    const storage = vi.spyOn(window.localStorage, "setItem");
    const { calls } = mockApi({
      "/auth/me/": { body: PARENT },
      [`${EMAIL_PATH}verify/check/`]: { body: { status: "VALID" } },
      [`${EMAIL_PATH}verify/`]: { body: { ...STATUS, verified: true, verification_required: false, email_masked: "p***@example.invalid" } },
    });
    renderApp("/parent/verify-email");
    const button = await screen.findByRole("button", { name: "توثيق البريد الإلكتروني" });
    expect(window.location.hash).toBe("");
    expect(document.querySelector('meta[name="referrer"]')).toHaveAttribute("content", "no-referrer");
    expect(postCalls(calls, `${EMAIL_PATH}verify/`)).toHaveLength(0);
    expect(JSON.parse(String(postCalls(calls, `${EMAIL_PATH}verify/check/`)[0]?.init?.body))).toEqual({ token });
    expect(calls.some((call) => call.url.includes(token))).toBe(false);
    expect(JSON.stringify(queryClient.getQueryCache().getAll())).not.toContain(token);
    expect(storage).not.toHaveBeenCalled();
    await userEvent.setup().click(button);
    expect(await screen.findByText("تم توثيق بريد الاسترداد")).toBeVisible();
    expect(postCalls(calls, `${EMAIL_PATH}verify/`)).toHaveLength(1);
    expect(screen.getByRole("link", { name: "الانتقال إلى أبنائي" })).toHaveAttribute("href", "/parent");
    storage.mockRestore();
  });

  it("preserves staff state and a teacher draft when email verification completes for the same account", async () => {
    fragment("/parent/verify-email");
    const staffKey = ["school", 10, "teacher-sessions"];
    const staffState = { items: [{ id: 55, status: "IN_PROGRESS" }] };
    const draftKey = "attendance-draft:v1:201:10:55";
    queryClient.setQueryData(staffKey, staffState);
    window.localStorage.setItem(draftKey, "synthetic teacher draft");
    mockApi({
      "/auth/me/": { body: PARENT },
      [`${EMAIL_PATH}verify/check/`]: { body: { status: "VALID" } },
      [`${EMAIL_PATH}verify/`]: { body: { ...STATUS, verified: true, verification_required: false, email_masked: "p***@example.invalid" } },
    });
    renderApp("/parent/verify-email");
    await userEvent.setup().click(await screen.findByRole("button", { name: "توثيق البريد الإلكتروني" }));
    expect(await screen.findByText("تم توثيق بريد الاسترداد")).toBeVisible();
    expect(queryClient.getQueryData(staffKey)).toEqual(staffState);
    expect(window.localStorage.getItem(draftKey)).toBe("synthetic teacher draft");
    expect(queryClient.getQueryData(["me"])).toEqual(PARENT);
  });

  it("asks an unauthenticated recipient to log in and reopen the original verification link", async () => {
    fragment("/parent/verify-email");
    const { calls } = mockApi({ "/auth/me/": UNAUTHENTICATED });
    renderApp("/parent/verify-email");
    expect(await screen.findByText("سجل الدخول إلى الحساب صاحب الطلب")).toBeVisible();
    expect(screen.getByRole("link", { name: "تسجيل الدخول" })).toHaveAttribute("href", "/login");
    expect(window.location.hash).toBe("");
    expect(calls.some((call) => call.url.includes("verify/check/"))).toBe(false);
  });

  it("does not consume another account's verification token or carry it into login when switching accounts", async () => {
    const token = fragment("/parent/verify-email");
    const storage = vi.spyOn(window.localStorage, "setItem");
    let signedOut = false;
    const { calls } = mockApi({
      "/auth/me/": () => signedOut ? UNAUTHENTICATED : { body: buildMe({ ...PARENT, id: 202, name: "حساب آخر" }) },
      "/auth/logout/": () => { signedOut = true; return { body: { detail: "تم تسجيل الخروج" } }; },
      [`${EMAIL_PATH}verify/check/`]: { status: 400, body: { code: "RECOVERY_TOKEN_INVALID", message: "رابط الاسترداد غير صالح أو انتهت صلاحيته. اطلب رابطاً جديداً.", details: {} } },
    });
    renderApp("/parent/verify-email");
    expect(await screen.findByText("رابط الاسترداد غير صالح أو انتهت صلاحيته. اطلب رابطاً جديداً.")).toBeVisible();
    expect(screen.queryByRole("button", { name: "توثيق البريد الإلكتروني" })).toBeNull();
    expect(postCalls(calls, `${EMAIL_PATH}verify/`)).toHaveLength(0);
    expect(calls.some((call) => call.url.includes("/parent/children/"))).toBe(false);
    expect(window.location.hash).toBe("");
    expect(window.location.search).not.toContain(token);
    await userEvent.setup().click(screen.getByRole("button", { name: "تسجيل الخروج لاستخدام الحساب صاحب الطلب" }));
    expect(await screen.findByLabelText("رقم الجوال")).toBeVisible();
    expect(calls.some((call) => call.url.includes(token))).toBe(false);
    expect(screen.queryByRole("link", { name: /token=/ })).toBeNull();
    expect(storage).not.toHaveBeenCalled();
    storage.mockRestore();
  });

  it.each([
    ["/parent/verify-email", "افتح رابط التحقق الأصلي"],
    ["/reset-password", "افتح رابط الاستعادة الأصلي"],
  ])("shows a clear missing-link state at %s without issuing a token request", async (path, message) => {
    const { calls } = mockApi({ "/auth/me/": { body: PARENT } });
    renderApp(path);
    expect(await screen.findByText(message)).toBeVisible();
    expect(calls.some((call) => call.url.includes("/check/") || call.url.includes("/complete/") || call.url.endsWith(`${EMAIL_PATH}verify/`))).toBe(false);
    expect(screen.queryByLabelText("كلمة المرور الجديدة")).toBeNull();
    expect(screen.queryByRole("button", { name: "توثيق البريد الإلكتروني" })).toBeNull();
  });

  it("does not offer confirmation for an expired or foreign verification token", async () => {
    fragment("/parent/verify-email");
    mockApi({ "/auth/me/": { body: PARENT }, [`${EMAIL_PATH}verify/check/`]: invalidToken });
    renderApp("/parent/verify-email");
    expect(await screen.findByText(invalidToken.body.message)).toBeVisible();
    expect(screen.queryByRole("button", { name: "توثيق البريد الإلكتروني" })).toBeNull();
  });

  it("requests password recovery with mobile alone and always shows the generic response", async () => {
    const { calls } = mockApi({ [RESET_PATH]: { status: 202, body: { message: "server response" } } });
    renderApp("/forgot-password");
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("رقم الجوال المسجل للدخول"), "٠٥٥١٢٣٤٥٦٧");
    expect(screen.queryByLabelText("البريد الإلكتروني")).toBeNull();
    await user.click(screen.getByRole("button", { name: "إرسال رابط الاستعادة" }));
    expect(await screen.findByText(RECOVERY_REQUEST_MESSAGE)).toBeVisible();
    expect(screen.queryByText("server response")).toBeNull();
    expect(JSON.parse(String(postCalls(calls, RESET_PATH)[0]?.init?.body))).toEqual({ mobile: "+966551234567" });
  });

  it("offers forgotten password from the existing mobile-and-password login", async () => {
    mockApi({ "/auth/me/": UNAUTHENTICATED });
    renderApp("/login");
    expect(await screen.findByRole("link", { name: "نسيت كلمة المرور؟" })).toHaveAttribute("href", "/forgot-password");
    expect(screen.getByLabelText("رقم الجوال")).toBeVisible();
    expect(screen.getByLabelText("كلمة المرور")).toBeVisible();
    expect(screen.queryByLabelText("البريد الإلكتروني")).toBeNull();
  });

  it("checks a reset token without creating a login session or resetting until the explicit submission", async () => {
    const token = fragment("/reset-password");
    const storage = vi.spyOn(window.localStorage, "setItem");
    const { calls } = mockApi({
      [`${RESET_PATH}check/`]: { body: { status: "VALID" } },
      [`${RESET_PATH}complete/`]: { body: { message: "تم تغيير كلمة المرور. سجل الدخول بكلمة المرور الجديدة." } },
    });
    renderApp("/reset-password");
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("كلمة المرور الجديدة"), "Next-Password-Safe!");
    await user.type(screen.getByLabelText("تأكيد كلمة المرور الجديدة"), "Next-Password-Safe!");
    expect(window.location.hash).toBe("");
    expect(postCalls(calls, `${RESET_PATH}complete/`)).toHaveLength(0);
    expect(calls.some((call) => call.url.includes(token))).toBe(false);
    expect(storage).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "حفظ كلمة المرور الجديدة" }));
    expect(await screen.findByText("تم تغيير كلمة المرور")).toBeVisible();
    expect(JSON.parse(String(postCalls(calls, `${RESET_PATH}complete/`)[0]?.init?.body))).toEqual({ token, new_password: "Next-Password-Safe!", confirm_password: "Next-Password-Safe!" });
    expect(screen.queryByLabelText("كلمة المرور الجديدة")).toBeNull();
    expect(calls.some((call) => call.url.includes("/auth/login/"))).toBe(false);
    expect(queryClient.getQueryData(["me"])).toBeUndefined();
    storage.mockRestore();
  });

  it("preserves an unrelated authenticated teacher's identity, state and draft during anonymous password recovery", async () => {
    fragment("/reset-password");
    const other = buildMe({ ...PARENT, id: 202, name: "المعلم صاحب الجلسة" });
    const staffKey = ["school", 10, "teacher-sessions"];
    const staffState = { items: [{ id: 55, status: "IN_PROGRESS" }] };
    const draftKey = "attendance-draft:v1:202:10:55";
    queryClient.setQueryData(["me"], other);
    queryClient.setQueryData(staffKey, staffState);
    window.localStorage.setItem(draftKey, "unrelated teacher draft");
    const { calls } = mockApi({
      "/auth/me/": { body: other },
      [`${RESET_PATH}check/`]: { body: { status: "VALID" } },
      [`${RESET_PATH}complete/`]: { body: { message: "تم تغيير كلمة المرور. سجل الدخول بكلمة المرور الجديدة." } },
    });
    renderApp("/reset-password");
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("كلمة المرور الجديدة"), "Next-Password-Safe!");
    await user.type(screen.getByLabelText("تأكيد كلمة المرور الجديدة"), "Next-Password-Safe!");
    await user.click(screen.getByRole("button", { name: "حفظ كلمة المرور الجديدة" }));
    expect(await screen.findByText("تم تغيير كلمة المرور")).toBeVisible();
    expect(queryClient.getQueryData(["me"])).toEqual(other);
    expect(queryClient.getQueryData(staffKey)).toEqual(staffState);
    expect(window.localStorage.getItem(draftKey)).toBe("unrelated teacher draft");
    expect(calls.some((call) => call.url.includes("/auth/login/"))).toBe(false);
  });

  it("clears an affected expired session and returns to login while retaining scoped teacher drafts", async () => {
    fragment("/reset-password");
    const draftKey = "attendance-draft:v1:201:10:55";
    queryClient.setQueryData(["me"], PARENT);
    queryClient.setQueryData(["school", 10, "teacher-sessions"], { items: [{ id: 55 }] });
    window.localStorage.setItem(draftKey, "scoped teacher draft");
    const { calls } = mockApi({
      "/auth/me/": UNAUTHENTICATED,
      [`${RESET_PATH}check/`]: { body: { status: "VALID" } },
      [`${RESET_PATH}complete/`]: { body: { message: "تم تغيير كلمة المرور. سجل الدخول بكلمة المرور الجديدة." } },
    });
    renderApp("/reset-password");
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("كلمة المرور الجديدة"), "Next-Password-Safe!");
    await user.type(screen.getByLabelText("تأكيد كلمة المرور الجديدة"), "Next-Password-Safe!");
    await user.click(screen.getByRole("button", { name: "حفظ كلمة المرور الجديدة" }));
    expect(await screen.findByLabelText("رقم الجوال")).toBeVisible();
    expect(screen.getByText("تم تغيير كلمة المرور")).toBeVisible();
    expect(queryClient.getQueryData(["me"])).toBeUndefined();
    expect(queryClient.getQueryData(["school", 10, "teacher-sessions"])).toBeUndefined();
    expect(window.localStorage.getItem(draftKey)).toBe("scoped teacher draft");
    expect(calls.some((call) => call.url.includes("/auth/login/"))).toBe(false);
  });

  it("does not restore an old session or clear a new account when the session recheck is cancelled by a login", async () => {
    fragment("/reset-password");
    const previous = buildMe({ ...PARENT, id: 202 });
    const current = buildMe({ ...PARENT, id: 203, name: "الحساب الجديد" });
    const staffKey = ["school", 30, "teacher-sessions"];
    const staffState = { items: [{ id: 77 }] };
    queryClient.setQueryData(["me"], previous);
    mockApi({
      "/auth/me/": () => {
        queryClient.clear();
        queryClient.setQueryData(["me"], current);
        queryClient.setQueryData(staffKey, staffState);
        return { body: previous };
      },
      [`${RESET_PATH}check/`]: { body: { status: "VALID" } },
      [`${RESET_PATH}complete/`]: { body: { message: "تم تغيير كلمة المرور. سجل الدخول بكلمة المرور الجديدة." } },
    });
    renderApp("/reset-password");
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("كلمة المرور الجديدة"), "Next-Password-Safe!");
    await user.type(screen.getByLabelText("تأكيد كلمة المرور الجديدة"), "Next-Password-Safe!");
    await user.click(screen.getByRole("button", { name: "حفظ كلمة المرور الجديدة" }));
    expect(await screen.findByText("تم تغيير كلمة المرور")).toBeVisible();
    expect(queryClient.getQueryData(["me"])).toEqual(current);
    expect(queryClient.getQueryData(staffKey)).toEqual(staffState);
  });

  it("rejects a password mismatch before submitting the reset token", async () => {
    fragment("/reset-password");
    const { calls } = mockApi({ [`${RESET_PATH}check/`]: { body: { status: "VALID" } } });
    renderApp("/reset-password");
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("كلمة المرور الجديدة"), "Next-Password-Safe!");
    await user.type(screen.getByLabelText("تأكيد كلمة المرور الجديدة"), "Different-Password!");
    await user.click(screen.getByRole("button", { name: "حفظ كلمة المرور الجديدة" }));
    expect(await screen.findByText("تأكيد كلمة المرور لا يطابق كلمة المرور الجديدة.")).toBeVisible();
    expect(postCalls(calls, `${RESET_PATH}complete/`)).toHaveLength(0);
  });

  it("does not offer password fields for an expired or replayed reset link", async () => {
    fragment("/reset-password");
    mockApi({ [`${RESET_PATH}check/`]: invalidToken });
    renderApp("/reset-password");
    expect(await screen.findByText(invalidToken.body.message)).toBeVisible();
    expect(screen.queryByLabelText("كلمة المرور الجديدة")).toBeNull();
  });

  it("does not report a successful password reset when the server rejects completion", async () => {
    fragment("/reset-password");
    mockApi({
      [`${RESET_PATH}check/`]: { body: { status: "VALID" } },
      [`${RESET_PATH}complete/`]: invalidToken,
    });
    renderApp("/reset-password");
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("كلمة المرور الجديدة"), "Next-Password-Safe!");
    await user.type(screen.getByLabelText("تأكيد كلمة المرور الجديدة"), "Next-Password-Safe!");
    await user.click(screen.getByRole("button", { name: "حفظ كلمة المرور الجديدة" }));
    expect(await screen.findByText(invalidToken.body.message)).toBeVisible();
    expect(screen.queryByText("تم تغيير كلمة المرور")).toBeNull();
    await waitFor(() => expect(screen.getByRole("button", { name: "حفظ كلمة المرور الجديدة" })).toBeEnabled());
  });
});
