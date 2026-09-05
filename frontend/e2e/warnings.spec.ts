/** E2E المرحلة 11 — قواعد الإنذارات والاستحقاق والإصدار (ضد Docker حقيقي).
 *
 * السيناريوهات الإلزامية (البنود 126-132، 152-154):
 * 1) 3 أيام غياب كامل بدون عذر → المستوى الأول مستحق → الوكيل يصدر → يظهر في الملف.
 * 2) 5 أيام → المستوى الثاني مستحق مع بقاء الأول صادرًا → إصدار الثاني.
 * 3) اعتماد عذر ليومين → القيمة الحالية تنخفض والإنذار يبقى (عند الإصدار 5 / حاليًا 3).
 * 4) 3 تأخرات صباحية → إنذار تأخر مستقل (لا يخلط بتأخر الحصص).
 * 5) تغيير القواعد يعيد التقييم ولا يمس الإنذارات الصادرة.
 * 6) العزل: مدير A لا يصل لإنذارات B.
 *
 * صف/فصل فريد لكل تشغيل (noor-8) يعزل العدادات عن بقية بيانات المدرسة.
 */

import { execSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test, type Page } from "@playwright/test";
import { COMPOSE } from "./compose";

const PASSWORD = process.env.E2E_SEED_PASSWORD ?? "E2e-Dev-2026!pass";
const FIXTURES = resolve(dirname(fileURLToPath(import.meta.url)), "fixtures");
const PROJECT_ROOT = resolve(FIXTURES, "..", "..", "..");

test.describe.configure({ mode: "serial", timeout: 300_000 });

interface Meta {
  warnings_grade: string;
  warnings_section: string;
  warnings_students: string[]; // فيصل، بندر
}

function meta(): Meta {
  return JSON.parse(readFileSync(resolve(FIXTURES, "meta.json"), "utf-8")) as Meta;
}

interface SeedOutput {
  date: string;
  sections: Record<
    string,
    { sessions: Record<string, number>; students: Record<string, number> }
  >;
}

let studentIds: Record<string, number> = {};
let daySeqs: number[] = [];
let seededDays: string[] = [];

async function api<T>(
  page: Page,
  path: string,
  init: { method?: string; body?: unknown } = {},
): Promise<{ status: number; body: T }> {
  return page.evaluate(
    async ({ path, init }) => {
      const csrf = document.cookie
        .split("; ")
        .find((c) => c.startsWith("csrftoken="))
        ?.split("=")[1];
      const response = await fetch(`/api/v1${path}`, {
        method: init.method ?? "GET",
        credentials: "include",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrf ?? "" },
        body: init.body ? JSON.stringify(init.body) : undefined,
      });
      const text = await response.text();
      return { status: response.status, body: text ? JSON.parse(text) : null };
    },
    { path, init },
  );
}

/** يبذر يوم غياب كامل في تاريخ محدد — بحصص ذلك اليوم نفسه.
 *  لكل يوم سياق مجمد خاص (م8) وقد يختلف عدد حصصه، فالغياب الكامل يتطلب تغطية
 *  كل حصص اليوم المعني لا حصص اليوم الحالي. */
function seedAbsenceDay(
  sectionCode: string,
  day: string,
  absent: string[],
  sequences: number[],
): SeedOutput {
  const plan = {
    school: "school-a",
    date: day,
    sections: [
      { code: sectionCode, periods: sequences.map((sequence) => ({ sequence, absent })) },
    ],
  };
  const stdout = execSync(
    `${COMPOSE} exec -T backend python manage.py seed_attendance_sessions --allow-production-like`,
    { input: JSON.stringify(plan), cwd: PROJECT_ROOT, encoding: "utf-8" },
  );
  return JSON.parse(stdout.trim().split("\n").pop() ?? "{}") as SeedOutput;
}

async function login(page: Page, mobile: string, school: string) {
  await page.goto("/");
  await page.getByLabel("رقم الجوال").fill(mobile);
  await page.getByLabel("كلمة المرور", { exact: true }).fill(PASSWORD);
  await page.getByRole("button", { name: "تسجيل الدخول" }).click();
  const chooser = page
    .locator("li", { hasText: school })
    .getByRole("button", { name: "دخول" });
  await chooser.click({ timeout: 4000 }).catch(() => undefined);
  await expect(page.getByTestId("active-school-name")).toHaveText(school);
}

async function logout(page: Page) {
  await page.getByRole("button", { name: "تسجيل الخروج" }).click();
  await expect(page.getByLabel("رقم الجوال")).toBeVisible({ timeout: 30_000 });
}

async function setRules(page: Page, one: number, two: number, three: number) {
  const { status } = await api(page, "/warning-rules/", {
    method: "PATCH",
    body: {
      UNEXCUSED_FULL_DAY_ABSENCE: {
        is_enabled: true,
        levels: { LEVEL_1: one, LEVEL_2: two, LEVEL_3: three },
      },
      MORNING_LATE_OCCURRENCES: {
        is_enabled: true,
        levels: { LEVEL_1: 3, LEVEL_2: 5, LEVEL_3: 10 },
      },
    },
  });
  expect(status).toBe(200);
}

