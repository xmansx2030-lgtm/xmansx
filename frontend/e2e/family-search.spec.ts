import { expect, test } from "@playwright/test";

// Synthetic UI fixtures; PostgreSQL/RLS search is covered separately in backend tests.
test.use({ serviceWorkers: "block" });

for (const viewport of [
  { name: "desktop", width: 1366, height: 900, role: "SCHOOL_MANAGER" },
  { name: "tablet", width: 768, height: 1024, role: "VICE_PRINCIPAL" },
  { name: "mobile", width: 390, height: 844, role: "SCHOOL_MANAGER" },
]) {
  test(`family search resets pagination and selection on ${viewport.name}`, async ({ page }) => {
    await page.setViewportSize(viewport);
    const school = { id: 20, name: "مدرسة اختبار البحث", slug: "search-school", school_type: "BOYS" };
    const family = {
      key: "synthetic-family", name: "أحمد ولي الأسرة", names: ["أحمد ولي الأسرة"],
      mobile: "+966551900003", mobile_masked: "+96655****003", needs_review: false,
      child_count: 2, children: [{ id: 1, name: "محمد أحمد", revision: 1 }, { id: 2, name: "خالد أحمد", revision: 1 }],
      invitation: null,
    };
    const errors: string[] = [];
    const searches: URL[] = [];
    let writes = 0;
    page.on("pageerror", error => errors.push(error.message));
    await page.route("**/api/v1/**", async route => {
      const url = new URL(route.request().url());
      if (route.request().method() !== "GET") writes++;
      let body: unknown = {};
      if (url.pathname.endsWith("/auth/me/")) {
        body = { id: 20, mobile: "+966551234567", name: "مدير اختبار البحث", is_platform_admin: false,
          active_school: school, roles: [viewport.role], capabilities: [], has_parent_portal: false, school_features: { PARENT_PORTAL: true, ABSENCE_SMS: true, BIOMETRIC_DEVICES: true },
          memberships: [{ id: 1, school, roles: [viewport.role], status: "ACTIVE" }], invitations: [],
          must_change_password: false, requires_initial_email: false };
      } else if (url.pathname.endsWith("/staff/parents/families/")) {
        searches.push(url);
        const term = url.searchParams.get("search");
        const empty = term === "غير موجود";
        body = { count: empty ? 0 : term ? 1 : 26, results: empty ? [] : [family],
          next: !term && url.searchParams.get("page") !== "2" ? "?page=2" : null,
          previous: url.searchParams.get("page") === "2" ? "?page=1" : null,
          sms_enabled: true, sms_configured: true };
      }
      await route.fulfill({ contentType: "application/json", body: JSON.stringify(body) });
    });
    await page.goto("/parent-management?tab=families");
    await page.getByRole("button", { name: "التالي", exact: true }).click();
    await expect(page.getByText("صفحة 2", { exact: true })).toBeVisible();
    await page.getByLabel(`اختيار ${family.name}`).check();
    const search = page.getByRole("searchbox", { name: "البحث عن ولي الأمر" });
    await search.fill("محمد أحمد");
    await expect(page.getByText("1 أسرة مطابقة للبحث", { exact: true })).toBeVisible();
    expect(searches.at(-1)?.searchParams.get("page")).toBe("1");
    expect(searches.at(-1)?.searchParams.get("search")).toBe("محمد أحمد");
    await expect(page.getByText("خالد أحمد", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "مراجعة وإرسال للمحدد (0)" })).toBeDisabled();
    await search.scrollIntoViewIfNeeded();
    await page.screenshot({ path: `../artifacts/parent-staging/family-search-${viewport.name}.png`, fullPage: true });
    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
    await search.fill("غير موجود");
    await expect(page.getByRole("heading", { name: "لا توجد أسر مطابقة للبحث" })).toBeVisible();
    await page.getByRole("button", { name: "مسح البحث" }).click();
    await expect(search).toHaveValue("");
    await expect(page.getByText("26 أسرة مقترحة", { exact: true })).toBeVisible();
    expect(writes).toBe(0);
    expect(errors).toEqual([]);
  });
}
