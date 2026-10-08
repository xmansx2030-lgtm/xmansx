import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { FRONTEND_URL } from "./compose";
import {
  completeRecoveryEmail, LINK_UNAVAILABLE_MESSAGE, RECOVERY_MESSAGE,
  securePost, syntheticRecoveryLink,
} from "./parent-email-mailbox";

interface EmailFixture {
  mobile: string;
  email: string;
  student_id: number;
  student_name: string;
  identifier: string;
  school_id: number;
  registration_path: string;
  staff_mobile: string;
}
interface Children {
  results: Array<{ relation_id: number; status: string; student: { id: number }; school: { id: number } }>;
}

const fixture = JSON.parse(readFileSync(
  process.env.PARENT_E2E_FIXTURE ?? resolve("..", "artifacts", "parent-e2e-fixture.json"), "utf-8",
)) as { email_recovery: EmailFixture[] };
const seedPassword = process.env.E2E_SEED_PASSWORD;
if (!seedPassword || fixture.email_recovery?.length !== 3) {
  throw new Error("Seed the three fresh synthetic email recovery owners before browser acceptance.");
}

async function authenticate(context: APIRequestContext, mobile: string, password: string) {
  await context.get("/api/v1/auth/csrf/");
  expect((await securePost(context, "/auth/login/", { mobile, password })).status()).toBe(200);
}

async function loginOnPage(page: Page, mobile: string, password: string) {
  await page.goto("/login");
  await page.getByLabel("رقم الجوال", { exact: true }).fill(mobile);
  await page.getByLabel("كلمة المرور", { exact: true }).fill(password);
  const response = page.waitForResponse((item) =>
    item.url().endsWith("/api/v1/auth/login/") && item.request().method() === "POST",
  );
  await page.getByRole("button", { name: "تسجيل الدخول", exact: true }).click();
  return response;
}

const viewports = [
  { name: "desktop", width: 1366, height: 900 },
  { name: "tablet", width: 768, height: 1024 },
  { name: "mobile", width: 390, height: 844 },
] as const;

