/** E2E المرحلة 10 — أعذار الغياب والتصنيف الإداري (ضد Docker حقيقي).
 *
 * السيناريوهات الإلزامية (البنود 179-182):
 * 1) غياب يوم كامل → معاينة → اعتماد → الغياب يبقى ويصبح «بعذر».
 * 2) عذر حصص محددة → 2 بعذر و1 بدون عذر.
 * 3) تعديل الحضور بعد الاعتماد → التغطية تلغى والعدادات تتحدث.
 * 4) يوم ناقص ثم اعتماد الحصة المفقودة → التغطية تتوسع تلقائيًا.
 *
 * صف/فصل فريد لكل تشغيل (noor-7) يعزل العدادات عن بقية بيانات المدرسة.
 */

import { execSync } from "node:child_process";
import { copyFileSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test, type Page } from "@playwright/test";
import { COMPOSE } from "./compose";

const PASSWORD = process.env.E2E_SEED_PASSWORD ?? "E2e-Dev-2026!pass";
const FIXTURES = resolve(dirname(fileURLToPath(import.meta.url)), "fixtures");
const PROJECT_ROOT = resolve(FIXTURES, "..", "..", "..");

test.describe.configure({ mode: "serial", timeout: 300_000 });

interface Meta {
  excuses_grade: string;
  excuses_section: string;
  excuses_students: string[]; // سالم، ناصر
}

/** لقطة محلية من الـfixtures عند أول استخدام: إعادة توليدها أثناء التشغيل (من
 *  تشغيل E2E متوازٍ لمرحلة أخرى) لا تجعل meta.json تخالف ملف الإكسل المرفوع. */
let M: Meta | null = null;
let SNAPSHOT_XLSX = "";

function meta(): Meta {
  if (M === null) {
    M = JSON.parse(readFileSync(resolve(FIXTURES, "meta.json"), "utf-8")) as Meta;
    SNAPSHOT_XLSX = resolve(FIXTURES, "excuses-run.xlsx");
    copyFileSync(resolve(FIXTURES, "noor-7.xlsx"), SNAPSHOT_XLSX);
  }
  return M;
}

interface SeedOutput {
  date: string;
  sections: Record<
    string,
    { sessions: Record<string, number>; students: Record<string, number> }
  >;
}

let seeded: SeedOutput | null = null;
let daySeqs: number[] = [];

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

function seedSessions(sectionCode: string, periods: unknown[]): SeedOutput {
  const plan = { school: "school-a", sections: [{ code: sectionCode, periods }] };
  const stdout = execSync(
    `${COMPOSE} exec -T backend python manage.py seed_attendance_sessions --allow-production-like`,
    { input: JSON.stringify(plan), cwd: PROJECT_ROOT, encoding: "utf-8" },
  );
  return JSON.parse(stdout.trim().split("\n").pop() ?? "{}") as SeedOutput;
}

