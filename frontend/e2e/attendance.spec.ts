/** E2E المرحلة 6 — تحضير المعلم وQR الفصل (ضد Docker حقيقي).
 *  ذاتي الاكتفاء: يستورد noor-4 (فصلا "8" و"9") بأسماء فريدة لكل تشغيل.
 */

import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test, type Page } from "@playwright/test";

const PASSWORD = process.env.E2E_SEED_PASSWORD ?? "E2e-Dev-2026!pass";
const FIXTURES = resolve(dirname(fileURLToPath(import.meta.url)), "fixtures");

test.describe.configure({ mode: "serial", timeout: 120_000 });

interface Meta {
  attendance_section_manual: string;
  attendance_section_qr: string;
  attendance_students: string[];
  attendance_qr_students: string[];
}

function meta(): Meta {
  return JSON.parse(readFileSync(resolve(FIXTURES, "meta.json"), "utf-8")) as Meta;
}

// يمرر بين الاختبارات التسلسلية في نفس الـ worker
let qrToken = "";

async function login(page: Page, mobile: string, school: string) {
  await page.goto("/");
  await page.getByLabel("رقم الجوال").fill(mobile);
  await page.getByLabel("كلمة المرور", { exact: true }).fill(PASSWORD);
  await page.getByRole("button", { name: "تسجيل الدخول" }).click();
  // كل حسابات هذا الملف متعددة العضويات → صفحة اختيار المدرسة تظهر دائمًا
  await page.locator("li", { hasText: school }).getByRole("button", { name: "دخول" }).click();
  await expect(page.getByTestId("active-school-name")).toHaveText(school, {
    timeout: 15_000,
  });
}

/** معرف الفصل بالاسم عبر الـ API من داخل جلسة المتصفح (بلا تخمين معرفات). */
async function sectionIdByName(page: Page, name: string): Promise<number> {
  const id = await page.evaluate(async (sectionName) => {
    const res = await fetch("/api/v1/attendance/sections/", { credentials: "include" });
    const sections = (await res.json()) as { id: number; name: string }[];
    return sections.find((s) => s.name === sectionName)?.id ?? 0;
  }, name);
  expect(id).toBeGreaterThan(0);
  return id;
}

function studentRow(page: Page, studentName: string) {
  return page.locator('[data-testid^="roster-student-"]', { hasText: studentName });
}

test("manager imports sections 8+9 and generates a section QR", async ({ page }) => {
  await login(page, "0550000002", "ثانوية الأندلس");

  // استيراد ملف الحضور (فصلا 8 و9)
  await page.goto("/students/import");
  await page.getByTestId("import-file-input").setInputFiles(resolve(FIXTURES, "noor-4.xlsx"));
  await page.getByRole("button", { name: "رفع الملف" }).click();
  await expect(page.getByText("الخطوة: مطابقة الأعمدة", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "بدء التحليل" }).click();
  await expect(page.getByRole("tab", { name: /جدد/ })).toBeVisible({ timeout: 120_000 });
  await page.getByRole("button", { name: "متابعة إلى التأكيد" }).click();
  await page.getByRole("button", { name: "اعتماد الاستيراد" }).click();
  await expect(page.getByTestId("import-result")).toBeVisible({ timeout: 60_000 });

  // صفحة رموز QR: اختيار فصل التشغيل الحالي → الرمز يظهر
  const m = meta();
  const section9 = await sectionIdByName(page, m.attendance_section_qr);
  await page.goto("/attendance/qr");
  await page.getByTestId(`qr-section-${section9}`).click();
  await expect(page.getByTestId("qr-canvas")).toBeVisible();
  await expect(page.getByTestId("qr-section-title")).toContainText(m.attendance_section_qr);

  // الرمز المبهم عبر API لاستخدامه في رحلة المعلم
  qrToken = await page.evaluate(async (id) => {
    const res = await fetch(`/api/v1/sections/${id}/qr/`, { credentials: "include" });
    const body = (await res.json()) as { token: string };
    return body.token;
  }, section9);
  expect(qrToken).toMatch(/^[A-Za-z0-9_-]{20,}$/); // رمز مبهم — ليس معرفًا رقميًا
});

