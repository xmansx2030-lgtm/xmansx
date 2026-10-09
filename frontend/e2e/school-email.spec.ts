import { expect, test } from "@playwright/test";

// These UI journeys use page.route rather than a real authenticated session.
// A production NetworkOnly service worker owns subsequent API fetches, which
// Playwright cannot intercept. Keep it out of this mocked fixture only; the
// phase17 journeys still exercise the real service worker and offline isolation.
test.use({ serviceWorkers: "block" });

test("school registration and teacher first login require email, then show verification", async ({ page }, testInfo) => {
  await page.addInitScript(() => localStorage.setItem("pwa-install-dismissed-until", String(Date.now() + 86_400_000)));
  const school = { id: 20, name: "مدرسة البريد التجريبية", slug: "email-school", school_type: "BOYS" };
  const base = { id: 20, mobile: "+966551234567", name: "مدير المدرسة", is_platform_admin: false,
    active_school: school, roles: ["SCHOOL_MANAGER"], capabilities: [], has_parent_portal: false,
    memberships: [{ id: 1, school, roles: ["SCHOOL_MANAGER"], status: "ACTIVE" }], invitations: [],
    must_change_password: false, requires_initial_email: false, school_recovery_email_enabled: true };
  let me: typeof base | null = null;
  let registrations = 0;
  let passwordChanges = 0;
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname.replace("/api/v1", "");
    let body: unknown;
    let status = 200;
    if (path === "/auth/me/") {
      status = me ? 200 : 401;
      body = me ?? { code: "NOT_AUTHENTICATED", message: "سجل الدخول" };
    } else if (path === "/auth/csrf/") {
      body = { detail: "ok" };
    } else if (path === "/auth/registration/plans/") {
      body = [{ id: 1, name: "باقة المدرسة", price_amount: "990", currency: "SAR",
        trial_days: 21, can_self_register: true, duration_value: 1, duration_unit: "YEARS" }];
    } else if (path === "/auth/register-school/") {
      expect(route.request().postDataJSON().manager_email).toBe("manager@school.invalid");
      registrations += 1;
      me = { ...base };
      body = me;
      status = 201;
    } else if (path === "/auth/change-initial-password/") {
      expect(route.request().postDataJSON().email).toBe("teacher@school.invalid");
      passwordChanges += 1;
      me = { ...base, id: 21, roles: ["TEACHER"], name: "المعلم" };
      body = me;
    } else if (path === "/parent/recovery-email/") {
      body = { verified: false, verification_required: true, email_masked: "",
        pending_email_masked: "m***@s***", enabled: true, delivery_status: "SUBMITTED_TO_PROVIDER" };
    } else {
      throw new Error(`Unexpected endpoint: ${path}`);
    }
    await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  });
  await page.goto("/register");
  await page.getByLabel("اسم المدرسة", { exact: true }).fill(school.name);
  await page.getByRole("button", { name: /متابعة إلى حساب المدير/ }).click();
  await page.getByLabel("اسم مدير المدرسة", { exact: true }).fill("مدير المدرسة");
  await page.getByLabel("رقم الجوال", { exact: true }).fill("0551234567");
  await page.getByLabel("كلمة المرور", { exact: true }).fill("School-Safe-2026!");
  await page.getByLabel("تأكيد كلمة المرور", { exact: true }).fill("School-Safe-2026!");
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: /إنشاء المدرسة وبدء التجربة/ }).click();
  await expect(page.getByRole("alert")).toContainText("أدخل بريدًا إلكترونيًا صحيحًا");
  expect(registrations).toBe(0);
  await page.getByLabel("البريد الإلكتروني للمدير", { exact: true }).fill("manager@school.invalid");
  await page.screenshot({ path: `../tmp/school-register-${testInfo.project.name}.png`, fullPage: true, scale: "css" });
  await page.getByRole("button", { name: /إنشاء المدرسة وبدء التجربة/ }).click();
  await expect(page).toHaveURL(/\/account\/recovery-email$/);
  await expect(page.getByText("ستصلك أيضاً تفاصيل اشتراك المدرسة وتنبيهاته إلى بريدك الموثق.")).toBeVisible();
  expect(registrations).toBe(1);

  me = { ...base, id: 21, name: "المعلم", roles: ["TEACHER"], must_change_password: true, requires_initial_email: true };
  await page.goto("/change-password");
  await page.getByLabel("كلمة المرور الحالية", { exact: true }).fill("0551234567");
  await page.getByLabel("كلمة المرور الجديدة", { exact: true }).fill("Teacher-Safe-2026!");
  await page.getByLabel("تأكيد كلمة المرور", { exact: true }).fill("Teacher-Safe-2026!");
  await page.getByRole("button", { name: "حفظ كلمة المرور", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("أدخل بريدًا إلكترونيًا صحيحًا");
  expect(passwordChanges).toBe(0);
  await page.getByLabel("البريد الإلكتروني", { exact: true }).fill("teacher@school.invalid");
  await page.evaluate(() => window.scrollTo(0, 0));
  await expect(page.getByRole("heading", { name: "تغيير كلمة المرور", exact: true })).toBeInViewport();
  expect(await page.locator("form").evaluate((form) => form.getBoundingClientRect().top)).toBeGreaterThanOrEqual(0);
  await page.getByRole("button", { name: "تسجيل الخروج", exact: true }).scrollIntoViewIfNeeded();
  await expect(page.getByRole("button", { name: "تسجيل الخروج", exact: true })).toBeInViewport();
  await page.screenshot({ path: `../tmp/school-first-login-${testInfo.project.name}.png`, fullPage: true, scale: "css" });
  await page.getByRole("button", { name: "حفظ كلمة المرور", exact: true }).click();
  await expect(page).toHaveURL(/\/account\/recovery-email$/);
  expect(passwordChanges).toBe(1);
  await expect(page.getByRole("button", { name: "مساحة العمل" })).toBeVisible();
  await expect(page.getByRole("link", { name: "الانتقال إلى أبنائي" })).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  expect(errors).toEqual([]);
});

