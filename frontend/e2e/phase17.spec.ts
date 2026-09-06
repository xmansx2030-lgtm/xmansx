import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test, type Page, type TestInfo } from "@playwright/test";

const PASSWORD = process.env.E2E_SEED_PASSWORD ?? "E2e-Dev-2026!pass";
const FIXTURES = resolve(dirname(fileURLToPath(import.meta.url)), "fixtures");

test.describe.configure({ mode: "serial", timeout: 180_000 });

interface Meta {
  phase17_section: string;
  phase17_students: string[];
}

function meta(): Meta {
  return JSON.parse(readFileSync(resolve(FIXTURES, "meta.json"), "utf-8")) as Meta;
}

async function login(page: Page, mobile: string, school?: string) {
  await page.goto("/login");
  await page.getByLabel("رقم الجوال").fill(mobile);
  await page.getByLabel("كلمة المرور", { exact: true }).fill(PASSWORD);
  await page.getByRole("button", { name: "تسجيل الدخول" }).click();
  if (school) {
    const chooser = page.locator("li", { hasText: school }).getByRole("button", { name: "دخول" });
    await chooser.click({ timeout: 5000 }).catch(() => undefined);
    await expect(page.getByTestId("active-school-name")).toHaveText(school);
  } else {
    await expect(page).not.toHaveURL(/\/login$/);
  }
}

async function logout(page: Page) {
  const desktop = page.getByRole("button", { name: "تسجيل الخروج" });
  if (await desktop.isVisible()) {
    await desktop.click();
  } else {
    await page.getByRole("button", { name: "فتح قائمة التنقل" }).click();
    await page.getByRole("button", { name: "خروج" }).click();
  }
  await expect(page.getByRole("button", { name: "تسجيل الدخول" })).toBeVisible();
}

async function assertNoPageOverflow(page: Page) {
  const dimensions = await page.evaluate(() => ({
    viewport: document.documentElement.clientWidth,
    content: document.documentElement.scrollWidth,
  }));
  expect(dimensions.content).toBeLessThanOrEqual(dimensions.viewport + 1);
}

async function screenshot(page: Page, testInfo: TestInfo, name: string) {
  await page.screenshot({ path: testInfo.outputPath(name), fullPage: true });
}

async function sectionId(page: Page, sectionName: string): Promise<number> {
  const id = await page.evaluate(async (name) => {
    const response = await fetch("/api/v1/attendance/sections/", { credentials: "include" });
    const sections = (await response.json()) as { id: number; name: string }[];
    return sections.find((section) => section.name === name)?.id ?? 0;
  }, sectionName);
  expect(id).toBeGreaterThan(0);
  return id;
}

test("production PWA manifest, headers, service worker, and SPA fallbacks", async ({ page, request }) => {
  const manifestResponse = await request.get("/manifest.webmanifest");
  expect(manifestResponse.status()).toBe(200);
  const manifest = (await manifestResponse.json()) as {
    name: string;
    lang: string;
    dir: string;
    display: string;
    icons: { sizes: string; purpose?: string }[];
  };
  expect(manifest.name).toBe("منصة المواظبة والمتابعة الطلابية");
  expect(manifest).toMatchObject({ lang: "ar", dir: "rtl", display: "standalone" });
  expect(manifest.icons.some((icon) => icon.sizes === "192x192")).toBe(true);
  expect(manifest.icons.some((icon) => icon.sizes === "512x512")).toBe(true);
  expect(manifest.icons.some((icon) => icon.purpose === "maskable")).toBe(true);

  for (const path of ["/dashboard", "/students/123/attendance", "/counselor", "/platform", "/subscription"]) {
    const response = await request.get(path);
    expect(response.status(), path).toBe(200);
    expect(response.headers()["content-security-policy"]).toContain("script-src 'self'");
    expect(response.headers()["permissions-policy"]).toContain("camera=(self)");
  }

  await page.goto("/");
  const registration = await page.evaluate(async () => {
    const ready = await navigator.serviceWorker.ready;
    return { scope: ready.scope, active: Boolean(ready.active) };
  });
  expect(registration.active).toBe(true);
  expect(registration.scope).toMatch(/\/$/);
});

