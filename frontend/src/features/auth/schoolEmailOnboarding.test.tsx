import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { queryClient } from "@/app/queryClient";
import { authenticatedDestination } from "@/features/auth/destination";
import { ME_QUERY_KEY } from "@/features/auth/useMe";
import { recoveryEmailKey, type RecoveryEmailStatus } from "@/features/parent/recoveryEmail";
import { mockBrowserStorage } from "@/test/browserStorage";
import { buildMe, membership, mockApi, UNAUTHENTICATED } from "@/test/mockApi";
import { renderApp } from "@/test/renderApp";
import type { Me, SchoolRole } from "@/types/auth";

const OLD = buildMe({
  id: 701, name: "المعلم القديم", roles: ["TEACHER"],
  active_school: { id: 10, name: "مدرسة الحسابات القديمة", slug: "old-school" },
  memberships: [membership(1, 10, "مدرسة الحسابات القديمة", ["TEACHER"])],
  school_recovery_email_enabled: true, school_email_completion_required: true,
  school_email_verification_pending: false,
});
const EMPTY: RecoveryEmailStatus = { verified: false, verification_required: true,
  email_masked: "", pending_email_masked: "", delivery_status: null, enabled: true };
const PENDING: RecoveryEmailStatus = { ...EMPTY, pending_email_masked: "p***@e***",
  delivery_status: "SUBMITTED_TO_PROVIDER" };
const COMPLETE = { ...OLD, school_email_completion_required: false, school_email_verification_pending: true };
const WORK = {
  "/attendance/current-period/": { body: { period: null } },
  "/attendance/sections/": { body: [] },
  "/attendance/sessions/pending/": { body: [] },
  "/teacher/follow-up-requests/": { body: [] },
  "/referrals/mine/": { body: { count: 0, results: [] } },
};

