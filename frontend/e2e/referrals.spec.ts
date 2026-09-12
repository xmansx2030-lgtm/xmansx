/** E2E المرحلة 13 — إحالات الطلاب إلى المرشد (ضد Docker حقيقي).
 *
 * السيناريوهات الإلزامية (البنود 154-158):
 * 1) معلم يحيل «النوم داخل الحصة» → المرشد يراها جديدة ويستلمها.
 * 2) وكيل يحيل «غياب متكرر» ويعيّن المرشد.
 * 3) معلم ثانٍ يصطدم بالتكرار → يضيف ملاحظة لنفس الحالة (حالة واحدة، ملاحظتان).
 * 4) اللقطة وقت الإحالة ثابتة بينما المؤشر الحالي ينخفض بعد اعتماد عذر.
 * 5) نفس المستخدم معلم في مدرسة ومرشد في أخرى — لا تسرب صلاحيات.
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
  referrals_grade: string;
  referrals_section: string;
  referrals_students: string[];
}

let M: Meta | null = null;
let SNAPSHOT_XLSX = "";

function meta(): Meta {
  if (M === null) {
    M = JSON.parse(readFileSync(resolve(FIXTURES, "meta.json"), "utf-8")) as Meta;
    SNAPSHOT_XLSX = resolve(FIXTURES, "referrals-run.xlsx");
    copyFileSync(resolve(FIXTURES, "noor-10.xlsx"), SNAPSHOT_XLSX);
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
let studentIds: Record<string, number> = {};

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

async function login(page: Page, mobile: string, school: string) {
  await page.goto("/");
  await page.getByLabel("رقم الجوال").fill(mobile);
  await page.getByLabel("كلمة المرور", { exact: true }).fill(PASSWORD);
  await page.getByRole("button", { name: "تسجيل الدخول" }).click();
  await page
    .locator("li", { hasText: school })
    .getByRole("button", { name: "دخول" })
    .click({ timeout: 4000 })
    .catch(() => undefined);
  await expect(page.getByTestId("active-school-name")).toHaveText(school, {
    timeout: 15_000,
  });
}

async function logout(page: Page) {
  await page.getByRole("button", { name: "تسجيل الخروج" }).click();
  await expect(page.getByLabel("رقم الجوال")).toBeVisible({ timeout: 30_000 });
}

test("teacher refers a student and the counselor acknowledges", async ({ page }) => {
  const m = meta();
  const [salem] = m.referrals_students;

  // الاستيراد صلاحية مدير — يبدأ به ثم ينتقل للمعلم
  await login(page, "0550000002", "ثانوية الأندلس");
  await page.goto("/students/import");
  await page.getByTestId("import-file-input").setInputFiles(SNAPSHOT_XLSX);
  await page.getByRole("button", { name: "رفع الملف" }).click();
  await expect(page.getByText("الخطوة: مطابقة الأعمدة", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "بدء التحليل" }).click();
  await expect(page.getByRole("tab", { name: /جدد/ })).toBeVisible({ timeout: 120_000 });
  await page.getByRole("button", { name: "متابعة إلى التأكيد" }).click();
  await page.getByRole("button", { name: "اعتماد الاستيراد" }).click();
  await expect(page.getByTestId("import-result")).toBeVisible({ timeout: 60_000 });

  const daily = await api<{ day_periods: { sequence: number }[] }>(
    page,
    "/attendance/analytics/daily/",
  );
  daySeqs = daily.body.day_periods.map((p) => p.sequence);

  // بذر جلسة واحدة لالتقاط معرفات الطلاب (نفس أداة بقية المراحل)
  const plan = {
    school: "school-a",
    sections: [{ code: m.referrals_section, periods: [{ sequence: daySeqs[0] }] }],
  };
  const stdout = execSync(
    `${COMPOSE} exec -T backend python manage.py seed_attendance_sessions --allow-production-like`,
    { input: JSON.stringify(plan), cwd: PROJECT_ROOT, encoding: "utf-8" },
  );
  seeded = JSON.parse(stdout.trim().split("\n").pop() ?? "{}") as SeedOutput;
  studentIds = seeded.sections[m.referrals_section].students;

  // المعلم يحيل من صفحة الفصل
  await logout(page);
  await login(page, "0550000001", "ثانوية الأندلس");
  const created = await api<{ id: number; status: string; source_type: string }>(
    page,
    "/referrals/",
    {
      method: "POST",
      body: {
        student_id: studentIds[salem],
        category: "CLASSROOM_BEHAVIOR",
        reason_code: "SLEEPING_IN_CLASS",
        description: "نام داخل الحصة ثلاث مرات هذا الأسبوع.",
        // تعيد Playwright المحاولة ضمن بيانات الشريحة ذاتها عند إخفاق عابر.
        allow_duplicate: true,
      },
    },
  );
  expect(created.status).toBe(201);
  expect(created.body.status).toBe("PENDING_VICE");
  expect(created.body.source_type).toBe("TEACHER");

  // «إحالاتي» تعرضها للمعلم
  await page.goto("/referrals/mine");
  await expect(page.getByTestId(`referral-row-${created.body.id}`)).toBeVisible({
    timeout: 15_000,
  });
  await expect(page.getByTestId("my-referrals-rows")).toContainText("النوم داخل الحصة");

  // الوكيل المسؤول يراجعها أولاً ثم يحولها إلى المرشدة.
  await logout(page);
  await login(page, "0550000003", "ثانوية الأندلس");
  const counselors = await api<{ counselors: { id: number }[] }>(
    page,
    "/referrals/counselors/",
  );
  expect(counselors.body.counselors).toHaveLength(1);
  const forwarded = await api(page, `/referrals/${created.body.id}/assign/`, {
    method: "POST",
    body: { counselor_membership_id: counselors.body.counselors[0].id },
  });
  expect(forwarded.status).toBe(200);

  // المرشدة تراها بعد التحويل وتستلمها.
  await logout(page);
  await login(page, "0550000005", "ثانوية الأندلس");
  await page.goto("/referrals");
  await expect(page.getByTestId("referral-kpis")).toBeVisible({ timeout: 15_000 });
  await page.getByTestId(`open-referral-${created.body.id}`).click();
  await expect(page.getByTestId("referral-detail")).toContainText("محوّلة للمرشد");
  await page.getByTestId("acknowledge-referral").click();
  await expect(page.getByTestId("referral-detail")).toContainText("تم استلام الإحالة", {
    timeout: 15_000,
  });
});

test("vice principal refers for repeated absence and assigns a counselor", async ({
  page,
}) => {
  const m = meta();
  const [, nasser] = m.referrals_students;
  await login(page, "0550000003", "ثانوية الأندلس");

  const created = await api<{ id: number; snapshot_at_referral: Record<string, unknown> }>(
    page,
    "/referrals/",
    {
      method: "POST",
      body: {
        student_id: studentIds[nasser],
        category: "ATTENDANCE",
        reason_code: "REPEATED_ABSENCE",
        description: "تكرر غيابه خلال الأسبوعين الماضيين.",
      },
    },
  );
  expect(created.status).toBe(201);
  expect(created.body.snapshot_at_referral).toHaveProperty("unexcused_full_absence_days");

  const counselors = await api<{ counselors: { id: number; name: string }[] }>(
    page,
    "/referrals/counselors/",
  );
  expect(counselors.body.counselors.length).toBeGreaterThan(0);

  await page.goto("/referrals");
  await expect(page.getByTestId("referral-kpis")).toBeVisible({ timeout: 15_000 });
  await page.getByTestId(`open-referral-${created.body.id}`).click();
  await page
    .getByTestId("assign-counselor")
    .selectOption(String(counselors.body.counselors[0].id));
  await page.getByTestId("save-assign").click();
  await expect(page.getByTestId("referral-detail")).toContainText(
    counselors.body.counselors[0].name,
    { timeout: 15_000 },
  );
});

test("duplicate referral becomes a contribution on the same case", async ({ page }) => {
  const m = meta();
  const [salem] = m.referrals_students;
  await login(page, "0550000003", "ثانوية الأندلس");

  // الحالة الصفية للمعلم ما زالت مفتوحة (استُلمت) — محاولة ثانية تكشف التكرار
  const duplicate = await api<{ code: string; details: { existing_referral_id: number } }>(
    page,
    "/referrals/",
    {
      method: "POST",
      body: {
        student_id: studentIds[salem],
        category: "CLASSROOM_BEHAVIOR",
        reason_code: "REPEATED_DISTRACTION",
        description: "تشتت متكرر في حصتي.",
      },
    },
  );
  expect(duplicate.status).toBe(409);
  expect(duplicate.body.code).toBe("DUPLICATE_OPEN_REFERRAL");
  const caseId = duplicate.body.details.existing_referral_id;

  // الإضافة بالطالب والفئة — الخادم يحل الحالة المفتوحة بنفسه
  const contribution = await api<{ referral_id: number }>(page, "/referrals/contribute/", {
    method: "POST",
    body: {
      student_id: studentIds[salem],
      category: "CLASSROOM_BEHAVIOR",
      observation_type: "CLASSROOM_OBSERVATION",
      notes: "لوحظ تشتت متكرر في حصة أخرى.",
    },
  });
  expect(contribution.status).toBe(201);
  expect(contribution.body.referral_id).toBe(caseId);

  await page.goto("/referrals");
  await expect(page.getByTestId("referral-kpis")).toBeVisible({ timeout: 15_000 });
  await page.getByTestId(`open-referral-${caseId}`).click();
  const detail = page.getByTestId("referral-detail");
  await expect(detail).toContainText("ملاحظات على الحالة (1)");
  await expect(detail).toContainText("لوحظ تشتت متكرر في حصة أخرى.");
});

test("snapshot stays fixed while current metrics improve", async ({ page }) => {
  const m = meta();
  const [, nasser] = m.referrals_students;
  await login(page, "0550000003", "ثانوية الأندلس");
  const studentId = studentIds[nasser];

  // غياب يوم كامل حقيقي ثم إحالة مواظبة تلتقط اللقطة
  const plan = {
    school: "school-a",
    sections: [
      {
        code: m.referrals_section,
        periods: daySeqs.map((sequence) => ({ sequence, absent: [nasser] })),
      },
    ],
  };
  execSync(`${COMPOSE} exec -T backend python manage.py seed_attendance_sessions --allow-production-like`, {
    input: JSON.stringify(plan),
    cwd: PROJECT_ROOT,
    encoding: "utf-8",
  });

  const created = await api<{
    id: number;
    snapshot_at_referral: { unexcused_full_absence_days: number };
  }>(page, "/referrals/", {
    method: "POST",
    body: {
      student_id: studentId,
      category: "ATTENDANCE",
      reason_code: "NO_IMPROVEMENT",
      description: "لم يتحسن بعد التنبيه.",
      allow_duplicate: true,
    },
  });
  expect(created.status).toBe(201);
  const atReferral = created.body.snapshot_at_referral.unexcused_full_absence_days;
  expect(atReferral).toBeGreaterThan(0);

  // اعتماد عذر يوم كامل يخفض «بدون عذر» الحالية دون لمس اللقطة
  const excuse = await api<{ id: number }>(page, "/excuses/", {
    method: "POST",
    body: {
      student_id: studentId,
      reason_type: "MEDICAL_REPORT",
      notes: "",
      targets: [{ attendance_date: seeded!.date }],
    },
  });
  expect(excuse.status).toBe(201);
  const preview = await api<{ preview_hash: string }>(
    page,
    `/excuses/${excuse.body.id}/preview/`,
    { method: "POST" },
  );
  await api(page, `/excuses/${excuse.body.id}/approve/`, {
    method: "POST",
    body: { preview_hash: preview.body.preview_hash },
  });

  const detail = await api<{
    snapshot_at_referral: { unexcused_full_absence_days: number };
    current_metrics: { unexcused_full_absence_days: number };
  }>(page, `/referrals/${created.body.id}/`);
  expect(detail.body.snapshot_at_referral.unexcused_full_absence_days).toBe(atReferral);
  expect(detail.body.current_metrics.unexcused_full_absence_days).toBeLessThan(atReferral);

  // والواجهة تعرض العمودين صراحة
  await page.goto("/referrals");
  await expect(page.getByTestId("referral-kpis")).toBeVisible({ timeout: 15_000 });
  await page.getByTestId(`open-referral-${created.body.id}`).click();
  await expect(
    page.getByTestId("metric-unexcused_full_absence_days"),
  ).toBeVisible({ timeout: 15_000 });
});

test("multi-school user keeps roles separate", async ({ page }) => {
  // أحمد: معلم في «ثانوية الأندلس» ومعلم+مرشد في «مدارس الرواد»
  await login(page, "0550000001", "ثانوية الأندلس");
  await expect(page.getByRole("link", { name: "التحويلات" })).toBeVisible();
  await expect(page.getByRole("link", { name: "الإحالات" })).toHaveCount(0);
  expect((await api(page, "/referrals/counselors/")).status).toBe(403);

  await page.goto("/referrals");
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole("heading", { name: /مرحبًا/ })).toBeVisible();

  // التبديل إلى المدرسة الثانية: صلاحية المرشد تظهر وبيانات الأولى لا تتسرب
  await page.getByRole("button", { name: "ثانوية الأندلس" }).click();
  await page
    .getByRole("listbox")
    .getByRole("button", { name: /مدارس الرواد/ })
    .click();
  await expect(page.getByTestId("active-school-name")).toHaveText("مدارس الرواد");
  await page.goto("/referrals");
  await expect(page.getByTestId("referral-kpis")).toBeVisible({ timeout: 15_000 });
  const listed = await api<{ count: number }>(page, "/referrals/");
  expect(listed.body.count).toBe(0);
});

test("isolation: foreign referral is not reachable", async ({ page }) => {
  await login(page, "0550000006", "مدارس الرواد"); // مديرة B
  const foreign = await api(page, `/referrals/1/`);
  expect(foreign.status).toBe(404);
});
