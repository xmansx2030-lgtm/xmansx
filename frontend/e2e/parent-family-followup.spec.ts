import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { FRONTEND_URL } from "./compose";
import { securePost } from "./parent-email-mailbox";

const fixture = JSON.parse(readFileSync(
  process.env.PARENT_E2E_FIXTURE ?? resolve("..", "artifacts", "parent-e2e-fixture.json"), "utf-8",
)) as {
  date: string;
  schools: Array<{ id: number; staff_mobile: string; acceptance_staff: { VICE_PRINCIPAL: { mobile: string } } }>;
  acceptance: { parent_mobile: string; children: Array<{ relation_id: number; student_name: string; school_id: number }> };
};
const password = process.env.E2E_SEED_PASSWORD;
if (!password || !fixture.acceptance || fixture.schools.length !== 3) {
  throw new Error("A fresh synthetic staging fixture and explicit seed password are required.");
}
const viewports = [
  { name: "desktop", width: 1366, height: 900 },
  { name: "tablet", width: 768, height: 1024 },
  { name: "mobile", width: 390, height: 844 },
] as const;

for (const viewport of viewports) {
  test(`manager and vice review the exact family queue request on ${viewport.name}`, async ({ page, playwright }) => {
    await page.setViewportSize(viewport);
    const parent = await playwright.request.newContext({ baseURL: FRONTEND_URL, ignoreHTTPSErrors: false });
    const manager = await playwright.request.newContext({ baseURL: FRONTEND_URL, ignoreHTTPSErrors: false });
    const vice = await playwright.request.newContext({ baseURL: FRONTEND_URL, ignoreHTTPSErrors: false });
    const contexts = [parent, manager, vice];
    const school = fixture.schools[0]!;
    const child = fixture.acceptance.children.find(item => item.school_id === school.id)!;
    const errors: string[] = [];
    page.on("pageerror", error => errors.push(error.message));
    try {
      for (const [context, mobile] of [[parent, fixture.acceptance.parent_mobile], [manager, school.staff_mobile], [vice, school.acceptance_staff.VICE_PRINCIPAL.mobile]] as const) {
        expect((await context.get("/api/v1/auth/csrf/")).status()).toBe(200);
        expect((await securePost(context, "/auth/login/", { mobile, password })).status()).toBe(200);
      }
      const created = await securePost(parent, `/parent/children/${child.relation_id}/excuses/`, {
        reason_type: "OTHER", notes: `طلب قبول متابعة الأسرة ${viewport.name}`,
        targets: [{ attendance_date: fixture.date, period_sequence: 1 }],
      });
      expect(created.status()).toBe(201);
      const excuse = await created.json() as { id: number };
      const path = `/parent-management?tab=requests&type=EXCUSE&request=${excuse.id}`;
      for (const actor of [manager, vice]) {
        await page.context().clearCookies();
        await page.context().addCookies((await actor.storageState()).cookies);
        await page.goto("/dashboard");
        const item = page.getByTestId(`attention-item-PARENT_EXCUSE_PENDING-${excuse.id}`);
        const link = item.getByRole("link", { name: "مراجعة عذر ولي الأمر" });
        // The queue may contain enough existing kinds to require expansion.
        const expand = page.getByRole("button", { name: /^عرض بقية المهام/ });
        if (await expand.isVisible()) await expand.click();
        await expect(link).toBeVisible();
        await expect(link).toHaveAttribute("href", path);
        await link.click();
        const dialog = page.getByRole("dialog");
        await expect(dialog.getByText(child.student_name, { exact: true })).toBeVisible();
        await expect(dialog.getByText(fixture.date, { exact: true })).toBeVisible();
        await expect(dialog.getByText(/الحصة 1/)).toBeVisible();
        await expect(dialog.getByText("ولي حالات القبول الصناعية", { exact: true })).toBeVisible();
        await expect(dialog.getByRole("button", { name: "حفظ قرار الطلب" })).toBeVisible();
        await page.screenshot({
          path: `../artifacts/parent-staging/family-followup-${viewport.name}-${actor === manager ? "manager" : "vice"}-pending.png`,
          fullPage: true,
        });
      }
      const dialog = page.getByRole("dialog");
      await dialog.getByLabel("قرار الطلب", { exact: true }).selectOption("REJECTED");
      await dialog.getByLabel("سبب القرار ورد المدرسة").fill("رفض صناعي بعد مراجعة النطاق");
      await dialog.getByRole("button", { name: "حفظ قرار الطلب" }).click();
      await expect(dialog.getByRole("button", { name: "حفظ قرار الطلب" })).toHaveCount(0);
      await expect(dialog.getByText("رفض صناعي بعد مراجعة النطاق", { exact: true })).toBeVisible();
      await expect(dialog.getByText("مرفوض", { exact: true })).toBeVisible();
      await expect(dialog.getByLabel("قرار الطلب", { exact: true })).toHaveCount(0);
      await page.screenshot({ path: `../artifacts/parent-staging/family-followup-${viewport.name}.png`, fullPage: true });
      expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
      const queue = await vice.get("/api/v1/dashboard/attention/");
      expect(queue.status()).toBe(200);
      expect((await queue.json() as { items: Array<{ kind: string; entity_id: number }> }).items.some(item => item.kind === "PARENT_EXCUSE_PENDING" && item.entity_id === excuse.id)).toBe(false);
      await page.reload();
      await expect(page.getByRole("dialog").getByText("رفض صناعي بعد مراجعة النطاق", { exact: true })).toBeVisible();
      await expect(page.getByRole("dialog").getByText(/طلب منتهٍ/)).toBeVisible();
      expect(errors).toEqual([]);
    } finally {
      for (const context of contexts) await context.dispose();
    }
  });
}
