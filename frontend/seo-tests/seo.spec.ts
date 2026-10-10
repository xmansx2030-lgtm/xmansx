import { expect, test } from "@playwright/test";

const features = ["attendance", "student-follow-up", "reports", "parent-portal", "qr-attendance"];

test("serves actual crawler files and meaningful HTTP statuses", async ({ request }) => {
  const robots = await request.get("/robots.txt");
  expect(robots.status()).toBe(200);
  expect(robots.headers()["content-type"]).toContain("text/plain");
  expect(await robots.text()).toContain("Sitemap: https://mowadhabah.com/sitemap.xml");
  const sitemap = await request.get("/sitemap.xml");
  expect(sitemap.status()).toBe(200);
  expect(sitemap.headers()["content-type"]).toContain("xml");
  expect((await sitemap.text()).match(/<loc>/g)).toHaveLength(6);
  for (const path of ["/login", "/parent/activate?token=secret", "/qr/secret", "/students/42/attendance"]) {
    const privatePage = await request.get(path);
    expect(privatePage.status()).toBe(200);
    expect(privatePage.headers()["x-robots-tag"]).toContain("noindex");
    expect(await privatePage.text()).not.toContain('rel="canonical"');
  }
  const missing = await request.get("/this-page-does-not-exist");
  expect(missing.status()).toBe(404);
  expect(await missing.text()).toContain("الصفحة غير موجودة");
  const discoveryMissing = await request.get("/features/not-a-feature");
  expect(discoveryMissing.status()).toBe(404);
  const trailing = await request.get("/features/reports/?source=test", {
    maxRedirects: 0, headers: { "X-Forwarded-Proto": "https" },
  });
  expect(trailing.status()).toBe(301);
  expect(trailing.headers().location).toBe("/features/reports?source=test");
  const indexAlias = await request.get("/index.html?source=test", {
    maxRedirects: 0, headers: { "X-Forwarded-Proto": "https" },
  });
  expect(indexAlias.status()).toBe(301);
  expect(indexAlias.headers().location).toBe("/?source=test");
  expect((await request.get("/icons/pwa-512.png")).status()).toBe(200);
  expect((await request.get("/app.html")).status()).toBe(200);
});

test("public pages are readable and linked with JavaScript disabled", async ({ browser, baseURL }) => {
  const context = await browser.newContext({ javaScriptEnabled: false, baseURL });
  const page = await context.newPage();
  try {
    for (const path of ["/", ...features.map((feature) => `/features/${feature}`)]) {
      const response = await page.goto(path);
      expect(response?.status()).toBe(200);
      expect(response?.headers()["content-type"]).toContain("text/html");
      await expect(page.locator("h1")).toBeVisible();
      await expect(page.locator('link[rel="canonical"]')).toHaveAttribute("href", `https://mowadhabah.com${path}`);
      await expect(page.locator('meta[name="robots"]')).toHaveAttribute("content", /^index,/);
      expect((await page.locator("#root").textContent())!.length).toBeGreaterThan(500);
      expect(await page.locator('a[href^="/features/"]').count()).toBeGreaterThan(3);
    }
  } finally { await context.close(); }
});

test("interactive navigation keeps metadata accurate and private tokens out", async ({ page }) => {
  const errors: string[] = [];
  const blockedScripts: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => { if (message.type() === "error" && message.text().includes("script-src")) blockedScripts.push(message.text()); });
  await page.route("**/api/**", (route) => route.fulfill({ status: route.request().url().includes("/auth/me/") ? 401 : 200, contentType: "application/json", body: route.request().url().includes("/auth/me/") ? '{"code":"UNAUTHENTICATED","message":"سجل الدخول","details":{}}' : "[]" }));
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await page.getByRole("tab", { name: /متابعة تربط المعلومة/ }).click();
  await expect(page.getByRole("tabpanel")).toContainText("الأعذار والإنذارات");
  await page.locator('a[href="/features/parent-portal"]').click();
  await expect(page.locator("h1")).toHaveText("بوابة ولي الأمر");
  await expect(page.locator('meta[property="og:url"]')).toHaveAttribute("content", "https://mowadhabah.com/features/parent-portal");
  await page.getByRole("link", { name: "تسجيل الدخول", exact: true }).click();
  await expect(page.locator('meta[name="robots"]')).toHaveAttribute("content", /noindex/);
  await expect(page.locator('link[rel="canonical"]')).toHaveCount(0);
  await expect(page.locator('script[type="application/ld+json"]')).toHaveCount(0);
  await page.goto("/parent/activate?token=synthetic-private-token");
  await expect(page.locator('meta[name="robots"]')).toHaveAttribute("content", /noindex/);
  expect(await page.locator("head").textContent()).not.toContain("synthetic-private-token");
  await page.goto("/features/not-a-feature");
  await expect(page.getByRole("heading", { name: "الصفحة غير موجودة" })).toBeVisible();
  await expect(page.locator('meta[name="robots"]')).toHaveAttribute("content", /noindex/);
  expect(errors).toEqual([]);
  expect(blockedScripts).toEqual([]);
});

test("public feature pages fit mobile, tablet and desktop", async ({ page }, testInfo) => {
  for (const width of [390, 768, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/features/attendance");
    await expect(page.locator("h1")).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath(`seo-attendance-${width}.png`), fullPage: true });
    await page.route("**/api/**", (route) => route.fulfill({ status: 401, contentType: "application/json", body: '{"code":"UNAUTHENTICATED","message":"سجل الدخول","details":{}}' }));
    await page.goto("/");
    await expect(page.locator("h1")).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  }
});

test("the service worker installs the app shell without caching private API data", async ({ page }) => {
  await page.route("**/api/**", (route) => route.fulfill({ status: 401, contentType: "application/json", body: '{"code":"UNAUTHENTICATED","message":"سجل الدخول","details":{}}' }));
  await page.goto("/");
  await expect.poll(() => page.evaluate(async () => Boolean((await navigator.serviceWorker.getRegistration())?.active)), { timeout: 30_000 }).toBe(true);
  expect(await page.evaluate(async () => {
    for (const name of await caches.keys()) {
      const cache = await caches.open(name);
      for (const request of await cache.keys()) if (new URL(request.url).pathname.startsWith("/api/")) return false;
    }
    return true;
  })).toBe(true);
});
