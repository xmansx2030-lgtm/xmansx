/** E2E المرحلة 4.1 — دورة حياة الطالب والحذف النهائي (ضد Worker حقيقي).
 *  ذاتي الاكتفاء: يستورد ملفه الخاص (noor-3) بطلاب بأسماء فريدة لكل تشغيل.
 */

import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test, type Page } from "@playwright/test";

const PASSWORD = process.env.E2E_SEED_PASSWORD ?? "E2e-Dev-2026!pass";
const FIXTURES = resolve(dirname(fileURLToPath(import.meta.url)), "fixtures");

// رحلات طويلة: استيراد + تصنيف + حذف عبر Worker حقيقي
test.describe.configure({ mode: "serial", timeout: 120_000 });

interface Meta {
  lifecycle_prefix: string;
  lifecycle_missing: string;
}

function meta(): Meta {
  return JSON.parse(readFileSync(resolve(FIXTURES, "meta.json"), "utf-8")) as Meta;
}

async function loginManagerToAndalus(page: Page) {
  await page.goto("/");
  await page.getByLabel("رقم الجوال").fill("0550000002");
  await page.getByLabel("كلمة المرور", { exact: true }).fill(PASSWORD);
  await page.getByRole("button", { name: "تسجيل الدخول" }).click();
  await page
    .locator("li", { hasText: "ثانوية الأندلس" })
    .getByRole("button", { name: "دخول" })
    .click();
  await expect(page.getByTestId("active-school-name")).toHaveText("ثانوية الأندلس");
}

async function importNoor(page: Page, fixtureFile: string) {
  await page.goto("/students/import");
  await page.getByTestId("import-file-input").setInputFiles(resolve(FIXTURES, fixtureFile));
  await page.getByRole("button", { name: "رفع الملف" }).click();
  await expect(page.getByText("الخطوة: مطابقة الأعمدة", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "بدء التحليل" }).click();
  await expect(page.getByRole("tab", { name: /جدد/ })).toBeVisible({ timeout: 30_000 });
  await page.getByRole("button", { name: "متابعة إلى التأكيد" }).click();
  await page.getByRole("button", { name: "اعتماد الاستيراد" }).click();
  await expect(page.getByTestId("import-result")).toBeVisible({ timeout: 30_000 });
}

