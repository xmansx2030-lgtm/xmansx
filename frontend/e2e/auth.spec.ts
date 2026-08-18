/** E2E المصادقة والتعدد المدرسي — يتطلب backend يعمل مع بيانات seed_dev:
 *    python manage.py seed_dev --password <E2E_SEED_PASSWORD>
 *  أحمد المعلم 0550000001: ثانوية الأندلس (معلم) + مدارس الرواد (معلم+مرشد)
 *  فهد المرشد 0550000004: ثانوية المستقبل فقط
 */

import { expect, test, type APIRequest, type APIRequestContext } from "@playwright/test";

const PASSWORD = process.env.E2E_SEED_PASSWORD ?? "E2e-Dev-2026!pass";

async function apiLogin(
  requestFactory: APIRequest,
  mobile: string,
): Promise<APIRequestContext> {
  const ctx = await requestFactory.newContext({ baseURL: "http://localhost:5173" });
  await ctx.get("/api/v1/auth/csrf/");
  const token =
    (await ctx.storageState()).cookies.find((c) => c.name === "csrftoken")?.value ?? "";
  const response = await ctx.post("/api/v1/auth/login/", {
    data: { mobile, password: PASSWORD },
    headers: { "X-CSRFToken": token },
  });
  expect(response.status(), "seed login must succeed — run seed_dev first").toBe(200);
  return ctx;
}

async function csrfToken(ctx: APIRequestContext): Promise<string> {
  return (await ctx.storageState()).cookies.find((c) => c.name === "csrftoken")?.value ?? "";
}

test("teacher with two schools: selection, shell, switching, logout", async ({ page }) => {
  await page.goto("/");

  // Login
  await page.getByLabel("رقم الجوال").fill("0550000001");
  await page.getByLabel("كلمة المرور", { exact: true }).fill(PASSWORD);
  await page.getByRole("button", { name: "تسجيل الدخول" }).click();

  // شاشة اختيار المدرسة تظهر لأن لديه مدرستين
  await expect(page.getByRole("heading", { name: "اختر المدرسة" })).toBeVisible();
  await expect(page.getByText("ثانوية الأندلس")).toBeVisible();
  await expect(page.getByText("مدارس الرواد")).toBeVisible();

  // اختيار ثانوية الأندلس
  await page
    .locator("li", { hasText: "ثانوية الأندلس" })
    .getByRole("button", { name: "دخول" })
    .click();
  await expect(page.getByTestId("active-school-name")).toHaveText("ثانوية الأندلس");
  await expect(page.getByTestId("user-roles")).toHaveText("معلم");

  // التبديل إلى مدارس الرواد من الـ Switcher
  await page.getByRole("button", { name: /ثانوية الأندلس/ }).click();
  await page.getByRole("button", { name: /مدارس الرواد/ }).click();
  await expect(page.getByTestId("active-school-name")).toHaveText("مدارس الرواد");
  await expect(page.getByTestId("user-roles")).toContainText("المرشد الطلابي");

  // الخروج → العودة لشاشة الدخول
  await page.getByRole("button", { name: "تسجيل الخروج" }).click();
  await expect(page.getByRole("button", { name: "تسجيل الدخول" })).toBeVisible();
});

test("isolation: user cannot select a school he has no membership in", async ({ playwright }) => {
  // المعلم (عضو في الأندلس) نستخرج منه معرفها الحقيقي
  const teacherCtx = await apiLogin(playwright.request, "0550000001");
  const schools = (await (await teacherCtx.get("/api/v1/auth/schools/")).json()) as {
    memberships: { school: { id: number; name: string } }[];
  };
  const andalusId = schools.memberships.find((m) => m.school.name === "ثانوية الأندلس")?.school
    .id;
  expect(andalusId).toBeTruthy();
  await teacherCtx.dispose();

  // فهد عضو في ثانوية المستقبل فقط
  const outsiderCtx = await apiLogin(playwright.request, "0550000004");
  const myList = (await (await outsiderCtx.get("/api/v1/auth/schools/")).json()) as {
    memberships: { school: { name: string } }[];
  };
  expect(myList.memberships.map((m) => m.school.name)).not.toContain("ثانوية الأندلس");

  // محاولة التبديل إلى الأندلس عبر API مباشرة → مرفوضة
  const attempt = await outsiderCtx.post("/api/v1/session/active-school/", {
    data: { school_id: andalusId },
    headers: { "X-CSRFToken": await csrfToken(outsiderCtx) },
  });
  expect(attempt.status()).toBe(403);
  const body = (await attempt.json()) as { code: string };
  expect(body.code).toBe("INVALID_SCHOOL_MEMBERSHIP");

  // المدرسة النشطة لم تتغير (بقيت ثانوية المستقبل — اختيرت تلقائيًا لأنها الوحيدة)
  const me = (await (await outsiderCtx.get("/api/v1/auth/me/")).json()) as {
    active_school: { name: string } | null;
  };
  expect(me.active_school?.name).toBe("ثانوية المستقبل");
  await outsiderCtx.dispose();
});
