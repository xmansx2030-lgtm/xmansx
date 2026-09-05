/** E2E المرحلة 7 — لوحة متابعة التحضير (ضد Docker حقيقي، بلا mock للساعة).
 *
 * التحكم الزمني: جدول التطوير 24 حصة × ساعة، والاختبار يضبط مهلة التنبيه عبر
 * إعدادات المدرسة حول وقت الخادم الحقيقي (مرتفعة = في الوقت، 1 دقيقة = متأخر).
 * صف فريد لكل تشغيل + فلتر الصف يعزل العدادات (KPIs تتبع الفلاتر — سلوك موثق).
 * دورة الحياة كلها اختبار واحد متسلسل حتى لا يقطعها تبدل الحصة على رأس الساعة،
 * مع حارس بداية ينتظر الحصة التالية لو كنا قرب نهايتها (نادر ومحدود).
 */

import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test, type Browser, type Page } from "@playwright/test";

const PASSWORD = process.env.E2E_SEED_PASSWORD ?? "E2e-Dev-2026!pass";
const FIXTURES = resolve(dirname(fileURLToPath(import.meta.url)), "fixtures");

test.describe.configure({ mode: "serial", timeout: 600_000 });

interface Meta {
  monitoring_grade: string;
  monitoring_sections: string[];
}

function meta(): Meta {
  return JSON.parse(readFileSync(resolve(FIXTURES, "meta.json"), "utf-8")) as Meta;
}

async function login(page: Page, mobile: string, school: string) {
  await page.goto("/");
  await page.getByLabel("رقم الجوال").fill(mobile);
  await page.getByLabel("كلمة المرور", { exact: true }).fill(PASSWORD);
  await page.getByRole("button", { name: "تسجيل الدخول" }).click();
  // متعدد المدارس يرى شاشة الاختيار؛ الوكيل سعد يدخل تلقائيًا
  const chooser = page.locator("li", { hasText: school }).getByRole("button", { name: "دخول" });
  await chooser.click({ timeout: 4000 }).catch(() => undefined);
  await expect(page.getByTestId("active-school-name")).toHaveText(school);
}

/** يضبط مهلة التنبيه عبر API الإعدادات من جلسة المدير المفتوحة. */
async function setAlertMinutes(managerPage: Page, minutes: number) {
  const status = await managerPage.evaluate(async (value) => {
    const csrf = document.cookie
      .split("; ")
      .find((c) => c.startsWith("csrftoken="))
      ?.split("=")[1];
    const res = await fetch("/api/v1/school/settings/", {
      method: "PATCH",
      credentials: "include",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf ?? "" },
      body: JSON.stringify({ unprepared_period_alert_minutes: value }),
    });
    return res.status;
  }, minutes);
  expect(status).toBe(200);
}

/** دقائق منقضية من بداية الحصة — من نص وقت الخادم (لا ساعة الجهاز ولا منطقة المتصفح). */
async function elapsedMinutes(page: Page): Promise<number> {
  return page.evaluate(async () => {
    const res = await fetch("/api/v1/attendance/monitoring/current/", {
      credentials: "include",
    });
    const body = (await res.json()) as {
      school_time: string;
      period: { start_time: string } | null;
    };
    if (!body.period) throw new Error("no current period");
    // school_time بصيغة ISO بمنطقة المدرسة: "2026-08-19T09:01:23+03:00"
    const nowMinutes =
      Number(body.school_time.slice(11, 13)) * 60 + Number(body.school_time.slice(14, 16));
    const [h, m] = body.period.start_time.split(":").map(Number);
    return nowMinutes - (h * 60 + m);
  });
}

async function sectionIdByName(page: Page, name: string): Promise<number> {
  const id = await page.evaluate(async (sectionName) => {
    const res = await fetch("/api/v1/attendance/sections/", { credentials: "include" });
    const sections = (await res.json()) as { id: number; name: string }[];
    return sections.find((s) => s.name === sectionName)?.id ?? 0;
  }, name);
  expect(id).toBeGreaterThan(0);
  return id;
}

async function openMonitoringFiltered(page: Page, grade: string) {
  await page.goto("/attendance/monitoring");
  await expect(page.getByTestId("monitoring-period")).toBeVisible();
  await page.getByTestId("grade-filter").selectOption({ label: grade });
}

function sectionRow(page: Page, name: string) {
  return page.locator('[data-testid^="monitoring-section-"]', { hasText: name });
}

/** معلم يفتح فصلًا (يبدأ جلسة) — ويعتمده إن طلب. */
async function teacherOpenSection(page: Page, sectionName: string, submit: boolean) {
  const id = await sectionIdByName(page, sectionName);
  await page.goto(`/attendance/section/${id}`);
  await expect(page.getByTestId("roster-list")).toBeVisible();
  if (submit) {
    await page.getByTestId("submit-attendance").click();
    await expect(page.getByTestId("submitted-banner")).toBeVisible({ timeout: 15_000 });
  }
}

async function teacherContext(browser: Browser) {
  const context = await browser.newContext();
  const page = await context.newPage();
  await login(page, "0550000001", "ثانوية الأندلس");
  return { context, page };
}