for (const [index, viewport] of viewports.entries()) {
  test(`verified recovery email lifecycle preserves the global account on ${viewport.name}`, async ({
    page, playwright,
  }) => {
    test.setTimeout(180_000);
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    const owner = fixture.email_recovery[index]!;
    if (!owner.email.endsWith(".invalid")) throw new Error("Email fixture must be synthetic.");
    const parentName = `ولي اختبار البريد ${viewport.name}`;
    const newPassword = `Str0ng-Recovery-${viewport.name}-2026`;
    const pageErrors: string[] = [];
    const secretRequests: string[] = [];
    page.on("pageerror", (error) => pageErrors.push(error.message));
    page.on("request", (request) => {
      const url = new URL(request.url());
      if (url.searchParams.has("token") || url.hash.includes("token=")) secretRequests.push(url.pathname);
    });
    const staff = await playwright.request.newContext({
      baseURL: FRONTEND_URL, ignoreHTTPSErrors: false,
    });
    const oldSession = await playwright.request.newContext({
      baseURL: FRONTEND_URL, ignoreHTTPSErrors: false,
    });
    try {
      await authenticate(staff, owner.staff_mobile, seedPassword!);
      await page.goto(owner.registration_path);
      await page.getByLabel("اسم ولي الأمر", { exact: true }).fill(parentName);
      await page.getByLabel("رقم الجوال", { exact: true }).fill(owner.mobile);
      await page.getByLabel("معرف الطالب المسجل لدى المدرسة").fill(owner.identifier);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
      const registrationPosts: string[] = [];
      const observeRegistration = (request: import("@playwright/test").Request) => {
        if (request.url().includes("/parent/registration/") && request.method() === "POST") registrationPosts.push("registration");
      };
      page.on("request", observeRegistration);
      await page.getByRole("button", { name: "تقديم طلب تسجيل", exact: true }).click();
      await expect(page.getByText("البريد الإلكتروني مطلوب.", { exact: true })).toBeVisible();
      expect(registrationPosts).toEqual([]);
      await page.screenshot({ path: `../artifacts/parent-staging/email-registration-${viewport.name}.png`, fullPage: true });
      await expect(page.getByText(owner.student_name, { exact: true })).toHaveCount(0);
      await page.getByLabel("البريد الإلكتروني", { exact: true }).fill(owner.email);
      await expect(page.getByText(
        "سيُستخدم هذا البريد لاستعادة كلمة المرور عند نسيانها، ولن تُرسل إليه إشعارات الطلاب أو الرسائل الإعلانية.",
        { exact: true },
      )).toBeVisible();
      await page.getByRole("button", { name: "تقديم طلب تسجيل", exact: true }).click();
      await expect(page.getByText("تم استلام طلبك، وستقوم المدرسة بمراجعته.", { exact: true })).toBeVisible();
      expect(registrationPosts).toEqual(["registration"]);
      page.off("request", observeRegistration);
      expect((await page.request.get("/api/v1/parent/children/")).status()).toBe(403);

      const pending = await (await staff.get("/api/v1/staff/parents/registrations/?status=PENDING")).json() as {
        results: Array<{ id: number; name: string; email?: string; email_masked?: string }>;
      };
      const registration = pending.results.find((item) => item.name === parentName);
      if (!registration) throw new Error("The synthetic registration must appear in its school's review queue.");
      expect(registration.email).toBeUndefined();
      const approval = await securePost(staff,
        `/staff/parents/registrations/${registration.id}/decision/`, {
          decision: "APPROVE", student_id: owner.student_id, delivery: "MANUAL",
          contact_bound: true,
          verification_note: "تحقق حضوري اصطناعي من الهوية والصفة؛ لا توجد رسائل SMS حقيقية",
        },
      );
      expect(approval.status()).toBe(200);
      const activationUrl = (await approval.json()).activation_url as string;
      await page.goto(activationUrl);
      await page.getByLabel("كلمة المرور الجديدة", { exact: true }).fill(seedPassword!);
      await page.getByLabel("تأكيد كلمة المرور", { exact: true }).fill(seedPassword!);
      await page.getByRole("button", { name: "إنشاء الحساب وتفعيل العلاقة", exact: true }).click();
      await expect(page.getByText("بانتظار توثيق بريد الاسترداد", { exact: true })).toBeVisible();
      await expect(page.getByText(owner.student_name, { exact: true })).toHaveCount(0);
      await page.screenshot({ path: `../artifacts/parent-staging/email-pending-${viewport.name}.png`, fullPage: true });
      expect((await page.request.get("/api/v1/parent/children/")).status()).toBe(403);
      const activated = await (await page.request.get("/api/v1/auth/me/")).json() as {
        id: number; memberships: unknown[];
      };
      expect(activated.memberships).toEqual([]);
      await completeRecoveryEmail(page, owner.mobile, seedPassword!, owner.email);
      await expect(page.getByRole("heading", { name: owner.student_name, exact: true })).toBeVisible();
      const childrenResponse = await page.request.get("/api/v1/parent/children/");
      expect(childrenResponse.status()).toBe(200);
      expect(childrenResponse.headers()["cache-control"]).toContain("no-store");
      const before = await childrenResponse.json() as Children;
      expect(before.results).toHaveLength(1);
      expect(before.results[0]?.student.id).toBe(owner.student_id);
      expect(before.results[0]?.school.id).toBe(owner.school_id);
      expect(before.results[0]?.status).toBe("ACTIVE");
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
      await authenticate(oldSession, owner.mobile, seedPassword!);
      expect((await oldSession.get("/api/v1/parent/children/")).status()).toBe(200);
      await page.getByRole("button", { name: "تسجيل الخروج", exact: true }).click();
      await expect(page.getByRole("heading", { name: "تسجيل الدخول", exact: true })).toBeVisible();
      expect((await page.request.get("/api/v1/parent/children/")).status()).toBe(403);
      await page.getByRole("link", { name: "نسيت كلمة المرور؟", exact: true }).click();
      await page.getByLabel("رقم الجوال المسجل للدخول", { exact: true }).fill(owner.mobile);
      await page.getByRole("button", { name: "إرسال رابط الاستعادة", exact: true }).click();
      await expect(page.getByText(RECOVERY_MESSAGE, { exact: true })).toBeVisible();
      await expect(page.getByText(owner.email, { exact: true })).toHaveCount(0);
      const resetLink = await syntheticRecoveryLink(owner.email, "PASSWORD_RESET");
      const resetToken = new URLSearchParams(new URL(resetLink).hash.slice(1)).get("token");
      if (!resetToken) throw new Error("A private synthetic reset token is required.");
      await page.goto(resetLink);
      await expect(page.getByLabel("كلمة المرور الجديدة", { exact: true })).toBeVisible();
      expect(new URL(page.url()).hash).toBe("");
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
      // Opening and checking a link never signs in or consumes it.
      expect((await page.request.get("/api/v1/auth/me/")).status()).toBe(403);
      expect((await oldSession.get("/api/v1/parent/children/")).status()).toBe(200);
      await page.getByLabel("كلمة المرور الجديدة", { exact: true }).fill(newPassword);
      await page.getByLabel("تأكيد كلمة المرور الجديدة", { exact: true }).fill(newPassword);
      await page.screenshot({ path: `../artifacts/parent-staging/email-reset-${viewport.name}.png`, fullPage: true });
      await page.getByRole("button", { name: "حفظ كلمة المرور الجديدة", exact: true }).click();
      await expect(page.getByText("تم تغيير كلمة المرور", { exact: true })).toBeVisible();
      expect((await page.request.get("/api/v1/auth/me/")).status()).toBe(403);
      expect((await oldSession.get("/api/v1/auth/me/")).status()).toBe(403);
      expect((await oldSession.get("/api/v1/parent/children/")).status()).toBe(403);

      expect((await loginOnPage(page, owner.mobile, seedPassword!)).status()).toBe(401);
      await expect(page.getByText("رقم الجوال أو كلمة المرور غير صحيحة.", { exact: true })).toBeVisible();
      expect((await loginOnPage(page, owner.mobile, newPassword)).status()).toBe(200);
      await expect(page.getByRole("heading", { name: owner.student_name, exact: true })).toBeVisible();
      const restored = await (await page.request.get("/api/v1/auth/me/")).json() as typeof activated;
      expect(restored.id).toBe(activated.id);
      expect(restored.memberships).toEqual(activated.memberships);
      const after = await (await page.request.get("/api/v1/parent/children/")).json() as Children;
      expect(after).toEqual(before);
      await page.goto(resetLink);
      await expect(page.getByText(LINK_UNAVAILABLE_MESSAGE, { exact: true })).toBeVisible();
      await expect(page.getByLabel("كلمة المرور الجديدة", { exact: true })).toHaveCount(0);
      expect((await securePost(page.request, "/auth/parent-password-recovery/complete/", {
        token: resetToken, new_password: `${newPassword}-replay`, confirm_password: `${newPassword}-replay`,
      })).status()).toBe(400);
      expect((await (await page.request.get("/api/v1/auth/me/")).json()).id).toBe(activated.id);
      expect((await page.request.get("/api/v1/gate/student-leaves/")).status()).toBe(403);
      expect((await securePost(page.request, "/student-leaves/", { student_id: owner.student_id })).status()).toBe(403);
      expect(secretRequests).toEqual([]);
      expect(pageErrors).toEqual([]);
    } finally { await staff.dispose(); await oldSession.dispose(); }
  });
}