test("teacher manual journey: mark → live summary → submit → reload persists → edit", async ({
  page,
}) => {
  const m = meta();
  await login(page, "0550000001", "ثانوية الأندلس");

  // الرئيسية: حصة حالية (جدول التطوير يغطي اليوم كاملًا) وقائمة فصول
  await expect(page.getByTestId("current-period-name")).toBeVisible();
  const section8 = await sectionIdByName(page, m.attendance_section_manual);
  await page.goto(`/attendance/section/${section8}`);

  // القائمة الكاملة والافتراضي «حاضر»
  for (const name of m.attendance_students) {
    await expect(studentRow(page, name)).toBeVisible();
  }
  await expect(page.getByTestId("live-summary")).toContainText("حاضر 3");

  // غائب + متأخر → الملخص الحي يتحدث
  await studentRow(page, m.attendance_students[0])
    .getByRole("button", { name: "غائب" })
    .click();
  await studentRow(page, m.attendance_students[1])
    .getByRole("button", { name: "متأخر" })
    .click();
  await expect(page.getByTestId("live-summary")).toContainText("حاضر 1");
  await expect(page.getByTestId("live-summary")).toContainText("غائب 1");
  await expect(page.getByTestId("live-summary")).toContainText("متأخر 1");

  await page.getByTestId("submit-attendance").click();
  await expect(page.getByTestId("submitted-banner")).toContainText("أحمد", { timeout: 15_000 });

  // إعادة التحميل: الجلسة المرسلة تظهر كما هي (استئناف من الخادم)
  await page.reload();
  await expect(page.getByTestId("submitted-banner")).toBeVisible({ timeout: 15_000 });
  await expect(studentRow(page, m.attendance_students[0])).toContainText("غائب");
  await expect(studentRow(page, m.attendance_students[1])).toContainText("متأخر");

  // التعديل داخل النافذة: الغائب يصبح حاضرًا مع سبب
  await page.getByTestId("edit-button").click();
  await studentRow(page, m.attendance_students[0])
    .getByRole("button", { name: "حاضر" })
    .click();
  await page.getByTestId("edit-reason").fill("حضر متأخرًا عن الرصد");
  await page.getByTestId("submit-attendance").click();
  await expect(page.getByTestId("submitted-banner")).toBeVisible({ timeout: 15_000 });
  await expect(studentRow(page, m.attendance_students[0])).toContainText("حاضر");
  await expect(studentRow(page, m.attendance_students[1])).toContainText("متأخر");
});

test("teacher QR journey: scan URL opens section 9 roster and submits", async ({ page }) => {
  const m = meta();
  expect(qrToken).not.toBe("");
  await login(page, "0550000001", "ثانوية الأندلس");

  // رمز غير صالح → رسالة واضحة بلا أي تسريب
  await page.goto("/qr/invalid-token-000000000000");
  await expect(page.getByRole("alert")).toContainText("رمز QR غير صالح");

  // الرمز الصحيح → قائمة الفصل 9 مباشرة
  await page.goto(`/qr/${qrToken}`);
  for (const name of m.attendance_qr_students) {
    await expect(studentRow(page, name)).toBeVisible({ timeout: 15_000 });
  }
  await studentRow(page, m.attendance_qr_students[0])
    .getByRole("button", { name: "غائب" })
    .click();
  await page.getByTestId("submit-attendance").click();
  await expect(page.getByTestId("submitted-banner")).toContainText("أحمد", { timeout: 15_000 });
});

test("multi-school isolation: switching to school B leaks nothing from school A", async ({
  page,
}) => {
  const m = meta();
  await login(page, "0550000001", "ثانوية الأندلس");
  await expect(page.getByTestId("sections-list")).toBeVisible();

  // التبديل إلى مدارس الرواد
  await page.getByRole("button", { name: "ثانوية الأندلس" }).click();
  await page.getByRole("listbox").getByRole("button", { name: /مدارس الرواد/ }).click();
  await expect(page.getByTestId("active-school-name")).toHaveText("مدارس الرواد");

  // لا فصول في B — ولا أثر لأسماء طلاب A في الصفحة
  await expect(page.getByTestId("no-sections")).toBeVisible();
  for (const name of m.attendance_students) {
    await expect(page.getByText(name)).not.toBeVisible();
  }

  // رمز QR الخاص بمدرسة A لا يعمل من داخل B (لا تسريب عبر المدارس)
  await page.goto(`/qr/${qrToken}`);
  await expect(page.getByRole("alert")).toContainText("رمز QR غير صالح");
});
