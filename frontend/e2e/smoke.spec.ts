import { expect, test } from "@playwright/test";

test("app loads the Arabic RTL landing page with login access and backend reachable", async ({
  page,
  request,
}) => {
  await page.goto("/");

  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
  await expect(page.locator("html")).toHaveAttribute("lang", "ar");

  // الزائر يرى صفحة الهبوط ويمكنه الوصول إلى تسجيل الدخول المخصص.
  await expect(
    page.getByRole("heading", { name: /كل تفاصيل المواظبة/ }),
  ).toBeVisible();
  await page.getByRole("link", { name: "تسجيل الدخول" }).first().click();
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByLabel("رقم الجوال")).toBeVisible();

  // الـ backend يعمل عبر الـ proxy
  const health = await request.get("/api/v1/health/");
  expect(health.status()).toBe(200);
});
