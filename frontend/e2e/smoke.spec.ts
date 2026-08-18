import { expect, test } from "@playwright/test";

test("app loads in Arabic RTL with login screen and backend reachable", async ({
  page,
  request,
}) => {
  await page.goto("/");

  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
  await expect(page.locator("html")).toHaveAttribute("lang", "ar");

  // غير مصادق → يعاد توجيهه لشاشة الدخول
  await expect(page.getByRole("heading", { name: "منصة المواظبة" })).toBeVisible();
  await expect(page.getByLabel("رقم الجوال")).toBeVisible();

  // الـ backend يعمل عبر الـ proxy
  const health = await request.get("/api/v1/health/");
  expect(health.status()).toBe(200);
});