/** خروج عبر API مباشرة — أسرع وأثبت من انتظار زر الهيدر. */
async function logout(page: Page) {
  await api(page, "/auth/logout/", { method: "POST" });
  await page.goto("/login");
  await expect(page.getByLabel("رقم الجوال")).toBeVisible({ timeout: 30_000 });
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

/** ملخص ملف الطالب ليوم البذر تحديدًا (لا نعتمد النطاق الافتراضي). */
async function profileMetrics(page: Page, studentId: number, day?: string) {
  const date = day ?? seeded!.date;
  const { body } = await api<{
    attendance: {
      full_absence_days: number;
      absent_periods: number;
      excused_full_absence_days: number;
      unexcused_full_absence_days: number;
      excused_absent_periods: number;
      unexcused_absent_periods: number;
    };
  }>(
    page,
    `/students/${studentId}/attendance-profile/?from_date=${date}&to_date=${date}`,
  );
  return body.attendance;
}

test("full-day excuse: absence stays, classification becomes excused", async ({ page }) => {
  const m = meta();
  const [salem] = m.excuses_students;
  // الاستيراد صلاحية مدير فقط — يبدأ بالمدير ثم ينتقل للوكيل لعمليات الأعذار
  await login(page, "0550000002", "ثانوية الأندلس");

  // استيراد فصل الأعذار
  await page.goto("/students/import");
  await page.getByTestId("import-file-input").setInputFiles(SNAPSHOT_XLSX);
  await page.getByRole("button", { name: "رفع الملف" }).click();
  await expect(page.getByText("مطابقة الأعمدة")).toBeVisible();
  await page.getByRole("button", { name: "بدء التحليل" }).click();
  await expect(page.getByRole("tab", { name: /جدد/ })).toBeVisible({ timeout: 30_000 });
  await page.getByRole("button", { name: "متابعة إلى التأكيد" }).click();
  await page.getByRole("button", { name: "اعتماد الاستيراد" }).click();
  await expect(page.getByTestId("import-result")).toBeVisible({ timeout: 30_000 });

  const daily = await api<{ day_periods: { sequence: number }[] }>(
    page,
    "/attendance/analytics/daily/",
  );
  daySeqs = daily.body.day_periods.map((p) => p.sequence);
  expect(daySeqs.length).toBeGreaterThanOrEqual(3);

  // سالم غائب كل حصص اليوم
  seeded = seedSessions(
    m.excuses_section,
    daySeqs.map((sequence) => ({ sequence, absent: [salem] })),
  );
  const salemId = seeded.sections[m.excuses_section].students[salem];

  // قبل العذر: غياب كامل بدون عذر
  let metrics = await profileMetrics(page, salemId);
  expect(metrics.full_absence_days).toBe(1);
  expect(metrics.unexcused_full_absence_days).toBe(1);
  expect(metrics.excused_full_absence_days).toBe(0);
  expect(metrics.unexcused_absent_periods).toBe(daySeqs.length);

  // الوكيل (لا المدير) هو من ينشئ ويعتمد العذر — سيناريو البند 179
  await logout(page);
  await login(page, "0550000003", "ثانوية الأندلس");
  await page.goto("/excuses");
  await expect(page.getByTestId("excuse-kpis")).toBeVisible({ timeout: 15_000 });
  await page.getByTestId("new-excuse").click();
  await page.getByLabel("بحث عن طالب").fill(salem.slice(0, 12));
  await page.getByTestId(`pick-student-${salemId}`).click();
  await page.getByTestId("excuse-from").fill(seeded.date);
  await page.getByTestId("excuse-to").fill(seeded.date);
  await page.getByTestId("save-excuse").click();

  // المعاينة تعرض عدد الحصص المغطاة ثم الاعتماد
  await expect(page.getByTestId("excuse-detail")).toBeVisible({ timeout: 15_000 });
  await page.getByTestId("preview-excuse").click();
  await expect(page.getByTestId("excuse-preview")).toContainText(
    `${daySeqs.length} حصة غياب سيتحول تصنيفها`,
  );
  await page.getByTestId("confirm-approve").click();
  await expect(page.getByTestId("excuse-detail")).toContainText("معتمد", {
    timeout: 15_000,
  });

  // سجل الحضور الخام لم يتغير: كل الحصص ما زالت ABSENT
  const detail = await api<{ periods: { status: string; excused: boolean | null }[] }>(
    page,
    `/students/${salemId}/attendance-days/${seeded.date}/`,
  );
  const marked = detail.body.periods.filter((p) => p.status === "ABSENT");
  expect(marked).toHaveLength(daySeqs.length);
  expect(marked.every((p) => p.excused === true)).toBe(true);

  // الملخص: الغياب الكامل يبقى يومًا واحدًا لكنه صار «بعذر»
  metrics = await profileMetrics(page, salemId);
  expect(metrics.full_absence_days).toBe(1);
  expect(metrics.excused_full_absence_days).toBe(1);
  expect(metrics.unexcused_full_absence_days).toBe(0);
  expect(metrics.excused_absent_periods).toBe(daySeqs.length);
  expect(metrics.unexcused_absent_periods).toBe(0);

  // بطاقات ملف الطالب تعرض ذلك للمستخدم
  await page.goto(`/students/${salemId}/attendance`);
  const cards = page.getByTestId("excuse-metrics");
  await expect(cards).toBeVisible({ timeout: 15_000 });
  await expect(cards).toContainText("غياب كامل بعذر");
  await expect(page.getByText("غياب كامل بعذر").locator("..")).toContainText("1 يوم");
});

test("period-specific excuse: 2 excused, 1 unexcused", async ({ page }) => {
  const m = meta();
  const [salem, nasser] = m.excuses_students;
  await login(page, "0550000003", "ثانوية الأندلس");

  // ناصر غائب في ثلاث حصص فقط — وسالم يبقى غائبًا كل الحصص (بذر يمسح ويعيد بناء
  // علامات الجلسة، فحذفه هنا يبطل تغطية الاختبار السابق التي يعتمد عليها التالي)
  const [p1, p2, p3] = daySeqs;
  seeded = seedSessions(
    m.excuses_section,
    daySeqs.map((sequence) => ({
      sequence,
      absent: [p1, p2, p3].includes(sequence) ? [salem, nasser] : [salem],
    })),
  );
  const nasserId = seeded.sections[m.excuses_section].students[nasser];

  await page.goto("/excuses");
  await expect(page.getByTestId("excuse-kpis")).toBeVisible({ timeout: 15_000 });
  await page.getByTestId("new-excuse").click();
  await page.getByLabel("بحث عن طالب").fill(nasser.slice(0, 12));
  await page.getByTestId(`pick-student-${nasserId}`).click();
  await page.getByTestId("excuse-scope").selectOption("PERIODS");
  await page.getByTestId("excuse-from").fill(seeded.date);
  await page.getByTestId("excuse-periods").fill(`${p1}، ${p2}`);
  await page.getByTestId("save-excuse").click();

  await expect(page.getByTestId("excuse-detail")).toBeVisible({ timeout: 15_000 });
  await page.getByTestId("preview-excuse").click();
  await expect(page.getByTestId("excuse-preview")).toContainText("2 حصة غياب");
  await page.getByTestId("confirm-approve").click();
  await expect(page.getByTestId("excuse-detail")).toContainText("معتمد", {
    timeout: 15_000,
  });

  const metrics = await profileMetrics(page, nasserId);
  expect(metrics.absent_periods).toBe(3);
  expect(metrics.excused_absent_periods).toBe(2);
  expect(metrics.unexcused_absent_periods).toBe(1);
});

test("attendance corrected to present: coverage voided and counters updated", async ({
  page,
}) => {
  const m = meta();
  const [salem] = m.excuses_students;
  await login(page, "0550000002", "ثانوية الأندلس"); // المدير — تصحيح إداري
  const section = seeded!.sections[m.excuses_section];
  const salemId = section.students[salem];
  const firstSession = section.sessions[String(daySeqs[0])];

  const before = await profileMetrics(page, salemId);
  expect(before.excused_absent_periods).toBeGreaterThan(0);

  // تصحيح: سالم حاضر في الحصة الأولى (قائمة العلامات بلا علامته)
  const edit = await api(page, `/attendance/sessions/${firstSession}/`, {
    method: "PATCH",
    body: { marks: [], reason: "تصحيح إداري E2E" },
  });
  expect(edit.status).toBe(200);

  const after = await profileMetrics(page, salemId);
  expect(after.absent_periods).toBe(before.absent_periods - 1);
  expect(after.excused_absent_periods).toBe(before.excused_absent_periods - 1);
  expect(after.unexcused_absent_periods).toBe(0);
  // اليوم لم يعد غيابًا كاملًا — الحقيقة التشغيلية تحكم
  expect(after.full_absence_days).toBe(0);

  // التغطية ظهرت ملغاة في تفاصيل العذر مع سبب تغير الحضور
  await page.goto("/excuses");
  await expect(page.getByTestId("excuse-kpis")).toBeVisible({ timeout: 15_000 });
  const { body: list } = await api<{ results: { id: number; student: { id: number } }[] }>(
    page,
    `/excuses/?student=${salemId}`,
  );
  const excuseId = list.results[0].id;
  await page.getByTestId(`open-excuse-${excuseId}`).click();
  await expect(page.getByTestId("excuse-detail")).toContainText("تغير الحضور", {
    timeout: 15_000,
  });
});

test("incomplete day then late submission expands coverage automatically", async ({
  page,
}) => {
  const m = meta();
  const [, nasser] = m.excuses_students;
  await login(page, "0550000003", "ثانوية الأندلس");
  const nasserId = seeded!.sections[m.excuses_section].students[nasser];

  // إلغاء أي عذر معتمد سابق لناصر حتى لا يتداخل مع هذا السيناريو
  const { body: existing } = await api<{ results: { id: number; status: string }[] }>(
    page,
    `/excuses/?student=${nasserId}`,
  );
  for (const row of existing.results.filter((r) => r.status === "APPROVED")) {
    await api(page, `/excuses/${row.id}/cancel/`, {
      method: "POST",
      body: { reason: "تهيئة سيناريو E2E" },
    });
  }

  // يوم ناقص: كل الحصص عدا الأخيرة، وناصر غائب فيها
  const missing = daySeqs[daySeqs.length - 1];
  const seededPartial = seedSessions(
    m.excuses_section,
    daySeqs
      .filter((sequence) => sequence !== missing)
      .map((sequence) => ({ sequence, absent: [nasser] })),
  );
  // الجلسة الأخيرة يجب ألا تكون معتمدة — نحذفها إن بذرت في اختبار سابق
  execSync(
    `${COMPOSE} exec -T backend python manage.py shell -c ` +
      `"from attendance.models import AttendanceSession as S; from attendance.services.daily_summary import recalculate_daily_attendance_for_section as R; ` +
      `qs=S.objects.filter(section__code='${m.excuses_section}', attendance_date='${seededPartial.date}', period_sequence=${missing}); ` +
      `s=qs.first(); qs.delete(); ` +
      `R(school=s.school, section=s.section, attendance_date=s.attendance_date) if s else None"`,
    { cwd: PROJECT_ROOT, encoding: "utf-8" },
  );

  // عذر يوم كامل: المعاينة تعلن نقص البيانات ثم الاعتماد يغطي الموجود فقط
  await page.goto("/excuses");
  await expect(page.getByTestId("excuse-kpis")).toBeVisible({ timeout: 15_000 });
  await page.getByTestId("new-excuse").click();
  await page.getByLabel("بحث عن طالب").fill(nasser.slice(0, 12));
  await page.getByTestId(`pick-student-${nasserId}`).click();
  await page.getByTestId("excuse-from").fill(seededPartial.date);
  await page.getByTestId("excuse-to").fill(seededPartial.date);
  await page.getByTestId("save-excuse").click();

  await expect(page.getByTestId("excuse-detail")).toBeVisible({ timeout: 15_000 });
  await page.getByTestId("preview-excuse").click();
  await expect(page.getByTestId("excuse-preview")).toContainText("بيانات اليوم غير مكتملة");
  await page.getByTestId("confirm-approve").click();
  await expect(page.getByTestId("excuse-detail")).toContainText("معتمد", {
    timeout: 15_000,
  });

  const partial = await profileMetrics(page, nasserId);
  expect(partial.excused_absent_periods).toBe(daySeqs.length - 1);
  expect(partial.unexcused_absent_periods).toBe(0);

  // الحصة المفقودة تعتمد الآن وناصر غائب فيها → التغطية تتوسع تلقائيًا
  seedSessions(m.excuses_section, [{ sequence: missing, absent: [nasser] }]);
  const complete = await profileMetrics(page, nasserId);
  expect(complete.absent_periods).toBe(daySeqs.length);
  expect(complete.excused_absent_periods).toBe(daySeqs.length);
  expect(complete.unexcused_absent_periods).toBe(0);
  expect(complete.excused_full_absence_days).toBe(1);
});

test("isolation: teacher has no excuses link, page, or API access", async ({ page }) => {
  await login(page, "0550000001", "ثانوية الأندلس"); // معلم
  await expect(page.getByRole("link", { name: "الأعذار" })).toHaveCount(0);

  const list = await api(page, "/excuses/");
  expect(list.status).toBe(403);
  const kpis = await api(page, "/excuses/kpis/");
  expect(kpis.status).toBe(403);

  await page.goto("/excuses");
  await expect(page.getByRole("heading", { name: "لا تملك صلاحية عرض الأعذار" })).toBeVisible(
    { timeout: 15_000 },
  );
});
