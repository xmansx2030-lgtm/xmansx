/** E2E المرحلة 8 — تحليلات الغياب (ضد Docker حقيقي).
 *
 * لا يمكن فتح جلسات إلا للحصة الحالية عبر الواجهة، بينما تحتاج التحليلات بيانات
 * عدة حصص لليوم — تبذر عبر أمر إدارة DEBUG-only (‏seed_attendance_sessions) بنفس
 * النماذج والخدمات، ثم تفحص النتائج من واجهة الوكيل الحقيقية.
 * صف فريد لكل تشغيل + فلتر الصف يعزل النتائج عن بقية بيانات المدرسة.
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

test.describe.configure({ mode: "serial", timeout: 240_000 });

interface Meta {
  analytics_grade: string;
  analytics_section_1: string;
  analytics_section_2: string;
  analytics_students_1: string[]; // محمد، خالد، سعد
  analytics_students_2: string[]; // فهد، عمر
}

function meta(): Meta {
  return JSON.parse(readFileSync(resolve(FIXTURES, "meta.json"), "utf-8")) as Meta;
}

interface SeedOutput {
  sections: Record<
    string,
    { sessions: Record<string, number>; students: Record<string, number> }
  >;
}

let seeded: SeedOutput | null = null;
// تسلسلات حصص اليوم كما جمدها سياق اليوم — لا افتراض لعددها أو أرقامها
let daySeqs: number[] = [];

async function fetchDaySequences(page: Page): Promise<number[]> {
  return page.evaluate(async () => {
    const res = await fetch("/api/v1/attendance/analytics/daily/", {
      credentials: "include",
    });
    const body = (await res.json()) as { day_periods: { sequence: number }[] };
    return body.day_periods.map((p) => p.sequence);
  });
}

function seedSessions(m: Meta, sequences: number[]): SeedOutput {
  const [mohammed, khaled, saad] = m.analytics_students_1;
  const [fahd] = m.analytics_students_2;
  const [first, second] = sequences;
  const t1Periods = sequences.map((seq) => {
    if (seq === first) return { sequence: seq, absent: [mohammed, khaled, saad] };
    if (seq === second) {
      return { sequence: seq, absent: [mohammed], late: [{ name: saad, minutes: 10 }] };
    }
    return { sequence: seq, absent: [mohammed] };
  });
  const plan = {
    school: "school-a",
    sections: [
      { code: m.analytics_section_1, periods: t1Periods },
      { code: m.analytics_section_2, periods: [{ sequence: first, absent: [fahd] }] },
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
  const chooser = page.locator("li", { hasText: school }).getByRole("button", { name: "دخول" });
  await chooser.click({ timeout: 4000 }).catch(() => undefined);
  await expect(page.getByTestId("active-school-name")).toHaveText(school);
}

async function openAnalytics(page: Page) {
  await page.goto("/attendance/analytics");
  await expect(page.getByTestId("period-selector")).toBeVisible({ timeout: 15_000 });
}

async function runReport(page: Page, m: Meta, sequences: number[], matchAny = false) {
  // إعادة الاختيار من الصفر: التبويب يحدد ثم يعرض
  for (const seq of sequences) {
    const option = page.getByTestId(`period-option-${seq}`);
    if ((await option.getAttribute("aria-pressed")) !== "true") {
      await option.click();
    }
  }
  if (matchAny) {
    await page.getByTestId("match-any").check();
  }
  await page
    .getByTestId("analytics-grade-filter")
    .selectOption({ label: m.analytics_grade });
  await page.getByTestId("run-report").click();
  await expect(page.getByTestId("report-summary")).toBeVisible({ timeout: 15_000 });
}

test("import + seed, then single-period and multi-period reports behave exactly", async ({
  page,
}) => {
  const m = meta();
  await login(page, "0550000002", "ثانوية الأندلس");

  // استيراد فصلي التحليلات
  await page.goto("/students/import");
  await page.getByTestId("import-file-input").setInputFiles(resolve(FIXTURES, "noor-6.xlsx"));
  await page.getByRole("button", { name: "رفع الملف" }).click();
  await expect(page.getByText("مطابقة الأعمدة")).toBeVisible();
  await page.getByRole("button", { name: "بدء التحليل" }).click();
  await expect(page.getByRole("tab", { name: /جدد/ })).toBeVisible({ timeout: 30_000 });
  await page.getByRole("button", { name: "متابعة إلى التأكيد" }).click();
  await page.getByRole("button", { name: "اعتماد الاستيراد" }).click();
  await expect(page.getByTestId("import-result")).toBeVisible({ timeout: 30_000 });

  daySeqs = await fetchDaySequences(page);
  expect(daySeqs.length).toBeGreaterThanOrEqual(3);
  seeded = seedSessions(m, daySeqs);
  expect(Object.keys(seeded.sections)).toHaveLength(2);

  const [mohammed, khaled, saad] = m.analytics_students_1;
  const [fahd, omar] = m.analytics_students_2;

  // (1) حصة محددة: أول حصة — الغائبون الأربعة (T2 معتمد لها فيدخل غائبه)
  await openAnalytics(page);
  await runReport(page, m, [daySeqs[0]]);
  await expect(page.getByTestId("report-summary")).toContainText("4 طالبًا");
  for (const name of [mohammed, khaled, saad, fahd]) {
    await expect(page.getByTestId("analytics-students")).toContainText(name);
  }
  await expect(page.getByTestId("analytics-students")).not.toContainText(omar);

  // (2) عدة حصص: الأولى+الثانية ALL — محمد فقط، وT2 يستبعد ويعلن ناقصًا
  await page.getByRole("tab", { name: "عدة حصص" }).click();
  await runReport(page, m, [daySeqs[0], daySeqs[1]]);
  await expect(page.getByTestId("report-summary")).toContainText("1 طالبًا");
  await expect(page.getByTestId("analytics-students")).toContainText(mohammed);
  await expect(page.getByTestId("analytics-students")).not.toContainText(khaled);
  await expect(page.getByTestId("analytics-students")).not.toContainText(saad); // متأخر ≠ غائب
  await expect(page.getByTestId("analytics-students")).not.toContainText(fahd);
  await expect(page.getByTestId("incomplete-warning")).toContainText(m.analytics_section_2);
  await expect(page.getByTestId("incomplete-warning")).toContainText("لم يتم التحضير");
  // بطاقات الحصص المطلوبة فقط
  const mohammedRow = page.locator('[data-testid^="analytics-student-"]', {
    hasText: mohammed,
  });
  await expect(mohammedRow).toContainText("غائب");

  // (3) إضافة الثالثة — القائمة تتغير فعليًا وفق البيانات (محمد وحده غائب الثلاث)
  await page.getByTestId(`period-option-${daySeqs[2]}`).click();
  await page.getByTestId("run-report").click();
  await expect(page.getByTestId("report-summary")).toContainText("1 طالبًا");
  await expect(mohammedRow).toBeVisible();

  // (4) ‏ANY: الثلاثة غائبون في حصة على الأقل — وT2 الناقص ما زال مستبعدًا
  await page.getByTestId("match-any").check();
  await page.getByTestId("run-report").click();
  await expect(page.getByTestId("report-summary")).toContainText("3 طالبًا");
  await expect(page.getByTestId("analytics-students")).toContainText(khaled);
  await expect(page.getByTestId("analytics-students")).not.toContainText(fahd);
});

test("daily summary: full, partial, incomplete, and late totals", async ({ page }) => {
  const m = meta();
  const [mohammed, khaled, saad] = m.analytics_students_1;
  const [fahd] = m.analytics_students_2;
  await login(page, "0550000003", "ثانوية الأندلس");
  await page.goto("/attendance/analytics");
  await page.getByRole("tab", { name: "ملخص اليوم" }).click();
  await expect(page.getByTestId("daily-kpis")).toBeVisible({ timeout: 15_000 });
  await page.getByTestId("daily-grade-filter").selectOption({ label: m.analytics_grade });

  // غياب يوم كامل: محمد (24/24 معتمدة وكلها غياب)
  await page.getByTestId("daily-status-filter").selectOption("FULL");
  await expect(page.getByTestId("daily-students")).toContainText(mohammed, {
    timeout: 15_000,
  });
  await expect(page.getByTestId("daily-students")).not.toContainText(fahd);

  // غياب جزئي: خالد (حصة) وسعد (حصة + تأخر) — التأخر لا يجعل اليوم غيابًا
  await page.getByTestId("daily-status-filter").selectOption("PARTIAL");
  await expect(page.getByTestId("daily-students")).toContainText(khaled, {
    timeout: 15_000,
  });
  await expect(page.getByTestId("daily-students")).toContainText(saad);
  const saadRow = page.locator('[data-testid^="daily-student-"]', { hasText: saad });
  await expect(saadRow).toContainText("تأخر 1 (10 د)");

  // بيانات غير مكتملة: فهد غائب في كل المسجل لفصله لكن 23 حصة لم تحضر → UNDETERMINED
  await page.getByTestId("daily-status-filter").selectOption("UNDETERMINED");
  await expect(page.getByTestId("daily-students")).toContainText(fahd, {
    timeout: 15_000,
  });
  await expect(page.getByTestId("daily-students")).not.toContainText(mohammed);
});

test("attendance edit updates analytics after refresh", async ({ page }) => {
  const m = meta();
  expect(seeded).not.toBeNull();
  const t1 = seeded!.sections[m.analytics_section_1];
  const [mohammed, khaled, saad] = m.analytics_students_1;

  await login(page, "0550000002", "ثانوية الأندلس");
  // تصحيح إداري حقيقي عبر PATCH: محمد يصبح حاضرًا في الأولى (يبقى خالد وسعد غائبين)
  const status = await page.evaluate(
    async ({ sessionId, marks }) => {
      const csrf = document.cookie
        .split("; ")
        .find((c) => c.startsWith("csrftoken="))
        ?.split("=")[1];
      const res = await fetch(`/api/v1/attendance/sessions/${sessionId}/`, {
        method: "PATCH",
        credentials: "include",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrf ?? "" },
        body: JSON.stringify({ marks, reason: "تصحيح إداري E2E" }),
      });
      return res.status;
    },
    {
      sessionId: t1.sessions[String(daySeqs[0])],
      marks: [
        { student_id: t1.students[khaled], status: "ABSENT" },
        { student_id: t1.students[saad], status: "ABSENT" },
      ],
    },
  );
  expect(status).toBe(200);

  // التحليلات المفتوحة تعكس التعديل بعد إعادة العرض
  await openAnalytics(page);
  await page.getByRole("tab", { name: "عدة حصص" }).click();
  await runReport(page, m, [daySeqs[0], daySeqs[1]]);
  await expect(page.getByTestId("no-matching-students")).toBeVisible(); // محمد لم يعد غائب الأولى

  await page.getByRole("tab", { name: "ملخص اليوم" }).click();
  await expect(page.getByTestId("daily-kpis")).toBeVisible({ timeout: 15_000 });
  await page.getByTestId("daily-grade-filter").selectOption({ label: m.analytics_grade });
  await page.getByTestId("daily-status-filter").selectOption("FULL");
  await expect(page.getByTestId("daily-students")).not.toContainText(mohammed, {
    timeout: 15_000,
  });
  await page.getByTestId("daily-status-filter").selectOption("PARTIAL");
  await expect(page.getByTestId("daily-students")).toContainText(mohammed);
});

test("isolation: teacher role in school B gets no analytics link, page, or API", async ({
  page,
}) => {
  await login(page, "0550000002", "ثانوية الأندلس");
  await expect(page.getByRole("link", { name: "الغياب والحضور" })).toBeVisible();

  await page.getByRole("button", { name: "ثانوية الأندلس" }).click();
  await page.getByRole("listbox").getByRole("button", { name: /مدارس الرواد/ }).click();
  await expect(page.getByTestId("active-school-name")).toHaveText("مدارس الرواد");

  await expect(page.getByRole("link", { name: "الغياب والحضور" })).not.toBeVisible();
  await page.goto("/attendance/analytics");
  await expect(page.getByRole("alert")).toContainText("صلاحية");

  const statuses = await page.evaluate(async () => {
    const daily = await fetch("/api/v1/attendance/analytics/daily/", {
      credentials: "include",
    });
    const csrf = document.cookie
      .split("; ")
      .find((c) => c.startsWith("csrftoken="))
      ?.split("=")[1];
    const multi = await fetch("/api/v1/attendance/analytics/multi-period/", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf ?? "" },
      body: JSON.stringify({
        date: "2026-08-19",
        period_sequences: [1],
        match: "ALL_ABSENT",
      }),
    });
    return { daily: daily.status, multi: multi.status };
  });
  expect(statuses.daily).toBe(403);
  expect(statuses.multi).toBe(403);
});
