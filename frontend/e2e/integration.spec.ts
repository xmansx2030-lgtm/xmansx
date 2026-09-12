/** E2E تكامل المرحلتين 12 و13 (ضد Docker حقيقي).
 *
 * السيناريوهات الإلزامية (البنود 66-74):
 * 1) إنذار ← مستند PDF ← إجراء «تسليم إنذار» ← ملف الطالب يعرض الثلاثة.
 * 2) إحالة الوكيل مرتبطة بالإنذار ← صندوق المرشد ← استلام.
 * 3) الإحالة الإدارية تسجل إجراء «إحالة إلى المرشد» **واحدًا** لا أكثر.
 * 4) بصمة المستند لا تتغير بعد إنشاء الإحالة واستلامها.
 * 5) لقطة الإحالة ثابتة بينما القيمة الحالية تنخفض بعد اعتماد عذر.
 * 6) ملف الطالب الموحد: الأعذار والإنذارات والإجراءات والمستندات والإحالات في جلسة واحدة.
 * 7) العزل: مديرة مدرسة أخرى لا تصل لأي من الوحدات الأربع.
 *
 * صف/فصل فريد (noor-11) يعزل السلسلة عن بقية بيانات المدرسة.
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
  integration_section: string;
  integration_students: string[];
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

interface WarningRow {
  id: number;
  warning_type: string;
  level: string;
  metric_value_at_issue: number;
}

let studentIds: Record<string, number> = {};
let seededDays: string[] = [];
let warningId = 0;
let documentId = 0;
let documentChecksum = "";
let referralId = 0;

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

async function downloadDocument(page: Page, id: number) {
  return page.evaluate(async (documentId) => {
    const response = await fetch(`/api/v1/documents/${documentId}/download/`, {
      credentials: "include",
    });
    const bytes = new Uint8Array(await response.arrayBuffer());
    let hash = 0;
    for (const byte of bytes) hash = (hash * 31 + byte) % 2147483647;
    return {
      status: response.status,
      size: bytes.length,
      header: String.fromCharCode(...bytes.slice(0, 5)),
      fingerprint: hash,
    };
  }, id);
}

async function findIssuedWarning(page: Page, studentId: number) {
  const existing = await api<{ results: WarningRow[] }>(
    page,
    `/warnings/?student=${studentId}&warning_type=UNEXCUSED_FULL_DAY_ABSENCE&status=ISSUED`,
  );
  return existing.body.results.find((row) => row.level === "LEVEL_2") ?? null;
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
  await chooser.click({ timeout: 4000 }).catch(() => undefined);
  await expect(page.getByTestId("active-school-name")).toHaveText(school);
}

async function logout(page: Page) {
  await page.getByRole("button", { name: "تسجيل الخروج" }).click();
  await expect(page.getByLabel("رقم الجوال")).toBeVisible({ timeout: 30_000 });
}

test("chain: warning → document → delivered action, all visible in the profile", async ({
  page,
}) => {
  const m = meta();
  const [student] = m.integration_students;
  await login(page, "0550000002", "ثانوية الأندلس"); // المدير يستورد

  await page.goto("/students/import");
  await page.getByTestId("import-file-input").setInputFiles(resolve(FIXTURES, "noor-11.xlsx"));
  await page.getByRole("button", { name: "رفع الملف" }).click();
  await expect(page.getByText("الخطوة: مطابقة الأعمدة", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "بدء التحليل" }).click();
  await expect(page.getByRole("tab", { name: /جدد/ })).toBeVisible({ timeout: 30_000 });
  await page.getByRole("button", { name: "متابعة إلى التأكيد" }).click();
  await page.getByRole("button", { name: "اعتماد الاستيراد" }).click();
  await expect(page.getByTestId("import-result")).toBeVisible({ timeout: 30_000 });

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
    seeded = seedAbsenceDay(m.integration_section, day, [student], await periodsFor(day));
  }
  studentIds = seeded!.sections[m.integration_section].students;
  const studentId = studentIds[student];

  const rules = await api(page, "/warning-rules/", {
    method: "PATCH",
    body: {
      UNEXCUSED_FULL_DAY_ABSENCE: {
        is_enabled: true,
        levels: { LEVEL_1: 3, LEVEL_2: 5, LEVEL_3: 10 },
      },
    },
  });
  expect(rules.status).toBe(200);

  await logout(page);
  await login(page, "0550000003", "ثانوية الأندلس"); // الوكيل

  const issued = await api<WarningRow>(
    page,
    "/warnings/issue/",
    {
      method: "POST",
      body: {
        student_id: studentId,
        warning_type: "UNEXCUSED_FULL_DAY_ABSENCE",
        level: "LEVEL_2",
      },
    },
  );
  const warning: WarningRow | null =
    issued.status === 409 ? await findIssuedWarning(page, studentId) : issued.body;
  if (issued.status !== 409) expect(issued.status).toBe(201);
  expect(warning).not.toBeNull();
  expect(warning!.metric_value_at_issue).toBe(5);
  warningId = warning!.id;

  // المستند من الواجهة
  await page.goto(`/students/${studentId}/attendance`);
  await page.getByRole("button", { name: "المستندات" }).click();
  await page.getByTestId("document-type").selectOption("WARNING_LEVEL_2");
  await page.getByTestId("document-warning").selectOption(String(warningId));
  await page.getByTestId("preview-document").click();
  await expect(page.getByTestId("document-preview")).toContainText("صدر عند 5 يوم", {
    timeout: 20_000,
  });
  await page.getByTestId("create-document").click();
  await expect(page.locator('[data-testid^="doc-row-"]').first()).toContainText("جاهز", {
    timeout: 60_000,
  });

  const documents = await api<{ results: { id: number; checksum: string }[] }>(
    page,
    `/documents/?student=${studentId}`,
  );
  documentId = documents.body.results[0].id;
  documentChecksum = documents.body.results[0].checksum;
  const downloaded = await downloadDocument(page, documentId);
  expect(downloaded.status).toBe(200);
  expect(downloaded.header).toBe("%PDF-");

  // تسليم الإنذار كإجراء صريح
  await page.getByRole("button", { name: "الإجراءات" }).click();
  await page.getByTestId("new-action").click();
  await page.getByTestId("action-type").selectOption("WARNING_DELIVERED");
  await page.getByTestId("action-warning").selectOption(String(warningId));
  await page.getByTestId("action-notes").fill("سُلم الإنذار لولي الأمر");
  await page.getByTestId("save-action").click();
  await expect(
    page.locator('[data-testid^="action-"]', { hasText: "تسليم إنذار" }).first(),
  ).toBeVisible({ timeout: 20_000 });

  // ملف الطالب يعرض الثلاثة معًا
  await page.getByRole("button", { name: "الإنذارات" }).click();
  await expect(page.getByTestId("student-warnings-tab")).toContainText("إنذارات الغياب: 1");
  await page.getByRole("button", { name: "المستندات" }).click();
  await expect(page.locator('[data-testid^="doc-row-"]').first()).toContainText(
    "الإنذار الثاني",
  );
});

test("vice principal refers the student: one referral action, counselor acknowledges", async ({
  page,
}) => {
  const m = meta();
  const [student] = m.integration_students;
  const studentId = studentIds[student];
  expect(studentId).toBeTruthy();

  await login(page, "0550000003", "ثانوية الأندلس"); // الوكيل
  const created = await api<{ id: number; source_warning_id: number | null }>(
    page,
    "/referrals/",
    {
      method: "POST",
      body: {
        student_id: studentId,
        category: "ATTENDANCE",
        reason_code: "NO_IMPROVEMENT",
        description: "لم يتحسن الحضور بعد الإنذار الثاني وتسليمه لولي الأمر.",
        source_warning_id: warningId,
      },
    },
  );
  expect(created.status).toBe(201);
  referralId = created.body.id;

  // إجراء «إحالة إلى المرشد» واحد فقط (البند 68)
  const actions = await api<{ results: { action_type: string }[] }>(
    page,
    `/student-actions/?student=${studentId}`,
  );
  const referralActions = actions.body.results.filter(
    (row) => row.action_type === "REFERRED_TO_COUNSELOR",
  );
  expect(referralActions).toHaveLength(1);
  await page.goto(`/students/${studentId}/attendance`);
  await page.getByRole("button", { name: "الإجراءات" }).click();
  await expect(page.getByTestId("student-actions-tab")).toContainText(
    "إحالة إلى المرشد الطلابي",
    { timeout: 20_000 },
  );

  // المرشد يستلمها من صندوقه
  await logout(page);
  await login(page, "0550000005", "ثانوية الأندلس"); // المرشدة (فهد مرشد مدرسة أخرى)
  await page.goto("/referrals");
  await expect(page.getByTestId("referral-kpis")).toBeVisible({ timeout: 20_000 });
  await page.getByTestId(`open-referral-${referralId}`).click();
  const detail = page.getByTestId("referral-detail");
  await expect(detail).toContainText("جديدة");
  await page.getByRole("button", { name: "استلام الحالة" }).click();
  await expect(detail).toContainText("تم استلام الإحالة", { timeout: 20_000 });
});

test("document checksum and referral snapshot both survive the other feature", async ({
  page,
}) => {
  const m = meta();
  const [student] = m.integration_students;
  const studentId = studentIds[student];
  await login(page, "0550000003", "ثانوية الأندلس");

  // (البند 70) المستند نفسه بعد الإحالة والاستلام
  const after = await api<{ checksum: string; snapshot: { warning: { metric_value_at_issue: number } } }>(
    page,
    `/documents/${documentId}/`,
  );
  expect(after.body.checksum).toBe(documentChecksum);
  expect(after.body.snapshot.warning.metric_value_at_issue).toBe(5);
  const redownload = await downloadDocument(page, documentId);
  expect(redownload.header).toBe("%PDF-");

  // (البند 71) عذر معتمد ليومين: اللقطة تبقى 5 والقيمة الحالية 3
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

  const referral = await api<{
    snapshot_at_referral: { unexcused_full_absence_days: number };
    current_metrics: { unexcused_full_absence_days: number };
  }>(page, `/referrals/${referralId}/`);
  expect(referral.status).toBe(200);
  expect(referral.body.snapshot_at_referral.unexcused_full_absence_days).toBe(5);
  expect(referral.body.current_metrics.unexcused_full_absence_days).toBe(3);

  // والمستند ما زال ببصمته نفسها بعد العذر
  const stillSame = await api<{ checksum: string }>(page, `/documents/${documentId}/`);
  expect(stillSame.body.checksum).toBe(documentChecksum);
});

test("unified student profile serves every module in one session", async ({ page }) => {
  const m = meta();
  const [student] = m.integration_students;
  const studentId = studentIds[student];
  await login(page, "0550000003", "ثانوية الأندلس");
  await page.goto(`/students/${studentId}/attendance`);

  for (const [tab, testId] of [
    ["الأعذار", "profile-add-excuse"],
    ["الإنذارات", "student-warnings-tab"],
    ["الإجراءات", "student-actions-tab"],
    ["المستندات", "student-documents-tab"],
    ["الإحالات", "student-referrals-tab"],
  ] as const) {
    await page.getByRole("button", { name: tab }).click();
    await expect(page.getByTestId(testId)).toBeVisible({ timeout: 20_000 });
  }
});

test("isolation: a manager of another school reaches none of the four modules", async ({
  page,
}) => {
  const m = meta();
  const [student] = m.integration_students;
  const studentId = studentIds[student];
  await login(page, "0550000006", "ثانوية المستقبل"); // مديرة مدرسة أخرى

  expect((await api(page, `/documents/${documentId}/`)).status).toBe(404);
  expect((await downloadDocument(page, documentId)).status).toBe(404);
  expect((await api(page, `/referrals/${referralId}/`)).status).toBe(404);
  expect(
    (await api(page, "/student-actions/", {
      method: "POST",
      body: { student_id: studentId, action_type: "PARENT_CONTACT" },
    })).status,
  ).toBe(404);
  const documents = await api<{ count: number }>(page, `/documents/?student=${studentId}`);
  expect(documents.body.count).toBe(0);
});
