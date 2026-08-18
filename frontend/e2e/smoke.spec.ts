import { expect, test } from "@playwright/test";

test("app loads in Arabic RTL and reaches the backend health endpoint", async ({ page }) => {
  await page.goto("/");

  // RTL + Arabic من index.html
  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
  await expect(page.locator("html")).toHaveAttribute("lang", "ar");

  // App shell
  await expect(
    page.getByRole("heading", { name: "منصة المواظبة والمتابعة الطلابية" }),
  ).toBeVisible();

  // الوصول الفعلي للـ backend عبر الـ proxy
  await expect(page.getByTestId("backend-status")).toContainText("متصل", { timeout: 15_000 });
});