test("monitoring lifecycle: before threshold → overdue → late submission via polling", async ({
  page,
  browser,
}) => {
  const m = meta();
  await login(page, "0550000002", "ثانوية الأندلس");

  // حارس نهاية الحصة: لو بقي أقل من ~5 دقائق ننتظر الحصة التالية (جسم الاختبار ~3 دقائق)
  let elapsed = await elapsedMinutes(page);
  while (elapsed > 55) {
    await page.waitForTimeout(30_000);
    elapsed = await elapsedMinutes(page);
  }

  // استيراد فصول المتابعة الثلاثة (صف فريد لهذا التشغيل)
  await page.goto("/students/import");
  await page.getByTestId("import-file-input").setInputFiles(resolve(FIXTURES, "noor-5.xlsx"));
  await page.getByRole("button", { name: "رفع الملف" }).click();
  await expect(page.getByText("مطابقة الأعمدة")).toBeVisible();
  await page.getByRole("button", { name: "بدء التحليل" }).click();
  await expect(page.getByRole("tab", { name: /جدد/ })).toBeVisible({ timeout: 30_000 });
  await page.getByRole("button", { name: "متابعة إلى التأكيد" }).click();
  await page.getByRole("button", { name: "اعتماد الاستيراد" }).click();
  await expect(page.getByTestId("import-result")).toBeVisible({ timeout: 30_000 });

  // (1) مهلة أعلى من المنقضي → كل شيء «في الوقت»؛ المعلم يعتمد M1 الآن
  // (‏snapshot المهلة المرتفعة يجعل اعتماده «في الوقت» للأبد — البند 36)
  elapsed = await elapsedMinutes(page);
  await setAlertMinutes(page, Math.min(120, elapsed + 45));
  const teacher1 = await teacherContext(browser);
  await teacherOpenSection(teacher1.page, m.monitoring_sections[0], true);
  await teacher1.context.close();

  await openMonitoringFiltered(page, m.monitoring_grade);
  await expect(page.getByTestId("kpi-total")).toContainText("3");
  await expect(page.getByTestId("kpi-submitted")).toContainText("1");
  await expect(page.getByTestId("kpi-not-started")).toContainText("2");
  await expect(page.getByTestId("kpi-overdue")).toContainText("0");
  await expect(sectionRow(page, m.monitoring_sections[0])).toContainText("✅ تم التحضير");
  await expect(sectionRow(page, m.monitoring_sections[1])).toContainText("لم يبدأ");

  // (2) مهلة دقيقة واحدة — وجلسة M2 تبدأ بعد الخفض (snapshot=1) → متأخرة
  await setAlertMinutes(page, 1);
  elapsed = await elapsedMinutes(page);
  while (elapsed < 2) {
    await page.waitForTimeout(15_000);
    elapsed = await elapsedMinutes(page);
  }
  const teacher2 = await teacherContext(browser);
  await teacherOpenSection(teacher2.page, m.monitoring_sections[1], false);

  // الوكيل سعد يرى: المعتمد باقٍ في الوقت، وقيد التحضير ولم يبدأ متأخران
  const vpContext = await browser.newContext();
  const vp = await vpContext.newPage();
  await login(vp, "0550000003", "ثانوية الأندلس");
  await openMonitoringFiltered(vp, m.monitoring_grade);
  await expect(vp.getByTestId("kpi-overdue")).toContainText("2");
  await expect(sectionRow(vp, m.monitoring_sections[0])).toContainText("✅ تم التحضير");
  await expect(sectionRow(vp, m.monitoring_sections[1])).toContainText(
    "بدأ ولم يعتمد — متأخر",
  );
  await expect(sectionRow(vp, m.monitoring_sections[2])).toContainText(
    "لم يتم التحضير — متأخر",
  );

  // (3) الاعتماد المتأخر يظهر على لوحة الوكيل المفتوحة عبر الاستطلاع الحقيقي (20 ث)
  await teacherOpenSection(teacher2.page, m.monitoring_sections[1], true);
  await teacher2.context.close();
  await expect(sectionRow(vp, m.monitoring_sections[1])).toContainText("تم التحضير متأخرًا", {
    timeout: 30_000,
  });
  await expect(sectionRow(vp, m.monitoring_sections[1])).toContainText("دقيقة");
  await expect(vp.getByTestId("kpi-submitted")).toContainText("2");
  await expect(vp.getByTestId("kpi-in-progress")).toContainText("0");
  await expect(vp.getByTestId("kpi-overdue")).toContainText("2"); // المعتمد متأخرًا يبقى متأخرًا
  await vpContext.close();
});

test("isolation: teacher role in school B gets no dashboard, link, or data", async ({
  page,
}) => {
  // خالد مدير في A ومعلم في B
  await login(page, "0550000002", "ثانوية الأندلس");
  const primaryNavigation = page.getByRole("navigation", { name: "التنقل الرئيسي" });
  await expect(
    primaryNavigation.getByRole("link", { name: "متابعة التحضير" }),
  ).toBeVisible();

  await page.getByRole("button", { name: "ثانوية الأندلس" }).click();
  await page.getByRole("listbox").getByRole("button", { name: /مدارس الرواد/ }).click();
  await expect(page.getByTestId("active-school-name")).toHaveText("مدارس الرواد");

  await expect(
    primaryNavigation.getByRole("link", { name: "متابعة التحضير" }),
  ).not.toBeVisible();
  await page.goto("/attendance/monitoring");
  await expect(page.getByRole("alert")).toContainText("صلاحية");

  const status = await page.evaluate(async () => {
    const res = await fetch("/api/v1/attendance/monitoring/current/", {
      credentials: "include",
    });
    return res.status;
  });
  expect(status).toBe(403);
});