describe("old school account email completion", () => {
  beforeEach(() => {
    queryClient.clear();
    mockBrowserStorage();
    document.cookie = "csrftoken=test-token";
    window.history.replaceState({}, "", "/");
  });

  it.each<SchoolRole>(["TEACHER", "SCHOOL_MANAGER", "VICE_PRINCIPAL", "COUNSELOR", "GATE_GUARD"])(
    "asks an existing %s to complete email before opening a direct protected link", async (role) => {
      const { calls } = mockApi({ "/auth/me/": { body: { ...OLD, roles: [role] } },
        "/parent/recovery-email/": { body: EMPTY } });
      renderApp("/workspace");
      expect(await screen.findByRole("heading", { name: "إكمال البريد الإلكتروني" })).toBeVisible();
      expect(await screen.findByLabelText("كلمة المرور الحالية")).toBeRequired();
      expect(screen.queryByLabelText("كلمة المرور الجديدة")).toBeNull();
      expect(screen.queryByRole("button", { name: "مساحة العمل" })).toBeNull();
      expect(calls.some((call) => call.url.includes("/attendance/") || call.url.includes("/dashboard/"))).toBe(false);
    },
  );

  it("redirects next login to email completion and retains a safe parent return path", async () => {
    let loggedIn = false;
    mockApi({
      "/auth/me/": () => loggedIn ? { body: OLD } : UNAUTHENTICATED,
      "/auth/login/": () => { loggedIn = true; return { body: OLD }; },
      "/parent/recovery-email/": { body: EMPTY },
    });
    renderApp("/login?returnTo=%2Fparent");
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("رقم الجوال"), "0550000001");
    await user.type(screen.getByLabelText("كلمة المرور", { exact: true }), "Unchanged-Password-2026!");
    await user.click(screen.getByRole("button", { name: "تسجيل الدخول" }));
    expect(await screen.findByRole("heading", { name: "إكمال البريد الإلكتروني" })).toBeVisible();
    expect(authenticatedDestination(OLD, "/parent")).toBe("/account/complete-email?returnTo=%2Fparent");
    expect(authenticatedDestination(OLD, "https://evil.invalid")).toBe("/account/complete-email");
  });

  it("validates missing email and current password, then opens work while verification is pending", async () => {
    let me = OLD;
    const { calls } = mockApi({ ...WORK,
      "/auth/me/": () => ({ body: me }),
      "/parent/recovery-email/": (init) => {
        if (init?.method === "POST") { me = COMPLETE; return { body: PENDING }; }
        return { body: EMPTY };
      },
    });
    renderApp("/workspace");
    const user = userEvent.setup();
    const submit = await screen.findByRole("button", { name: "إرسال رابط توثيق البريد" });
    await user.click(submit);
    expect(screen.getByText("البريد الإلكتروني مطلوب.")).toBeVisible();
    await user.type(screen.getByLabelText("البريد الإلكتروني"), "personal@example.invalid");
    await user.click(submit);
    expect(screen.getByText("أدخل كلمة المرور الحالية لإثبات ملكية حسابك.")).toBeVisible();
    await user.type(screen.getByLabelText("كلمة المرور الحالية"), "Unchanged-Password-2026!");
    await user.click(submit);
    expect(await screen.findByText("بانتظار توثيق بريدك الإلكتروني")).toBeVisible();
    expect(await screen.findByTestId("teacher-workspace-header")).toBeVisible();
    const sent = calls.filter((call) => call.url.endsWith("/parent/recovery-email/") && call.init?.method === "POST");
    expect(sent).toHaveLength(1);
    expect(JSON.parse(String(sent[0]?.init?.body))).toEqual({ email: "personal@example.invalid", current_password: "Unchanged-Password-2026!" });
    expect(calls.some((call) => call.url.includes("/change-initial-password/"))).toBe(false);
  });

  it("keeps the completion form after rejected current-password proof", async () => {
    mockApi({ "/auth/me/": { body: OLD }, "/parent/recovery-email/": (init) => init?.method === "POST"
      ? { status: 403, body: { code: "RECOVERY_PROOF_REQUIRED", message: "كلمة المرور غير صحيحة.", details: {} } }
      : { body: EMPTY } });
    renderApp("/workspace");
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("البريد الإلكتروني"), "personal@example.invalid");
    await user.type(screen.getByLabelText("كلمة المرور الحالية"), "wrong-password");
    await user.click(screen.getByRole("button", { name: "إرسال رابط توثيق البريد" }));
    expect(await screen.findByText("كلمة المرور غير صحيحة.")).toBeVisible();
    expect(screen.getByRole("heading", { name: "إكمال البريد الإلكتروني" })).toBeVisible();
    expect(queryClient.getQueryData<Me>(ME_QUERY_KEY)?.school_email_completion_required).toBe(true);
  });

  it("refreshes stale completion metadata from an already pending owned status", async () => {
    mockApi({ ...WORK, "/auth/me/": { body: OLD }, "/parent/recovery-email/": { body: PENDING } });
    renderApp("/account/complete-email");
    expect(await screen.findByTestId("teacher-workspace-header")).toBeVisible();
    expect(screen.getByText("بانتظار توثيق بريدك الإلكتروني")).toBeVisible();
    expect(screen.queryByLabelText("البريد الإلكتروني")).toBeNull();
  });

  it("leaves work available and links failed pending delivery to resend settings", async () => {
    mockApi({ ...WORK, "/auth/me/": { body: COMPLETE },
      "/parent/recovery-email/": { body: { ...PENDING, delivery_status: "FAILED" } } });
    renderApp("/workspace");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("link", { name: "توثيق البريد وإعادة الإرسال" }));
    expect(await screen.findByText("تعذر إرسال رسالة التحقق")).toBeVisible();
    expect(screen.getByRole("button", { name: "إعادة إرسال رابط التحقق" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "مساحة العمل" })).toBeVisible();
  });

  it("removes the workspace notice immediately after explicit verification", async () => {
    const verified = { ...EMPTY, verified: true, verification_required: false, email_masked: "p***@e***" };
    mockApi({ ...WORK, "/auth/me/": { body: COMPLETE },
      "/parent/recovery-email/verify/check/": { body: { valid: true } },
      "/parent/recovery-email/verify/": { body: verified },
    });
    window.history.replaceState({}, "", `/parent/verify-email#token=${"onboarding-token-".repeat(4)}`);
    renderApp("/parent/verify-email");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "توثيق البريد الإلكتروني" }));
    await user.click(await screen.findByRole("link", { name: "الانتقال إلى مساحة العمل" }));
    expect(await screen.findByTestId("teacher-workspace-header")).toBeVisible();
    expect(screen.queryByText("بانتظار توثيق بريدك الإلكتروني")).toBeNull();
  });

  it("does not update a different account after a late enrollment response", async () => {
    mockApi({ "/auth/me/": { body: OLD }, "/parent/recovery-email/": { body: EMPTY } });
    const normalFetch = globalThis.fetch;
    let resolve!: (value: Response) => void;
    vi.stubGlobal("fetch", (input: RequestInfo | URL, init?: RequestInit) =>
      String(input).endsWith("/parent/recovery-email/") && init?.method === "POST"
        ? new Promise<Response>((done) => { resolve = done; }) : normalFetch(input, init));
    renderApp("/workspace");
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("البريد الإلكتروني"), "personal@example.invalid");
    await user.type(screen.getByLabelText("كلمة المرور الحالية"), "Unchanged-Password-2026!");
    await user.click(screen.getByRole("button", { name: "إرسال رابط توثيق البريد" }));
    await waitFor(() => expect(resolve).toBeTypeOf("function"));
    const another = { ...OLD, id: 702 };
    await act(async () => {
      queryClient.setQueryData(ME_QUERY_KEY, another);
      resolve(new Response(JSON.stringify(PENDING), { status: 200, headers: { "Content-Type": "application/json" } }));
    });
    await waitFor(() => expect(queryClient.getQueryData<Me>(ME_QUERY_KEY)).toEqual(another));
    expect(queryClient.getQueryData(recoveryEmailKey(702))).not.toEqual(PENDING);
  });

  it("keeps temporary-password and platform destinations ahead of school completion", () => {
    expect(authenticatedDestination({ ...OLD, must_change_password: true })).toBe("/change-password");
    expect(authenticatedDestination({ ...OLD, is_platform_admin: true })).toBe("/platform");
  });
});