async function purgeShown(page: Page, quickButton: RegExp) {
  await page.getByRole("button", { name: quickButton }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  const text = await dialog.locator("p").first().innerText();
  const match = /حذف بيانات (\d+) طالبًا/.exec(text);
  expect(match).toBeTruthy();
  await page.getByTestId("purge-confirm-input").fill(`حذف ${match![1]} طالبًا`);
  const confirmButton = page.getByRole("button", { name: "حذف نهائي" });
  // الحوار ينمو بنمو خطوات الحذف — يجب أن يبقى زر التأكيد قابلًا للوصول داخل الشاشة
  await confirmButton.scrollIntoViewIfNeeded();
  await expect(confirmButton).toBeInViewport();
  await confirmButton.click();
  await expect(page.getByTestId("purge-progress")).toContainText("اكتمل الحذف النهائي", {
    timeout: 30_000,
  });
}

test("graduates: bulk graduate → inactive list → bulk purge → students disappear", async ({
  page,
}) => {
  const m = meta();
  await loginManagerToAndalus(page);
  await importNoor(page, "noor-3.xlsx");

  // تخريج دفعة: بحث بأسماء هذا التشغيل → تحديد الكل → تعيين كخريجين
  await page.goto("/students");
  await page.getByLabel("بحث بالاسم").fill(m.lifecycle_prefix);
  await expect(page.locator("tr", { hasText: `${m.lifecycle_prefix}-1` })).toBeVisible();
  await page.getByRole("checkbox", { name: "تحديد الكل" }).check();
  await page.getByRole("button", { name: "تعيين المحددين كخريجين" }).click();
  // اختفوا من النشطين
  await expect(page.locator("tr", { hasText: `${m.lifecycle_prefix}-1` })).not.toBeVisible();

  // غير النشطين → فلتر الخريجين + بحث بأسماء هذا التشغيل → طلابنا بآخر صف/فصل
  await page.goto("/students/inactive");
  await page.getByRole("tab", { name: "الخريجون" }).click();
  await page.getByLabel("بحث بالاسم").fill(m.lifecycle_prefix);
  const row = page.locator("tr", { hasText: `${m.lifecycle_prefix}-1` });
  await expect(row).toBeVisible();
  await expect(row).toContainText("الثالث الثانوي");
  await expect(row).toContainText("متخرج");

  // حذف جميع الخريجين المعروضين → تأكيد بالكتابة → تقدم → اكتمال
  await purgeShown(page, /حذف جميع الخريجين المعروضين/);

  // الطلاب اختفوا نهائيًا
  await page.reload();
  await page.getByRole("tab", { name: "الخريجون" }).click();
  await page.getByLabel("بحث بالاسم").fill(m.lifecycle_prefix);
  await expect(page.getByText("لا يوجد طلاب مطابقون.")).toBeVisible();
});

test("missing from new Noor file: review → mark transferred → purge transferred", async ({
  page,
}) => {
  const m = meta();
  await loginManagerToAndalus(page);
  // إعادة استيراد الملف الكامل (يعيد إنشاء الطلاب المحذوفين في الاختبار السابق)
  await importNoor(page, "noor-3.xlsx");
  // ثم ملف جديد ناقص الطالب 3
  await importNoor(page, "noor-3b.xlsx");

  // فلتر «غير الموجودين في آخر ملف نور» يظهر الطالب 3 — ولم يحذف
  await page.goto("/students/inactive");
  await page.getByRole("tab", { name: "غير الموجودين في آخر ملف نور" }).click();
  await page.getByLabel("بحث بالاسم").fill(m.lifecycle_missing);
  const missingRow = page.locator("tr", { hasText: m.lifecycle_missing });
  await expect(missingRow).toBeVisible();

  // تحديده وتعيينه منتقلًا
  await missingRow.getByRole("checkbox").check();
  await page.getByRole("button", { name: "تعيين كمنتقلين" }).click();

  // فلتر المنتقلين (بحث بهذا التشغيل) → حذفهم نهائيًا
  await page.getByRole("tab", { name: "المنتقلون" }).click();
  await page.getByLabel("بحث بالاسم").fill(m.lifecycle_missing);
  await expect(page.locator("tr", { hasText: m.lifecycle_missing })).toBeVisible();
  await purgeShown(page, /حذف جميع المنتقلين المعروضين/);

  await page.reload();
  await page.getByRole("tab", { name: "المنتقلون" }).click();
  await page.getByLabel("بحث بالاسم").fill(m.lifecycle_missing);
  await expect(page.getByText("لا يوجد طلاب مطابقون.")).toBeVisible();
});

test("vice principal: no purge controls and API purge denied", async ({ page }) => {
  // سعد الوكيل — ثانوية الأندلس
  await page.goto("/");
  await page.getByLabel("رقم الجوال").fill("0550000003");
  await page.getByLabel("كلمة المرور", { exact: true }).fill(PASSWORD);
  await page.getByRole("button", { name: "تسجيل الدخول" }).click();
  await expect(page.getByTestId("active-school-name")).toHaveText("ثانوية الأندلس");

  await page.goto("/students/inactive");
  await expect(page.getByRole("heading", { name: "الطلاب غير النشطين" })).toBeVisible();
  await expect(page.getByRole("button", { name: /حذف/ })).not.toBeVisible();
  await expect(page.getByRole("checkbox")).not.toBeVisible();

  const statuses = await page.evaluate(async () => {
    const csrf = document.cookie
      .split("; ")
      .find((c) => c.startsWith("csrftoken="))
      ?.split("=")[1];
    const preview = await fetch("/api/v1/student-purges/preview/", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf ?? "" },
      body: JSON.stringify({ student_ids: [1] }),
    });
    const bulk = await fetch("/api/v1/students/bulk-status/", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf ?? "" },
      body: JSON.stringify({ student_ids: [1], status: "GRADUATED" }),
    });
    return { preview: preview.status, bulk: bulk.status };
  });
  expect(statuses.preview).toBe(403);
  expect(statuses.bulk).toBe(403);
});
