/** E2E المرحلة 5 — استيراد المعلمين ضد Worker حقيقي:
 *  1) معلم جديد: استيراد → كلمة مؤقتة تعرض مرة واحدة → دخول → تغيير إجباري → Shell.
 *  2) متعدد المدارس: مدرسة B تستورد نفس الجوال → دعوة → قبول → المدرستان في Switcher.
 *  3) مرشد يستورد كمعلم → دوراه معًا.
 *  4) العزل: مدير A معلم في B — لا استيراد موظفين في B.
 *  يتطلب: docker compose up + seed_dev (منى المديرة لمدرستي B وC).
 */

import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test, type Page } from "@playwright/test";

const PASSWORD = process.env.E2E_SEED_PASSWORD ?? "E2e-Dev-2026!pass";
const FIXTURES = resolve(dirname(fileURLToPath(import.meta.url)), "fixtures");

test.describe.configure({ mode: "serial" });

interface Meta {
  tag: string;
  teacher1_name: string;
  teacher1_mobile: string;
  teacher2_name: string;
  teacher3_name: string;
}

function meta(): Meta {
  return JSON.parse(readFileSync(resolve(FIXTURES, "meta.json"), "utf-8")) as Meta;
}

async function login(page: Page, mobile: string, password: string) {
  await page.goto("/");
  await page.getByLabel("رقم الجوال").fill(mobile);
  await page.getByLabel("كلمة المرور", { exact: true }).fill(password);
  await page.getByRole("button", { name: "تسجيل الدخول" }).click();
}

async function selectSchool(page: Page, schoolName: string) {
  await page
    .locator("li", { hasText: schoolName })
    .getByRole("button", { name: "دخول" })
    .click();
  await expect(page.getByTestId("active-school-name")).toHaveText(schoolName);
}

async function runStaffImport(page: Page, fixtureFile: string) {
  await page.goto("/staff/import");
  await page.getByTestId("staff-file-input").setInputFiles(resolve(FIXTURES, fixtureFile));
  await page.getByRole("button", { name: "رفع الملف" }).click();
  await expect(page.getByText("مطابقة الأعمدة")).toBeVisible();
  await page.getByRole("button", { name: "بدء التحليل" }).click();
  await expect(page.getByRole("tab", { name: /معلمون جدد/ })).toBeVisible({
    timeout: 30_000,
  });
  await page.getByRole("button", { name: "متابعة إلى التأكيد" }).click();
  await page.getByRole("button", { name: "اعتماد الاستيراد" }).click();
  await expect(page.getByTestId("staff-import-result")).toBeVisible({ timeout: 30_000 });
}

let teacher1TempPassword = "";
const TEACHER1_NEW_PASSWORD = "Jadeed-2026!x";

test("new teacher journey: import → one-time credentials → forced password change → shell", async ({
  page,
}) => {
  const m = meta();
  // المدير خالد في ثانوية الأندلس
  await login(page, "0550000002", PASSWORD);
  await selectSchool(page, "ثانوية الأندلس");

  await runStaffImport(page, "staff-a.xlsx");
  const credentials = page.getByTestId("new-credentials");
  await expect(credentials).toContainText(m.teacher1_name);
  await expect(credentials).toContainText("مرة واحدة فقط");
  teacher1TempPassword = (await page.getByTestId("temp-password-0").innerText()).trim();
  expect(teacher1TempPassword.length).toBeGreaterThan(8);

  // الدليل يعرض المعلم الجديد بجوال مقنع
  await page.getByRole("button", { name: "عرض الموظفين" }).click();
  await page.getByLabel(/بحث/).fill(m.teacher1_name);
  const row = page.locator("li", { hasText: m.teacher1_name });
  await expect(row).toBeVisible();
  await expect(row).not.toContainText(m.teacher1_mobile.replace(/^0/, "+966"));

  // خروج المدير ودخول المعلم الجديد بالكلمة المؤقتة
  await page.getByRole("button", { name: "تسجيل الخروج" }).click();
  await login(page, m.teacher1_mobile, teacher1TempPassword);

  // شاشة التغيير الإجبارية
  await expect(page.getByRole("heading", { name: "تغيير كلمة المرور" })).toBeVisible();
  await page.getByLabel("كلمة المرور الحالية").fill(teacher1TempPassword);
  await page.getByLabel("كلمة المرور الجديدة").fill(TEACHER1_NEW_PASSWORD);
  await page.getByLabel("تأكيد كلمة المرور").fill(TEACHER1_NEW_PASSWORD);
  await page.getByRole("button", { name: "حفظ كلمة المرور" }).click();

  // يدخل مدرسته (الوحيدة) مباشرة
  await expect(page.getByTestId("active-school-name")).toHaveText("ثانوية الأندلس", {
    timeout: 15_000,
  });
  await expect(page.getByTestId("user-roles")).toHaveText("معلم");
});