test("old employee completes personal email, keeps work open pending verification, then loses the notice", async ({ page }, testInfo) => {
  await page.addInitScript(() => localStorage.setItem("pwa-install-dismissed-until", String(Date.now() + 86_400_000)));
  const school = { id: 30, name: "مدرسة الحسابات القديمة", slug: "old-email-school", school_type: "BOYS" };
  const originalPassword = "Unchanged-School-Password-2026!";
  let me = { id: 31, mobile: "+966551234568", name: "المعلم القديم", is_platform_admin: false,
    active_school: school, roles: ["TEACHER"], capabilities: [], has_parent_portal: false,
    memberships: [{ id: 31, school, roles: ["TEACHER"], status: "ACTIVE" }], invitations: [],
    must_change_password: false, requires_initial_email: false, school_recovery_email_enabled: true,
    school_email_completion_required: true, school_email_verification_pending: false };
  let loggedIn = false;
  let enrollments = 0;
  let emailStatus = { verified: false, verification_required: true, email_masked: "",
    pending_email_masked: "", enabled: true, delivery_status: null as string | null };
  const errors: string[] = [];
  const paths: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname.replace("/api/v1", "");
    paths.push(path);
    let body: unknown;
    let status = 200;
    if (path === "/auth/me/") {
      status = loggedIn ? 200 : 401;
      body = loggedIn ? me : { code: "NOT_AUTHENTICATED", message: "سجل الدخول" };
    } else if (path === "/auth/csrf/") {
      body = { detail: "ok" };
    } else if (path === "/auth/login/") {
      expect(route.request().postDataJSON().password).toBe(originalPassword);
      loggedIn = true;
      body = me;
    } else if (path === "/parent/recovery-email/") {
      if (route.request().method() === "POST") {
        expect(route.request().postDataJSON()).toEqual({ email: "personal@example.invalid", current_password: originalPassword });
        enrollments += 1;
        me = { ...me, school_email_completion_required: false, school_email_verification_pending: true };
        emailStatus = { ...emailStatus, pending_email_masked: "p***@e***", delivery_status: "SUBMITTED_TO_PROVIDER" };
      }
      body = emailStatus;
    } else if (path === "/parent/recovery-email/verify/check/") {
      body = { valid: true };
    } else if (path === "/parent/recovery-email/verify/") {
      me = { ...me, school_email_verification_pending: false };
      emailStatus = { ...emailStatus, verified: true, verification_required: false,
        email_masked: "p***@e***", pending_email_masked: "" };
      body = emailStatus;
    } else if (path === "/attendance/current-period/") {
      body = { period: null };
    } else if (["/attendance/sections/", "/attendance/sessions/pending/", "/teacher/follow-up-requests/"].includes(path)) {
      body = [];
    } else if (path === "/referrals/mine/") {
      body = { count: 0, results: [] };
    } else {
      throw new Error(`Unexpected old-account endpoint: ${path}`);
    }
    await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  });
  await page.goto("/login");
  await page.getByLabel("رقم الجوال", { exact: true }).fill("0551234568");
  await page.getByLabel("كلمة المرور", { exact: true }).fill(originalPassword);
  await page.getByRole("button", { name: "تسجيل الدخول", exact: true }).click();
  await expect(page).toHaveURL(/\/account\/complete-email$/);
  await expect(page.getByRole("heading", { name: "إكمال البريد الإلكتروني" })).toBeVisible();
  await expect(page.getByLabel("كلمة المرور الجديدة", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "مساحة العمل" })).toHaveCount(0);
  await page.getByRole("button", { name: "إرسال رابط توثيق البريد" }).click();
  await expect(page.getByText("البريد الإلكتروني مطلوب.", { exact: true })).toBeVisible();
  expect(enrollments).toBe(0);
  await page.getByLabel("البريد الإلكتروني", { exact: true }).fill("personal@example.invalid");
  await page.getByLabel("كلمة المرور الحالية", { exact: true }).fill(originalPassword);
  await page.evaluate(() => window.scrollTo(0, 0));
  await expect(page.getByRole("heading", { name: "إكمال البريد الإلكتروني" })).toBeInViewport();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: `../tmp/school-old-email-${testInfo.project.name}.png`, fullPage: true, scale: "css" });
  await page.getByRole("button", { name: "إرسال رابط توثيق البريد" }).click();
  await expect(page).toHaveURL(/\/workspace$/);
  await expect(page.getByTestId("teacher-workspace-header")).toBeVisible();
  await expect(page.getByText("بانتظار توثيق بريدك الإلكتروني", { exact: true })).toBeVisible();
  await page.screenshot({ path: `../tmp/school-old-email-pending-${testInfo.project.name}.png`, fullPage: true, scale: "css" });
  await page.goto(`/parent/verify-email#token=${"onboarding-token-".repeat(4)}`);
  await page.getByRole("button", { name: "توثيق البريد الإلكتروني" }).click();
  await expect(page.getByText("تم توثيق بريد الاسترداد", { exact: true })).toBeVisible();
  await page.getByRole("link", { name: "الانتقال إلى مساحة العمل" }).click();
  await expect(page.getByTestId("teacher-workspace-header")).toBeVisible();
  await expect(page.getByText("بانتظار توثيق بريدك الإلكتروني", { exact: true })).toHaveCount(0);
  await page.goto("/login");
  await expect(page).toHaveURL(/\/workspace$/);
  expect(enrollments).toBe(1);
  expect(paths).not.toContain("/auth/change-initial-password/");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  expect(errors).toEqual([]);
});
