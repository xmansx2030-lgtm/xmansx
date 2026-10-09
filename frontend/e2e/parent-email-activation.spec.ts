import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { FRONTEND_URL } from "./compose";
import { securePost, syntheticRecoveryLink, RECOVERY_MESSAGE } from "./parent-email-mailbox";

interface ActivationFixture {
  mobile: string;
  email: string;
  student_id: number;
  student_name: string;
  identifier: string;
  school_id: number;
  registration_path: string;
  staff_mobile: string;
}
const fixture = JSON.parse(readFileSync(
  process.env.PARENT_E2E_FIXTURE ?? resolve("..", "artifacts", "parent-e2e-fixture.json"), "utf-8",
)) as { email_recovery: ActivationFixture[] };
const password = process.env.E2E_SEED_PASSWORD;
if (!password || fixture.email_recovery?.length !== 3) {
  throw new Error("Seed three fresh synthetic email owners before acceptance.");
}

const viewports = [
  { name: "desktop", width: 1366, height: 900 },
  { name: "tablet", width: 768, height: 1024 },
  { name: "mobile", width: 390, height: 844 },
] as const;

for (const [index, viewport] of viewports.entries()) {
  test(`school approval emails atomic activation and verification on ${viewport.name}`, async ({
    page, playwright,
  }) => {
    test.setTimeout(180_000);
    await page.setViewportSize(viewport);
    const owner = fixture.email_recovery[index]!;
    if (!owner.email.endsWith(".invalid")) throw new Error("Only synthetic recipients are allowed.");
    const name = `ولي التفعيل البريدي ${viewport.name}`;
    const pageErrors: string[] = [];
    page.on("pageerror", error => pageErrors.push(error.message));
    const staff = await playwright.request.newContext({
      baseURL: FRONTEND_URL, ignoreHTTPSErrors: false,
    });
    try {
      await staff.get("/api/v1/auth/csrf/");
      expect((await securePost(staff, "/auth/login/", {
        mobile: owner.staff_mobile, password,
      })).status()).toBe(200);
      await page.goto(owner.registration_path);
      await page.getByLabel("اسم ولي الأمر", { exact: true }).fill(name);
      await page.getByLabel("رقم الجوال", { exact: true }).fill(owner.mobile);
      await page.getByLabel("معرف الطالب المسجل لدى المدرسة").fill(owner.identifier);
      await page.getByLabel("البريد الإلكتروني", { exact: true }).fill(owner.email);
      await page.getByRole("button", { name: "تقديم طلب تسجيل", exact: true }).click();
      await expect(page.getByText("تم استلام طلبك، وستقوم المدرسة بمراجعته.", { exact: true })).toBeVisible();
      expect((await page.request.get("/api/v1/parent/children/")).status()).toBe(403);
      const registrations = await (await staff.get(
        "/api/v1/staff/parents/registrations/?status=PENDING",
      )).json() as { results: Array<{ id: number; name: string }> };
      const request = registrations.results.find(item => item.name === name);
      if (!request) throw new Error("School review must find its exact synthetic request.");
      const approved = await securePost(staff, `/staff/parents/registrations/${request.id}/decision/`, {
        decision: "APPROVE", student_id: owner.student_id, contact_bound: true,
        verification_note: "تحقق حضوري صناعي موثق من صاحب الصفة — دون إرسال خارجي",
        // Omission deliberately verifies the new EMAIL default.
      });
      expect(approved.status()).toBe(200);
      const decision = await approved.json() as { delivery_status: string; activation_url?: string };
      expect(decision.delivery_status).toBe("PENDING");
      expect(decision.activation_url).toBeUndefined();
      const activationLink = await syntheticRecoveryLink(owner.email, "PARENT_ACCOUNT_ACTIVATION");
      const token = new URLSearchParams(new URL(activationLink).hash.slice(1)).get("token");
      if (!token) throw new Error("The private activation message must carry its bearer.");
      const commits: string[] = [];
      page.on("request", item => {
        const url = new URL(item.url());
        expect(url.searchParams.has("token")).toBe(false);
        if (url.pathname === "/api/v1/parent/activation/" && item.method() === "POST") {
          commits.push("activate");
        }
      });
      await page.goto(activationLink);
      await expect(page.getByLabel("كلمة المرور الجديدة", { exact: true })).toBeVisible();
      expect(new URL(page.url()).hash).toBe("");
      expect(commits).toEqual([]);
      expect((await page.request.get("/api/v1/auth/me/")).status()).toBe(403);
      expect((await page.request.get("/api/v1/parent/children/")).status()).toBe(403);
      const metadata = await securePost(page.request, "/parent/activation/check/", { token });
      expect(metadata.status()).toBe(200);
      const state = await metadata.json() as { school_name: string; verifies_email: boolean };
      expect(state.verifies_email).toBe(true);
      await expect(page.getByText(state.school_name, { exact: true })).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await page.screenshot({ path: `../artifacts/parent-staging/activation-email-${viewport.name}.png`, fullPage: true });
      await page.getByLabel("كلمة المرور الجديدة", { exact: true }).fill(password!);
      await page.getByLabel("تأكيد كلمة المرور", { exact: true }).fill(password!);
      await page.getByRole("button", { name: "إنشاء الحساب وتفعيل العلاقة", exact: true }).click();
      await expect(page.getByRole("heading", { name: owner.student_name, exact: true })).toBeVisible();
      expect(commits).toEqual(["activate"]);
      const credential = await page.request.get("/api/v1/parent/recovery-email/");
      expect(credential.status()).toBe(200);
      expect((await credential.json()).verified).toBe(true);
      const children = await page.request.get("/api/v1/parent/children/");
      expect(children.status()).toBe(200);
      expect(children.headers()["cache-control"]).toContain("no-store");
      const before = await children.json() as {
        results: Array<{ status: string; student: { id: number }; school: { id: number } }>;
      };
      expect(before.results).toHaveLength(1);
      expect(before.results[0]).toMatchObject({
        status: "ACTIVE", student: { id: owner.student_id }, school: { id: owner.school_id },
      });
      const userId = (await (await page.request.get("/api/v1/auth/me/")).json()).id as number;
      expect((await securePost(page.request, "/parent/activation/", {
        token, new_password: password, confirm_password: password,
      })).status()).toBe(409);
      expect((await page.request.get("/api/v1/gate/student-leaves/")).status()).toBe(403);
      expect((await securePost(page.request, "/student-leaves/", {
        student_id: owner.student_id,
      })).status()).toBe(403);
      await page.getByRole("button", { name: "تسجيل الخروج", exact: true }).click();
      await page.getByRole("link", { name: "نسيت كلمة المرور؟", exact: true }).click();
      await page.getByLabel("رقم الجوال المسجل للدخول", { exact: true }).fill(owner.mobile);
      await page.getByRole("button", { name: "إرسال رابط الاستعادة", exact: true }).click();
      await expect(page.getByText(RECOVERY_MESSAGE, { exact: true })).toBeVisible();
      await page.goto(await syntheticRecoveryLink(owner.email, "PASSWORD_RESET"));
      const newPassword = `Atomic-Email-${viewport.name}-2026!`;
      await page.getByLabel("كلمة المرور الجديدة", { exact: true }).fill(newPassword);
      await page.getByLabel("تأكيد كلمة المرور الجديدة", { exact: true }).fill(newPassword);
      await page.getByRole("button", { name: "حفظ كلمة المرور الجديدة", exact: true }).click();
      await expect(page.getByText("تم تغيير كلمة المرور", { exact: true })).toBeVisible();
      expect((await page.request.get("/api/v1/auth/me/")).status()).toBe(403);
      expect((await securePost(page.request, "/auth/login/", {
        mobile: owner.mobile, password,
      })).status()).toBe(401);
      expect((await securePost(page.request, "/auth/login/", {
        mobile: owner.mobile, password: newPassword,
      })).status()).toBe(200);
      expect((await (await page.request.get("/api/v1/auth/me/")).json()).id).toBe(userId);
      expect(await (await page.request.get("/api/v1/parent/children/")).json()).toEqual(before);
      expect(pageErrors).toEqual([]);
    } finally { await staff.dispose(); }
  });
}