function studentRow(page: Page, name: string) {
  return page.locator('[data-testid^="row-"]', { hasText: name });
}

test("absence warnings: level 1 then level 2, excuse lowers current metric only", async ({
  page,
}) => {
  const m = meta();
  const [faisal] = m.warnings_students;
  await login(page, "0550000002", "ثانوية الأندلس");

  // استيراد فصل الإنذارات
  await page.goto("/students/import");
  await page.getByTestId("import-file-input").setInputFiles(resolve(FIXTURES, "noor-8.xlsx"));
  await page.getByRole("button", { name: "رفع الملف" }).click();
  await expect(page.getByText("مطابقة الأعمدة")).toBeVisible();
  await page.getByRole("button", { name: "بدء التحليل" }).click();
  await expect(page.getByRole("tab", { name: /جدد/ })).toBeVisible({ timeout: 30_000 });
  await page.getByRole("button", { name: "متابعة إلى التأكيد" }).click();
  await page.getByRole("button", { name: "اعتماد الاستيراد" }).click();
  await expect(page.getByTestId("import-result")).toBeVisible({ timeout: 30_000 });

  const daily = await api<{ date: string; day_periods: { sequence: number }[] }>(
    page,
    "/attendance/analytics/daily/",
  );
  daySeqs = daily.body.day_periods.map((p) => p.sequence);
  expect(daySeqs.length).toBeGreaterThanOrEqual(3);

  // خمسة أيام دراسية سابقة (اليوم وما قبله) — نبدأ بثلاثة
  const today = new Date(daily.body.date);
  const dayIso = (offset: number) => {
    const d = new Date(today);
    d.setDate(d.getDate() - offset);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  };
  seededDays = [0, 1, 2, 3, 4].map(dayIso);

  const periodsFor = async (day: string) => {
    const { body } = await api<{ day_periods: { sequence: number }[] }>(
      page, `/attendance/analytics/daily/?date=${day}`,
    );
    return body.day_periods.map((p) => p.sequence);
  };

  let seeded: SeedOutput | null = null;
  for (const day of seededDays.slice(0, 3)) {
    seeded = seedAbsenceDay(m.warnings_section, day, [faisal], await periodsFor(day));
  }
  studentIds = seeded!.sections[m.warnings_section].students;
  const faisalId = studentIds[faisal];

  await setRules(page, 3, 5, 10);

  // (1) المستوى الأول مستحق — من واجهة الوكيل
  await logout(page);
  await login(page, "0550000003", "ثانوية الأندلس");
  await page.goto("/warnings");
  await page.getByTestId("type-filter").selectOption("UNEXCUSED_FULL_DAY_ABSENCE");
  const row = studentRow(page, faisal);
  await expect(row).toBeVisible({ timeout: 20_000 });
  await expect(row).toContainText("3 أيام");
  await expect(row).toContainText("وصل: الإنذار الأول");

  await row.getByRole("button", { name: /إصدار الإنذار الأول/ }).click();
  await expect(page.getByTestId("issue-result")).toContainText("الإنذار الأول");

  // يظهر في ملف الطالب
  await page.goto(`/students/${faisalId}/attendance`);
  await page.getByRole("button", { name: "الإنذارات" }).click();
  await expect(page.getByTestId("student-warnings-tab")).toContainText("إنذارات الغياب: 1");
  await expect(page.getByTestId("student-warnings-tab")).toContainText("صدر عند 3 أيام");

  // (2) يومان إضافيان → المستوى الثاني مستحق والأول يبقى صادرًا
  for (const day of seededDays.slice(3, 5)) {
    seedAbsenceDay(m.warnings_section, day, [faisal], await periodsFor(day));
  }
  await page.goto("/warnings");
  await page.getByTestId("type-filter").selectOption("UNEXCUSED_FULL_DAY_ABSENCE");
  const row2 = studentRow(page, faisal);
  await expect(row2).toContainText("5 أيام", { timeout: 20_000 });
  await expect(row2).toContainText("صدر: الإنذار الأول");
  await expect(
    row2.getByRole("button", { name: /إصدار الإنذار الأول/ }),
  ).toHaveCount(0); // الصادر لا يعاد إصداره
  await row2.getByRole("button", { name: /إصدار الإنذار الثاني/ }).click();
  await expect(page.getByTestId("issue-result")).toContainText("الإنذار الثاني");

  // (3) عذر ليومين → القيمة الحالية 3 والإنذار يبقى عند 5
  const excuse = await api<{ id: number }>(page, "/excuses/", {
    method: "POST",
    body: {
      student_id: faisalId,
      reason_type: "MEDICAL_REPORT",
      notes: "تقرير طبي",
      targets: seededDays.slice(0, 2).map((day) => ({ attendance_date: day })),
    },
  });
  expect(excuse.status).toBe(201);
  const preview = await api<{ preview_hash: string }>(
    page, `/excuses/${excuse.body.id}/preview/`, { method: "POST" },
  );
  expect(preview.status).toBe(200);
  const approved = await api(page, `/excuses/${excuse.body.id}/approve/`, {
    method: "POST",
    body: { preview_hash: preview.body.preview_hash },
  });
  expect(approved.status).toBe(200);

  await page.goto(`/students/${faisalId}/attendance`);
  await page.getByRole("button", { name: "الإنذارات" }).click();
  const level2 = page.locator('[data-testid^="warning-"]', { hasText: "الإنذار الثاني" });
  await expect(level2).toBeVisible();
  await level2.getByRole("button", { name: "التفاصيل" }).click();
  const detail = page.locator('[data-testid^="detail-"]').first();
  await expect(detail).toContainText("عند الإصدار: 5");
  await expect(detail).toContainText("حاليًا: 3");
  await expect(detail).toContainText("الإنذار يبقى كما صدر");
});

