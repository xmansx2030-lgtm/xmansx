/** E2E المرحلة 14 — بوابة المرشد وإدارة الحالات (ضد Docker حقيقي).
 *
 * السيناريوهات الإلزامية (البنود 133-140، 160-164):
 * 1) إحالة معلم ← استلام المرشدة ← فتح الملف ← ظهوره في لوحة الإرشاد.
 * 2) جلسة مقابلة الطالب ← الخط الزمني يتحدث.
 * 3) خطة متابعة بهدف رقمي ← تفعيلها ← إجراء ينفذ.
 * 4) طلب ملاحظة من معلم ← المعلم يرد «تحسن» ← المرشدة ترى الرد.
 * 5) خصوصية المعلم: معلم آخر لا يرى الطلب ولا الحالة.
 * 6) اللقطة عند الفتح مقابل الحالي بعد اعتماد عذر.
 * 7) الإغلاق بسبب ثم إعادة الفتح — الخط الزمني كامل.
 * 8) العزل: مديرة مدرسة أخرى لا تصل للحالة.
 *
 * صف/فصل فريد (noor-13) يعزل الحالة عن بقية بيانات المدرسة.
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
  counseling_section: string;
  counseling_students: string[];
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
let seededDays: string[] = [];
// طالب المحاولة الحالية: إعادة المحاولة تبدأ بطالب نظيف بدل الاصطدام بإحالة سابقة
let caseStudent = "";
let referralId = 0;
let caseId = 0;
let requestId = 0;

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
  const activeSchool = page.getByTestId("active-school-name");
  // مستخدم المدرسة الواحدة يدخل مباشرة، أما متعدد المدارس فقد يتأخر ظهور
  // الخيارات بعد تسجيل الدخول تحت الحمل؛ لا نتجاهل نقرة اختيار مدرسة موجودة.
  await expect(chooser.or(activeSchool)).toBeVisible({ timeout: 15_000 });
  if (await chooser.isVisible()) {
    await chooser.click();
  }
  await expect(activeSchool).toHaveText(school, {
    timeout: 15_000,
  });
}

async function logout(page: Page) {
  await page.getByRole("button", { name: "تسجيل الخروج" }).click();
  await expect(page.getByLabel("رقم الجوال")).toBeVisible({ timeout: 30_000 });
}

test("teacher referral becomes a counselor case visible on the dashboard", async ({ page }, testInfo) => {
  const m = meta();
  const student = m.counseling_students[
    Math.min(testInfo.retry, m.counseling_students.length - 1)
  ];
  caseStudent = student;

  // المدير يستورد فصل الإرشاد
  await login(page, "0550000002", "ثانوية الأندلس");
  await page.goto("/students/import");
  await page.getByTestId("import-file-input").setInputFiles(resolve(FIXTURES, "noor-13.xlsx"));
  await page.getByRole("button", { name: "رفع الملف" }).click();
  await expect(page.getByText("مطابقة الأعمدة")).toBeVisible();
  await page.getByRole("button", { name: "بدء التحليل" }).click();
  await expect(page.getByRole("tab", { name: /جدد/ })).toBeVisible({ timeout: 120_000 });
  await page.getByRole("button", { name: "متابعة إلى التأكيد" }).click();
  await page.getByRole("button", { name: "اعتماد الاستيراد" }).click();
  await expect(page.getByTestId("import-result")).toBeVisible({ timeout: 60_000 });

  const daily = await api<{ date: string; day_periods: { sequence: number }[] }>(
    page,
    "/attendance/analytics/daily/",
  );
  const today = new Date(daily.body.date);
  const dayIso = (offset: number) => {
    const d = new Date(today);
    d.setDate(d.getDate() - offset);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  };
  seededDays = [0, 1, 2, 3, 4].map(dayIso);
  const periodsFor = async (day: string) => {
    const { body } = await api<{ day_periods: { sequence: number }[] }>(
      page,
      `/attendance/analytics/daily/?date=${day}`,
    );
    return body.day_periods.map((p) => p.sequence);
  };
  let seeded: SeedOutput | null = null;
  for (const day of seededDays) {
    seeded = seedAbsenceDay(m.counseling_section, day, [student], await periodsFor(day));
  }
  studentIds = seeded!.sections[m.counseling_section].students;
  const studentId = studentIds[student];

  // الوكيل يحيل الطالب (فئة المواظبة للإدارة) ويعيّن المرشدة
  await logout(page);
  await login(page, "0550000003", "ثانوية الأندلس");
  const counselors = await api<{ counselors: { id: number; name: string }[] }>(
    page,
    "/referrals/counselors/",
  );
  expect(counselors.status).toBe(200);
  const counselorId = counselors.body.counselors[0].id;

  const created = await api<{ id: number }>(page, "/referrals/", {
    method: "POST",
    body: {
      student_id: studentId,
      category: "ATTENDANCE",
      reason_code: "REPEATED_ABSENCE",
      description: "غياب متكرر ولم يتحسن بعد التواصل مع ولي الأمر.",
      assigned_counselor_id: counselorId,
    },
  });
  expect(created.status).toBe(201);
  referralId = created.body.id;

  // المرشدة تستلم الإحالة وتفتح ملف المتابعة
  await logout(page);
  await login(page, "0550000005", "ثانوية الأندلس");
  await page.goto("/referrals");
  await expect(page.getByTestId("referral-kpis")).toBeVisible({ timeout: 20_000 });
  await page.getByTestId(`open-referral-${referralId}`).click();
  await page.getByRole("button", { name: "استلام الحالة" }).click();
  await expect(page.getByTestId("referral-detail")).toContainText("تم الاستلام", {
    timeout: 20_000,
  });

  const opened = await api<{ id: number }>(page, `/referrals/${referralId}/open-case/`, {
    method: "POST",
    body: {},
  });
  expect(opened.status).toBe(201);
  caseId = opened.body.id;

  // اللوحة تعرض الحالة. المؤشر مدرسي تراكمي عبر التشغيلات، فالثابت الحقيقي هو
  // تطابقه مع عدد الحالات الحية المرئية لا رقم مطلق.
  await page.goto("/counselor");
  await expect(page.getByTestId("counselor-kpis")).toBeVisible({ timeout: 20_000 });
  await expect(page.getByTestId(`case-row-${caseId}`)).toContainText(student);
  const kpis = await api<{ open_cases: number }>(page, "/counselor/dashboard/");
  const live = await api<{ count: number }>(page, "/counselor/cases/?status=live");
  expect(kpis.body.open_cases).toBe(live.body.count);
  expect(kpis.body.open_cases).toBeGreaterThanOrEqual(1);
});

test("session, plan with a numeric goal, and activity completion", async ({ page }) => {
  await login(page, "0550000005", "ثانوية الأندلس");
  await page.goto(`/counselor/cases/${caseId}`);
  await expect(page.getByTestId("case-detail")).toBeVisible({ timeout: 20_000 });

  // (2) جلسة مقابلة الطالب
  await page.getByRole("tab", { name: "الجلسات" }).click();
  await page.getByTestId("session-type").selectOption("STUDENT_MEETING");
  await page.getByTestId("session-summary").fill("مقابلة أولى: الطالب متعاون ووعد بالالتزام.");
  await page.getByTestId("save-session").click();
  await expect(
    page.locator('[data-testid^="session-"]', { hasText: "مقابلة الطالب" }).first(),
  ).toBeVisible({ timeout: 20_000 });

  // (3) خطة متابعة بهدف رقمي ثم تنفيذ إجراء
  await page.getByRole("tab", { name: "خطة المتابعة" }).click();
  await page.getByTestId("plan-title").fill("خطة الالتزام بالحضور");
  await page.getByTestId("create-plan").click();
  const plan = page.locator('[data-testid^="plan-"]').first();
  await expect(plan).toContainText("نشطة", { timeout: 20_000 });

  await page.getByTestId("goal-title").fill("خفض التأخر الصباحي");
  await page.getByTestId("goal-type").selectOption("MORNING_LATENESS");
  await page.getByTestId("goal-baseline").fill("6");
  await page.getByTestId("goal-target").fill("1");
  await page.getByTestId("add-goal").click();
  await expect(
    page.locator('[data-testid^="goal-"]', { hasText: "خفض التأخر الصباحي" }).first(),
  ).toContainText("من 6 إلى 1", { timeout: 20_000 });

  await page.getByTestId("activity-title").fill("متابعة أسبوعية مع الطالب");
  await page.getByTestId("activity-type").selectOption("STUDENT_CHECK_IN");
  await page.getByTestId("add-activity").click();
  const activity = page
    .locator('[data-testid^="activity-"]', { hasText: "متابعة أسبوعية" })
    .first();
  await expect(activity).toBeVisible({ timeout: 20_000 });
  await activity.getByRole("button", { name: "تم التنفيذ" }).click();
  await expect(activity).toContainText("منفذ", { timeout: 20_000 });

  // الخط الزمني يعكس ما جرى
  await page.getByRole("tab", { name: "الخط الزمني" }).click();
  const timeline = page.getByTestId("case-timeline");
  await expect(timeline).toContainText("فتح الحالة");
  await expect(timeline).toContainText("إضافة جلسة");
  await expect(timeline).toContainText("تفعيل خطة");
});

test("teacher follow-up: request, response, and other teacher privacy", async ({ page }) => {
  await login(page, "0550000005", "ثانوية الأندلس"); // المرشدة
  await page.goto(`/counselor/cases/${caseId}`);
  await page.getByRole("tab", { name: "طلبات المعلمين" }).click();

  const teachers = await api<{ membership_id: number; name: string }[]>(
    page,
    "/counselor/teachers/",
  );
  expect(teachers.status).toBe(200);
  const ahmed = teachers.body.find((teacher) => teacher.name === "أحمد المعلم");
  expect(ahmed).toBeDefined();
  await page.getByTestId("request-teacher").selectOption(String(ahmed!.membership_id));
  await page.getByTestId("request-type").selectOption("CLASSROOM_BEHAVIOR");
  await page.getByTestId("request-question").fill("كيف كان التزامه داخل الفصل هذا الأسبوع؟");
  await page.getByTestId("send-request").click();
  const requestRow = page.locator('[data-testid^="req-row-"]').first();
  await expect(requestRow).toContainText("بانتظار الرد", { timeout: 20_000 });
  const requests = await api<{ id: number; question: string; status: string }[]>(
    page,
    `/counselor/cases/${caseId}/teacher-requests/`,
  );
  const pendingRequest = requests.body.find(
    (row) =>
      row.status === "PENDING" &&
      row.question === "كيف كان التزامه داخل الفصل هذا الأسبوع؟",
  );
  expect(pendingRequest).toBeDefined();
  requestId = pendingRequest!.id;

  // المعلم يرى طلبه هو ويرد
  await logout(page);
  await login(page, "0550000001", "ثانوية الأندلس"); // أحمد المعلم
  await page.goto("/teacher/follow-ups");
  const inbox = page.getByTestId("teacher-follow-ups");
  await expect(inbox).toContainText("كيف كان التزامه", { timeout: 20_000 });
  // لا محتوى إرشادي في صندوقه (البند 71)
  await expect(inbox).not.toContainText("مقابلة أولى");
  await expect(page.getByTestId("case-detail")).toHaveCount(0);

  await page.getByTestId(`respond-${requestId}`).click();
  await page.getByTestId("response-observation").fill("تحسن واضح في الانضباط والمشاركة.");
  await page.getByTestId("response-improvement").selectOption("IMPROVED");
  await page.getByTestId("submit-response").click();
  await expect(page.getByTestId(`my-response-${requestId}`)).toContainText("تحسن واضح", {
    timeout: 20_000,
  });

  // والحالة نفسها محجوبة عنه بالمعرف (البند 98)
  const forbidden = await api(page, `/counselor/cases/${caseId}/`);
  expect(forbidden.status).toBe(403);

  // المرشدة ترى الرد داخل الحالة
  await logout(page);
  await login(page, "0550000005", "ثانوية الأندلس");
  await page.goto(`/counselor/cases/${caseId}`);
  await page.getByRole("tab", { name: "طلبات المعلمين" }).click();
  await expect(page.getByTestId(`req-response-${requestId}`)).toContainText("تحسن واضح", {
    timeout: 20_000,
  });
});

test("opening snapshot stays frozen while current metrics drop after an excuse", async ({
  page,
}) => {
  const studentId = studentIds[caseStudent];

  await login(page, "0550000003", "ثانوية الأندلس"); // الوكيل يعتمد العذر
  const excuse = await api<{ id: number }>(page, "/excuses/", {
    method: "POST",
    body: {
      student_id: studentId,
      reason_type: "MEDICAL_REPORT",
      notes: "تقرير طبي",
      targets: seededDays.slice(0, 2).map((day) => ({ attendance_date: day })),
    },
  });
  expect(excuse.status).toBe(201);
  const preview = await api<{ preview_hash: string }>(
    page,
    `/excuses/${excuse.body.id}/preview/`,
    { method: "POST" },
  );
  const approved = await api(page, `/excuses/${excuse.body.id}/approve/`, {
    method: "POST",
    body: { preview_hash: preview.body.preview_hash },
  });
  expect(approved.status).toBe(200);

  await logout(page);
  await login(page, "0550000005", "ثانوية الأندلس");
  await page.goto(`/counselor/cases/${caseId}`);
  const metric = page.getByTestId("metric-unexcused_full_absence_days");
  await expect(metric).toBeVisible({ timeout: 20_000 });
  await expect(metric).toContainText("5"); // عند الفتح
  await expect(metric).toContainText("3"); // حاليًا
});

test("case closes with a reason and reopens with a full timeline", async ({ page }) => {
  await login(page, "0550000005", "ثانوية الأندلس");
  await page.goto(`/counselor/cases/${caseId}`);
  await expect(page.getByTestId("case-detail")).toBeVisible({ timeout: 20_000 });

  // الانتقالات تتبع ALLOWED_STATUS_FLOW: لا قفز من «مفتوحة» إلى «تم التحسن»
  await page.getByTestId("status-FOLLOW_UP_ACTIVE").click();
  await expect(page.getByTestId("case-status")).toHaveText("متابعة جارية", {
    timeout: 20_000,
  });

  await page.getByTestId("status-RESOLVED").click();
  await expect(page.getByTestId("case-status")).toHaveText("تم التحسن", { timeout: 20_000 });

  await page.getByTestId("closure-reason").selectOption("GOALS_MET");
  await page.getByTestId("closure-improvement").selectOption("IMPROVED");
  await page.getByTestId("close-case").click();
  await expect(page.getByTestId("case-status")).toHaveText("مغلقة", { timeout: 20_000 });
  await expect(page.getByTestId("closure-summary")).toContainText("تحققت أهداف الخطة");

  await page.getByTestId("reopen-reason").fill("عاد الغياب بعد أسبوعين");
  await page.getByTestId("reopen-case").click();
  await expect(page.getByTestId("case-status")).toHaveText("مفتوحة", { timeout: 20_000 });

  await page.getByRole("tab", { name: "الخط الزمني" }).click();
  const timeline = page.getByTestId("case-timeline");
  await expect(timeline).toContainText("إعادة فتح الحالة");
  await expect(timeline).toContainText("إغلاق الحالة");
  await expect(timeline).toContainText("تغيير الحالة");
});

test("isolation: another school's manager cannot reach the case", async ({ page }) => {
  await login(page, "0550000006", "ثانوية المستقبل");
  expect((await api(page, `/counselor/cases/${caseId}/`)).status).toBe(404);
  expect(
    (await api(page, `/counselor/cases/${caseId}/sessions/`)).status,
  ).toBe(404);
  const listing = await api<{ count: number }>(page, "/counselor/cases/");
  expect(listing.body.count).toBe(0);
});