test("teacher mobile attendance is responsive and logout cannot reopen cached data offline", async ({
  page,
  context,
}, testInfo) => {
  const m = meta();
  const consoleErrors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });

  await login(page, "0550000002", "ثانوية الأندلس");
  await page.goto("/students/import");
  await page.getByTestId("import-file-input").setInputFiles(resolve(FIXTURES, "noor-17.xlsx"));
  await page.getByRole("button", { name: "رفع الملف" }).click();
  await page.getByRole("button", { name: "بدء التحليل" }).click();
  await expect(page.getByRole("tab", { name: /جدد/ })).toBeVisible({ timeout: 30_000 });
  await page.getByRole("button", { name: "متابعة إلى التأكيد" }).click();
  await page.getByRole("button", { name: "اعتماد الاستيراد" }).click();
  await expect(page.getByTestId("import-result")).toBeVisible({ timeout: 30_000 });
  await logout(page);

  await page.setViewportSize({ width: 390, height: 844 });
  await login(page, "0550000001", "ثانوية الأندلس");
  consoleErrors.length = 0;
  const id = await sectionId(page, m.phase17_section);
  await page.goto(`/attendance/section/${id}`);
  const rows = page.locator('[data-testid^="roster-student-"]');
  await expect(rows).toHaveCount(3);
  await rows.nth(0).getByRole("button", { name: "غائب" }).click();
  await rows.nth(1).getByRole("button", { name: "متأخر" }).click();
  await page.getByTestId("submit-attendance").click();
  await expect(page.getByTestId("submitted-banner")).toBeVisible({ timeout: 20_000 });
  await assertNoPageOverflow(page);
  await screenshot(page, testInfo, "teacher-mobile.png");

  const cachedUrls = await page.evaluate(async () => {
    const urls: string[] = [];
    for (const name of await caches.keys()) {
      const cache = await caches.open(name);
      urls.push(...(await cache.keys()).map((request) => request.url));
    }
    return urls;
  });
  expect(cachedUrls.some((url) => new URL(url).pathname.startsWith("/api/"))).toBe(false);
  expect(consoleErrors).toEqual([]);

  await logout(page);
  await context.setOffline(true);
  await page.goto(`/attendance/section/${id}`);
  for (const student of m.phase17_students) {
    await expect(page.getByText(student)).not.toBeVisible();
  }
  await expect(page.getByText(/تعذر الاتصال|حدث خطأ/)).toBeVisible();
  await context.setOffline(false);
});

test("rapid school switching has no stale tenant flash", async ({ page }) => {
  const m = meta();
  await login(page, "0550000001", "ثانوية الأندلس");
  await page.goto("/");
  await page.getByRole("button", { name: /ثانوية الأندلس/ }).click();
  await page.getByRole("button", { name: /مدارس الرواد/ }).click();
  await expect(page.getByTestId("active-school-name")).toHaveText("مدارس الرواد");
  for (const student of m.phase17_students) await expect(page.getByText(student)).not.toBeVisible();

  await page.getByRole("button", { name: /مدارس الرواد/ }).click();
  await page.getByRole("button", { name: /ثانوية الأندلس/ }).click();
  await expect(page.getByTestId("active-school-name")).toHaveText("ثانوية الأندلس");
});

test("primary shell has no horizontal overflow at release viewports", async ({ page }, testInfo) => {
  await login(page, "0550000002", "ثانوية الأندلس");

  for (const viewport of [
    { width: 360, height: 800 },
    { width: 1024, height: 768 },
    { width: 1366, height: 768 },
  ]) {
    await page.setViewportSize(viewport);
    await page.goto("/dashboard");
    await expect(page.getByTestId("dashboard-page")).toBeVisible();
    await assertNoPageOverflow(page);
    await screenshot(page, testInfo, `dashboard-${viewport.width}x${viewport.height}.png`);
  }
});

test("VP tablet, counselor tablet, manager desktop, and platform admin remain usable", async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 768, height: 1024 });
  await login(page, "0550000003", "ثانوية الأندلس");
  await page.goto("/dashboard");
  await expect(page.getByTestId("dashboard-page")).toBeVisible();
  await assertNoPageOverflow(page);
  await screenshot(page, testInfo, "vice-principal-tablet.png");
  await logout(page);

  await login(page, "0550000005", "ثانوية الأندلس");
  await page.goto("/counselor");
  await expect(page.getByTestId("counselor-kpis")).toBeVisible();
  await assertNoPageOverflow(page);
  await screenshot(page, testInfo, "counselor-tablet.png");
  await logout(page);

  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page, "0550000002", "ثانوية الأندلس");
  await page.goto("/subscription");
  await expect(page.getByRole("heading", { name: "اشتراك المدرسة" })).toBeVisible();
  await screenshot(page, testInfo, "manager-desktop.png");
  await page.goto("/platform");
  await expect(page).not.toHaveURL(/\/platform$/);
  await logout(page);

  await login(page, "0550000016");
  await page.goto("/");
  await expect(page).toHaveURL(/\/platform$/);
  await expect(page.getByRole("heading", { name: "إدارة المنصة" })).toBeVisible();
  await assertNoPageOverflow(page);
  await screenshot(page, testInfo, "platform-admin-desktop.png");
  await page.getByRole("button", { name: "المدارس" }).click();
  await page.getByRole("button", { name: /ثانوية الأندلس/ }).click();
  await expect(page.getByRole("heading", { name: "بيانات المدرسة والدخول" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "حسابات مديري المدرسة" })).toBeVisible();
  await expect(page.getByText("بيانات الاشتراك")).toBeVisible();
  await assertNoPageOverflow(page);
  await screenshot(page, testInfo, "platform-school-account-management.png");
});
