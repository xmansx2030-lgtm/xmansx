/** E2E المرحلة 3 — رحلة مدير المدرسة الكاملة + حدود الأدوار عبر المدارس.
 *  يتطلب seed_dev: خالد 0550000002 = مدير في ثانوية الأندلس + معلم في مدارس الرواد.
 */

import { expect, test, type Page } from "@playwright/test";

const PASSWORD = process.env.E2E_SEED_PASSWORD ?? "E2e-Dev-2026!pass";
const RUN_TAG = `${Date.now()}`.slice(-6);
const CITY_VALUE = `الرياض ${RUN_TAG}`;

async function loginAsManager(page: Page) {
  await page.goto("/");
  await page.getByLabel("رقم الجوال").fill("0550000002");
  await page.getByLabel("كلمة المرور", { exact: true }).fill(PASSWORD);
  await page.getByRole("button", { name: "تسجيل الدخول" }).click();
  // مدرستان → شاشة الاختيار
  await page
    .locator("li", { hasText: "ثانوية الأندلس" })
    .getByRole("button", { name: "دخول" })
    .click();
  await expect(page.getByTestId("active-school-name")).toHaveText("ثانوية الأندلس");
}

test("manager full settings journey: data, year, semester, schedule, days, attendance settings", async ({
  page,
}) => {
  await loginAsManager(page);

  // فتح الإعدادات
  await page.getByRole("link", { name: "الإعدادات" }).click();
  await expect(page.getByRole("heading", { name: "إعدادات المدرسة" })).toBeVisible();

  // 1) تعديل بيانات المدرسة
  await page.getByLabel("المدينة").fill(CITY_VALUE);
  await page.getByRole("button", { name: "حفظ البيانات" }).click();
  await expect(page.getByText("تم حفظ بيانات المدرسة بنجاح.")).toBeVisible();

  // 2) إنشاء عام دراسي
  await page.getByRole("tab", { name: "العام الدراسي" }).click();
  await page.getByLabel(/اسم العام/).fill(`عام ${RUN_TAG}`);
  await page.getByLabel("بداية العام").fill("2026-08-23");
  await page.getByLabel("نهاية العام").fill("2027-06-25");
  await page.getByRole("button", { name: "إنشاء عام دراسي" }).click();
  const yearCard = page.getByTestId("academic-year-card").filter({
    has: page.getByRole("heading", { name: `عام ${RUN_TAG}`, exact: true }),
  });
  await expect(yearCard).toBeVisible();

  // 3) إنشاء فصل دراسي داخل العام
  await yearCard.getByRole("button", { name: "إضافة فصل دراسي" }).click();
  await yearCard.getByLabel("البداية").fill("2026-08-23");
  await yearCard.getByLabel("النهاية").fill("2026-12-10");
  await yearCard.getByRole("button", { name: "حفظ الفصل" }).click();
  await expect(yearCard.getByText(/الفصل الدراسي 1/)).toBeVisible();

  // 4) إنشاء جدول حصص بـ 7 حصص
  await page.getByRole("tab", { name: "أوقات الحصص" }).click();
  await page.getByLabel(/اسم الجدول/).fill(`الجدول العادي ${RUN_TAG}`);
  await page.getByRole("button", { name: "إنشاء جدول" }).click();
  const scheduleCard = page.getByTestId("bell-schedule-card").filter({
    has: page.getByRole("heading", {
      name: `الجدول العادي ${RUN_TAG}`,
      exact: true,
    }),
  });
  await expect(scheduleCard).toBeVisible();

  const times: [string, string][] = [
    ["07:00", "07:45"], ["07:45", "08:30"], ["08:30", "09:15"], ["09:15", "10:00"],
    ["10:20", "11:05"], ["11:05", "11:50"], ["11:50", "12:35"],
  ];
  for (let i = 0; i < times.length; i++) {
    await scheduleCard.getByRole("button", { name: "إضافة حصة" }).click();
    const entry = times[i];
    if (!entry) continue;
    await scheduleCard.getByLabel(`بداية الفترة ${i + 1}`).fill(entry[0]);
    await scheduleCard.getByLabel(`نهاية الفترة ${i + 1}`).fill(entry[1]);
  }
  await scheduleCard.getByRole("button", { name: "حفظ الحصص" }).click();
  await expect(scheduleCard.getByText("تم حفظ الحصص.")).toBeVisible();

  // 5) تطبيق الجدول على الأحد–الخميس
  for (const day of ["الأحد", "الاثنين", "الثلاثاء", "الأربعاء", "الخميس"]) {
    await scheduleCard.getByRole("checkbox", { name: day }).check();
  }
  await scheduleCard.getByRole("button", { name: "تطبيق على الأيام المحددة" }).click();
  await expect(scheduleCard.getByText("تم ربط الجدول بالأيام المحددة.")).toBeVisible();

  // 6) إعدادات التحضير: غيّر القيم فعليًا حتى يبقى الاختبار صالحًا بعد إعادة التشغيل
  await page.getByRole("tab", { name: "إعدادات التحضير" }).click();
  const alertInput = page.getByLabel(/إظهار تنبيه/);
  const editWindowInput = page.getByLabel("مهلة تعديل التحضير");
  const alertValue = (await alertInput.inputValue()) === "25" ? "26" : "25";
  const editWindowValue = (await editWindowInput.inputValue()) === "15" ? "16" : "15";
  await alertInput.fill(alertValue);
  await editWindowInput.fill(editWindowValue);
  await page.getByRole("button", { name: "حفظ الإعدادات" }).click();
  await expect(page.getByText("تم حفظ سياسة التحضير.")).toBeVisible();

  // 7) إعادة تحميل — كل القيم ثابتة
  await page.reload();
  await page.getByRole("tab", { name: "إعدادات التحضير" }).click();
  await expect(page.getByLabel(/إظهار تنبيه/)).toHaveValue(alertValue);
  await expect(page.getByLabel("مهلة تعديل التحضير")).toHaveValue(editWindowValue);

  await page.getByRole("tab", { name: "بيانات المدرسة" }).click();
  await expect(page.getByLabel("المدينة")).toHaveValue(CITY_VALUE);

  await page.getByRole("tab", { name: "أيام الدراسة", exact: true }).click();
  await expect(
    page.locator("li", { hasText: "الأحد" }).locator("select"),
  ).toContainText(`الجدول العادي ${RUN_TAG}`);
});

test("multi-tenant roles: manager in A is teacher in B — settings blocked in B", async ({
  page,
}) => {
  await loginAsManager(page);
  await expect(page.getByRole("link", { name: "الإعدادات" })).toBeVisible();

  // التبديل إلى مدارس الرواد حيث هو معلم فقط
  await page.getByRole("button", { name: /ثانوية الأندلس/ }).click();
  await page.getByRole("button", { name: /مدارس الرواد/ }).click();
  await expect(page.getByTestId("active-school-name")).toHaveText("مدارس الرواد");

  // رابط الإعدادات يختفي (UX) — والخادم يرفض مباشرة (الحماية الحقيقية)
  await expect(page.getByRole("link", { name: "الإعدادات" })).not.toBeVisible();

  const patchStatus = await page.evaluate(async () => {
    const csrf = document.cookie
      .split("; ")
      .find((c) => c.startsWith("csrftoken="))
      ?.split("=")[1];
    const response = await fetch("/api/v1/school/settings/", {
      method: "PATCH",
      credentials: "include",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf ?? "" },
      body: JSON.stringify({ city: "اختراق" }),
    });
    return response.status;
  });
  expect(patchStatus).toBe(403);
});
