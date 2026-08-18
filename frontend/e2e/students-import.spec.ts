/** E2E المرحلة 4 — استيراد نور الحقيقي عبر Celery worker داخل Docker.
 *  يتطلب: docker compose up (كل الخدمات) + seed_dev.
 *  الـ fixtures تولد بهويات فريدة لكل تشغيل (global-setup) — النتائج حتمية.
 */

import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test, type Page } from "@playwright/test";

const PASSWORD = process.env.E2E_SEED_PASSWORD ?? "E2e-Dev-2026!pass";
const FIXTURES = resolve(dirname(fileURLToPath(import.meta.url)), "fixtures");

// «التحديث» يعتمد على اكتمال «الأساس» — تسلسل إلزامي
test.describe.configure({ mode: "serial" });

interface Meta {
  tag: string;
  first_student: string;
  moved_student: string;
  missing_student: string;
  new_student: string;
  first_nid_last4: string;
  first_nid_full: string;
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

async function runImport(page: Page, fixtureFile: string) {
  await page.goto("/students/import");
  await page.getByTestId("import-file-input").setInputFiles(resolve(FIXTURES, fixtureFile));
  await page.getByRole("button", { name: "رفع الملف" }).click();
  await expect(page.getByText("مطابقة الأعمدة")).toBeVisible();
  await page.getByRole("button", { name: "بدء التحليل" }).click();
  // انتظار الـ worker الحقيقي (polling)
  await expect(page.getByRole("tab", { name: /جدد/ })).toBeVisible({ timeout: 30_000 });
}

test("full Noor import journey: upload → map → preview → commit → students list", async ({
  page,
}) => {
  const m = meta();
  await loginManagerToAndalus(page);

  await runImport(page, "noor-1.xlsx");
  await expect(page.getByRole("tab", { name: "جدد (8)" })).toBeVisible();

  await page.getByRole("button", { name: "متابعة إلى التأكيد" }).click();
  await expect(page.getByTestId("confirm-summary")).toContainText("سيتم إنشاء 8 طالبًا");
  await page.getByRole("button", { name: "اعتماد الاستيراد" }).click();

  await expect(page.getByTestId("import-result")).toContainText("طلاب جدد: 8", {
    timeout: 30_000,
  });
  await page.getByRole("button", { name: "عرض الطلاب" }).click();

  // القائمة: الاسم + هوية مقنعة فقط (لا رقم كامل)
  await page.getByLabel("بحث بالاسم").fill(m.first_student);
  const row = page.locator("tr", { hasText: m.first_student });
  await expect(row).toBeVisible();
  await expect(row).toContainText(`******${m.first_nid_last4}`);
  const bodyText = await page.getByTestId("students-table-body").innerText();
  expect(bodyText).not.toContain(m.first_nid_full);

  // البحث الدقيق بالهوية الكاملة يعمل (HMAC)
  await page.getByLabel("بحث بالاسم").fill("");
  await page.getByLabel(/بحث برقم الهوية/).fill(m.first_nid_full);
  await expect(page.locator("tr", { hasText: m.first_student })).toBeVisible();

  // إعادة التحميل — البيانات ثابتة
  await page.reload();
  await page.getByLabel("بحث بالاسم").fill(m.first_student);
  await expect(page.locator("tr", { hasText: m.first_student })).toBeVisible();
});

test("update import: section move + newcomer + missing student preserved", async ({
  page,
}) => {
  const m = meta();
  await loginManagerToAndalus(page);

  await runImport(page, "noor-2.xlsx");
  await expect(page.getByRole("tab", { name: "انتقال فصل (1)" })).toBeVisible();
  await expect(page.getByRole("tab", { name: "جدد (1)" })).toBeVisible();
  await expect(page.getByRole("tab", { name: "بلا تغيير (6)" })).toBeVisible();
  // العدد يشمل طلاب تشغيلات سابقة متراكمة — نتحقق من وجود التنبيه لا من الرقم الحرفي
  await expect(page.getByText(/موجودون في النظام وغير موجودين في الملف الجديد/)).toBeVisible();

  await page.getByRole("button", { name: "متابعة إلى التأكيد" }).click();
  await page.getByRole("button", { name: "اعتماد الاستيراد" }).click();
  await expect(page.getByTestId("import-result")).toContainText("تغييرات فصول: 1", {
    timeout: 30_000,
  });

  // المنقول أصبح في الفصل 2، والجديد ظهر، والمفقود لم يحذف
  await page.goto("/students");
  await page.getByLabel("بحث بالاسم").fill(m.moved_student);
  await expect(page.locator("tr", { hasText: m.moved_student })).toContainText("2");

  await page.getByLabel("بحث بالاسم").fill(m.new_student);
  await expect(page.locator("tr", { hasText: m.new_student })).toBeVisible();

  await page.getByLabel("بحث بالاسم").fill(m.missing_student);
  await expect(page.locator("tr", { hasText: m.missing_student })).toBeVisible();
});

test("tenant roles: manager in A is teacher in B — no students access in B", async ({
  page,
}) => {
  await loginManagerToAndalus(page);
  await expect(page.getByRole("link", { name: "الطلاب" })).toBeVisible();

  // التبديل إلى مدارس الرواد (معلم فقط)
  await page.getByRole("button", { name: /ثانوية الأندلس/ }).click();
  await page.getByRole("button", { name: /مدارس الرواد/ }).click();
  await expect(page.getByTestId("active-school-name")).toHaveText("مدارس الرواد");
  await expect(page.getByRole("link", { name: "الطلاب" })).not.toBeVisible();

  // محاولة API مباشرة: قائمة الطلاب والاستيراد كلاهما 403
  const statuses = await page.evaluate(async () => {
    const csrf = document.cookie
      .split("; ")
      .find((c) => c.startsWith("csrftoken="))
      ?.split("=")[1];
    const list = await fetch("/api/v1/students/", { credentials: "include" });
    const upload = await fetch("/api/v1/student-imports/", {
      method: "POST",
      credentials: "include",
      headers: { "X-CSRFToken": csrf ?? "" },
    });
    return { list: list.status, upload: upload.status };
  });
  expect(statuses.list).toBe(403);
  expect(statuses.upload).toBe(403);
});