test("morning late warning is independent from period late", async ({ page }) => {
  const m = meta();
  const [, bandar] = m.warnings_students;
  await login(page, "0550000002", "ثانوية الأندلس");

  const bandarId = studentIds[bandar];
  expect(bandarId).toBeTruthy();

  // ثلاث حالات تأخر صباحي عبر تسجيل يدوي (وكيل/مدير) — بلا أي تأخر حصص
  for (const day of seededDays.slice(0, 3)) {
    const response = await api(page, "/morning/arrivals/", {
      method: "POST",
      body: {
        student_id: bandarId,
        date: day,
        arrival_time: "07:40",
        reason: "تأخر صباحي E2E",
      },
    });
    expect([201, 409]).toContain(response.status);
  }

  await page.goto("/warnings");
  await page.getByTestId("type-filter").selectOption("MORNING_LATE_OCCURRENCES");
  const row = studentRow(page, bandar);
  await expect(row).toBeVisible({ timeout: 20_000 });
  await expect(row).toContainText("3 مرات");
  await row.getByRole("button", { name: /إصدار الإنذار الأول/ }).click();
  await expect(page.getByTestId("issue-result")).toContainText("الإنذار الأول");

  // ملف الطالب: إنذار تأخر واحد ولا إنذار غياب
  await page.goto(`/students/${bandarId}/attendance`);
  await page.getByRole("button", { name: "الإنذارات" }).click();
  await expect(page.getByTestId("warnings-summary")).toContainText("إنذارات الغياب: 0");
  await expect(page.getByTestId("warnings-summary")).toContainText("إنذارات التأخر: 1");
});

test("rule change re-evaluates eligibility without touching issued warnings", async ({
  page,
}) => {
  const m = meta();
  const [faisal] = m.warnings_students;
  const faisalId = studentIds[faisal];
  await login(page, "0550000002", "ثانوية الأندلس");

  // الحدود 2/4/7 → القيمة الحالية 3 (بعد العذر) تبلغ المستوى الأول الجديد فقط،
  // وهو صادر مسبقًا؛ فلا مستوى مستحق ويختفي من فلتر «مستحق» — نراه بفلتر «الكل»
  await setRules(page, 2, 4, 7);
  await page.goto("/warnings");
  await page.getByTestId("type-filter").selectOption("UNEXCUSED_FULL_DAY_ABSENCE");
  await page.getByTestId("status-filter").selectOption("all");
  const row = studentRow(page, faisal);
  await expect(row).toContainText("3 أيام", { timeout: 20_000 });
  await expect(row).toContainText("وصل: الإنذار الأول"); // أعيد التقييم بالحدود الجديدة
  await expect(row.getByRole("button", { name: /إصدار/ })).toHaveCount(0);

  // الإنذارات الصادرة لم تتغير: الثاني ما زال «صدر عند 5» والحد 5
  await page.goto(`/students/${faisalId}/attendance`);
  await page.getByRole("button", { name: "الإنذارات" }).click();
  const level2 = page.locator('[data-testid^="warning-"]', { hasText: "الإنذار الثاني" });
  await expect(level2).toContainText("صدر عند 5 أيام");
  await expect(level2).toContainText("الحد 5");

  // إعادة الحدود الافتراضية لبقية التشغيلات
  await setRules(page, 3, 5, 10);
});

test("isolation: manager in another school sees no warnings or rules leakage", async ({
  page,
}) => {
  const m = meta();
  const [faisal] = m.warnings_students;
  // منى مديرة في مدارس الرواد (مدرسة أخرى)
  await login(page, "0550000006", "مدارس الرواد");

  await page.goto("/warnings");
  await expect(page.getByTestId("warning-kpis")).toBeVisible({ timeout: 20_000 });
  await expect(page.locator('[data-testid^="row-"]', { hasText: faisal })).toHaveCount(0);

  const warnings = await api<{ count: number }>(page, "/warnings/");
  expect(warnings.body.count).toBe(0);

  // إصدار لطالب مدرسة أخرى → 404
  const issue = await api(page, "/warnings/issue/", {
    method: "POST",
    body: {
      student_id: studentIds[faisal],
      warning_type: "UNEXCUSED_FULL_DAY_ABSENCE",
      level: "LEVEL_1",
    },
  });
  expect(issue.status).toBe(404);
});