test("existing multi-school teacher: B imports same mobile → invitation → accept → both schools", async ({
  page,
}) => {
  const m = meta();
  // منى مديرة B تستورد نفس جوال المعلم 1
  await login(page, "0550000006", PASSWORD);
  await selectSchool(page, "مدارس الرواد");
  await runStaffImport(page, "staff-b.xlsx");
  // النتيجة: حساب جديد واحد (معلم 3) ودعوة واحدة (معلم 1)
  await expect(page.getByTestId("staff-import-result")).toContainText("حسابات جديدة: 1");
  await expect(page.getByTestId("staff-import-result")).toContainText("دعوات أرسلت: 1");
  await page.getByRole("button", { name: "تسجيل الخروج" }).click();

  // المعلم 1 يدخل بكلمته الجديدة (غيرها في الاختبار السابق)
  await login(page, m.teacher1_mobile, TEACHER1_NEW_PASSWORD);
  // لديه مدرسة فعالة واحدة → دخل مباشرة (ننتظر استقرار الجلسة قبل التنقل)
  await expect(page.getByTestId("active-school-name")).toHaveText("ثانوية الأندلس", {
    timeout: 15_000,
  });
  // الدعوة تظهر في شاشة الاختيار
  await page.goto("/select-school");
  const invitations = page.getByTestId("invitations-section");
  await expect(invitations).toContainText("مدارس الرواد");
  await invitations.getByRole("button", { name: "قبول" }).click();

  // المدرستان متاحتان الآن
  await expect(page.getByTestId("invitations-section")).not.toBeVisible();
  await expect(page.locator("li", { hasText: "ثانوية الأندلس" })).toBeVisible();
  await expect(page.locator("li", { hasText: "مدارس الرواد" })).toBeVisible();

  // الدخول إلى B والتبديل إلى A — الأدوار صحيحة
  await selectSchool(page, "مدارس الرواد");
  await expect(page.getByTestId("user-roles")).toHaveText("معلم");
  await page.getByRole("button", { name: /مدارس الرواد/ }).first().click();
  await page.getByRole("button", { name: /ثانوية الأندلس/ }).click();
  await expect(page.getByTestId("active-school-name")).toHaveText("ثانوية الأندلس");
});

test("counselor imported as teacher keeps both roles", async ({ page }) => {
  // منى مديرة C تستورد فهد المرشد كمعلم
  await login(page, "0550000006", PASSWORD);
  await selectSchool(page, "ثانوية المستقبل");
  await page.goto("/staff/import");
  await page.getByTestId("staff-file-input").setInputFiles(resolve(FIXTURES, "staff-c.xlsx"));
  await page.getByRole("button", { name: "رفع الملف" }).click();
  await page.getByRole("button", { name: "بدء التحليل" }).click();
  await expect(page.getByRole("tab", { name: /معلمون جدد/ })).toBeVisible({ timeout: 30_000 });
  await page.getByRole("button", { name: "متابعة إلى التأكيد" }).click();
  await page.getByRole("button", { name: "اعتماد الاستيراد" }).click();
  await expect(page.getByTestId("staff-import-result")).toBeVisible({ timeout: 30_000 });
  await page.getByRole("button", { name: "تسجيل الخروج" }).click();

  // فهد: دوراه معًا في مدرسته
  await login(page, "0550000004", PASSWORD);
  await expect(page.getByTestId("active-school-name")).toHaveText("ثانوية المستقبل");
  await expect(page.getByTestId("user-roles")).toContainText("المرشد الطلابي");
  await expect(page.getByTestId("user-roles")).toContainText("معلم");
});

test("isolation: manager in A is teacher in B — staff import blocked in B", async ({
  page,
}) => {
  await login(page, "0550000002", PASSWORD);
  await selectSchool(page, "ثانوية الأندلس");
  await expect(page.getByRole("link", { name: "الموظفون" })).toBeVisible();

  await page.getByRole("button", { name: /ثانوية الأندلس/ }).click();
  await page.getByRole("button", { name: /مدارس الرواد/ }).click();
  await expect(page.getByTestId("active-school-name")).toHaveText("مدارس الرواد");
  await expect(page.getByRole("link", { name: "الموظفون" })).not.toBeVisible();

  const status = await page.evaluate(async () => {
    const csrf = document.cookie
      .split("; ")
      .find((c) => c.startsWith("csrftoken="))
      ?.split("=")[1];
    const response = await fetch("/api/v1/staff-imports/", {
      method: "POST",
      credentials: "include",
      headers: { "X-CSRFToken": csrf ?? "" },
    });
    return response.status;
  });
  expect(status).toBe(403);
});
