import { expect, test, type Page, type TestInfo } from "@playwright/test";

const PASSWORD = process.env.E2E_SEED_PASSWORD ?? "E2e-Dev-2026!pass";
const VIEWPORTS = [
  { width: 375, height: 812 },
  { width: 390, height: 844 },
  { width: 430, height: 932 },
  { width: 500, height: 900 },
  { width: 768, height: 1024 },
  { width: 1024, height: 768 },
  { width: 1280, height: 800 },
  { width: 1440, height: 900 },
  { width: 1920, height: 1080 },
] as const;

const MANAGER_ROUTES = [
  "/dashboard",
  "/students",
  "/students/inactive",
  "/students/import",
  "/staff",
  "/staff/import",
  "/reports",
  "/warnings",
  "/excuses",
  "/referrals",
  "/counselor",
  "/attendance/monitoring",
  "/attendance/analytics",
  "/morning",
  "/student-leaves",
  "/gate",
  "/attendance/qr",
  "/devices",
  "/devices/roster-sync",
  "/subscription",
  "/settings",
  "/settings?section=calendar",
] as const;

async function login(page: Page, mobile: string, school?: string) {
  await page.goto("/login");
  await page.getByLabel("رقم الجوال").fill(mobile);
  await page.getByLabel("كلمة المرور", { exact: true }).fill(PASSWORD);
  await page.getByRole("button", { name: "تسجيل الدخول" }).click();
  await expect(page).not.toHaveURL(/\/login$/, { timeout: 20_000 });
  if (school) {
    if (/\/select-school$/.test(new URL(page.url()).pathname)) {
      await page.locator("li", { hasText: school }).getByRole("button", { name: "دخول" }).click();
    }
    await expect(page.getByTestId("active-school-name")).toHaveText(school);
  }
}

async function assertViewportContract(page: Page, path: string) {
  await expect(page.locator("main h1").first(), path).toBeVisible({ timeout: 20_000 });
  await expect(page.getByRole("heading", { name: "حدث خطأ غير متوقع" }), path).toHaveCount(0);
  const audit = await page.evaluate(() => ({
    viewport: document.documentElement.clientWidth,
    content: document.documentElement.scrollWidth,
    direction: document.documentElement.dir,
    unnamedButtons: [...document.querySelectorAll("button")].filter(
      (button) => !(button.getAttribute("aria-label") || button.textContent?.trim()),
    ).length,
    unlabelledFields: [...document.querySelectorAll("input,select,textarea")].filter((field) => {
      if (field.getAttribute("aria-label") || field.getAttribute("aria-labelledby") || field.closest("label")) return false;
      return !(field.id && document.querySelector(`label[for="${CSS.escape(field.id)}"]`));
    }).length,
  }));
  expect(audit.content, path).toBeLessThanOrEqual(audit.viewport + 1);
  expect(audit.direction, path).toBe("rtl");
  expect(audit.unnamedButtons, path).toBe(0);
  expect(audit.unlabelledFields, path).toBe(0);
}

/** Hundreds of full reloads are an artificial request burst. Respect the real
 * 240/account/minute budget, reserving room for requests from the current page.
 * BrowserContext also observes service-worker requests; no Redis keys or
 * production limits are changed for this matrix. */
function requestPacer(page: Page) {
  let minute = Math.floor(Date.now() / 60_000);
  let count = 0;
  page.context().on("request", (request) => {
    if (!new URL(request.url()).pathname.startsWith("/api/")) return;
    const now = Math.floor(Date.now() / 60_000);
    if (now !== minute) { minute = now; count = 0; }
    count += 1;
  });
  return async () => {
    if (Math.floor(Date.now() / 60_000) === minute && count >= 180) {
      await page.waitForTimeout((minute + 1) * 60_000 - Date.now() + 1500);
    }
  };
}

test.describe.configure({ mode: "serial", timeout: 720_000 });

test("all manager workspaces satisfy the exact responsive RTL matrix", async ({ page }, testInfo: TestInfo) => {
  const pace = requestPacer(page);
  await login(page, "0550000002", "ثانوية الأندلس");

  for (const viewport of VIEWPORTS) {
    await page.setViewportSize(viewport);
    for (const path of MANAGER_ROUTES) {
      await page.goto(path);
      await assertViewportContract(page, path);
      await pace();
    }
    await page.goto("/dashboard");
    await page.screenshot({ path: testInfo.outputPath(`manager-${viewport.width}.png`), fullPage: false });
  }
});

test("teacher, counselor, and platform shells satisfy the same viewport contract", async ({ page }) => {
  const pace = requestPacer(page);
  const roleJourneys = [
    { mobile: "0550000001", school: "ثانوية الأندلس", routes: ["/", "/teacher/follow-ups", "/referrals/mine"] },
    { mobile: "0550000005", school: "ثانوية الأندلس", routes: ["/counselor", "/students", "/excuses", "/referrals"] },
  ] as const;

  for (const journey of roleJourneys) {
    await login(page, journey.mobile, journey.school);
    for (const viewport of VIEWPORTS) {
      await page.setViewportSize(viewport);
      for (const path of journey.routes) {
        await page.goto(path);
        await assertViewportContract(page, path);
        await pace();
      }
    }
    await page.getByRole("button", { name: "تسجيل الخروج" }).click();
    await expect(page).toHaveURL(/\/login$/);
  }

  await login(page, "0550000016");
  for (const viewport of VIEWPORTS) {
    await page.setViewportSize(viewport);
    await page.goto("/platform");
    await assertViewportContract(page, "/platform");
  }
});

test("public and authentication surfaces satisfy the exact responsive matrix", async ({ page }) => {
  for (const viewport of VIEWPORTS) {
    await page.setViewportSize(viewport);
    await page.goto("/login");
    await assertViewportContract(page, "/login");
    await page.goto("/qr/invalid-token");
    await assertViewportContract(page, "/qr/:token");
  }
});
