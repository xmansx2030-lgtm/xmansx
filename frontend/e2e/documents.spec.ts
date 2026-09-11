/** E2E المرحلة 12 — الإجراءات والمستندات والطباعة (ضد Docker حقيقي).
 *
 * السيناريوهات الإلزامية (البنود 126-133، 155-159):
 * 1) إنذار صادر ← إنشاء مستنده ← تنزيل PDF فعلي ← تغيير المقاييس ← إعادة تنزيل
 *    تعطي نفس البايتات والبصمة (اللقطة مجمدة).
 * 2) تعهد ← PDF + إجراء «أخذ تعهد» يظهران في ملف الطالب.
 * 3) تسجيل «التواصل مع ولي الأمر» يبقى بعد إعادة التحميل.
 * 4) كشف غياب لفترة → التصنيف بعذر/بدون عذر صحيح داخل اللقطة.
 * 5) كشف التأخر يعتمد على الوصول الصباحي وحده.
 * 6) العزل: مديرة مدرسة أخرى لا ترى ولا تنزل مستندات هذه المدرسة.
 *
 * صف/فصل فريد لكل تشغيل (noor-9) يعزل اللقطات عن بقية بيانات المدرسة.
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
  documents_section: string;
  documents_students: string[]; // تركي، ماجد
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
  await chooser.click({ timeout: 4000 }).catch(() => undefined);
  await expect(page.getByTestId("active-school-name")).toHaveText(school);
}

async function logout(page: Page) {
  await page.getByRole("button", { name: "تسجيل الخروج" }).click();
  await expect(page.getByLabel("رقم الجوال")).toBeVisible({ timeout: 30_000 });
}

/** تنزيل المستند عبر الجلسة نفسها وإرجاع بايتاته (لا رابط تخزين عام). */
async function downloadDocument(page: Page, documentId: number) {
  return page.evaluate(async (id) => {
    const response = await fetch(`/api/v1/documents/${id}/download/`, {
      credentials: "include",
    });
    const buffer = await response.arrayBuffer();
    const bytes = new Uint8Array(buffer);
    let hash = 0;
    for (const byte of bytes) hash = (hash * 31 + byte) % 2147483647;
    return {
      status: response.status,
      contentType: response.headers.get("content-type"),
      size: bytes.length,
      header: String.fromCharCode(...bytes.slice(0, 5)),
      fingerprint: hash,
    };
  }, documentId);
}

test("warning document: generate, download a real PDF, and reprint the frozen snapshot", async ({
  page,
}) => {
  const m = meta();
  const [turki] = m.documents_students;
  await login(page, "0550000002", "ثانوية الأندلس");

  // استيراد فصل المستندات
  await page.goto("/students/import");
  await page.getByTestId("import-file-input").setInputFiles(resolve(FIXTURES, "noor-9.xlsx"));
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
    seeded = seedAbsenceDay(m.documents_section, day, [turki], await periodsFor(day));
  }
  studentIds = seeded!.sections[m.documents_section].students;
  const turkiId = studentIds[turki];

  // قواعد ثابتة ثم إصدار الإنذار الثاني (5 أيام بدون عذر)
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
  const issued = await api<{ id: number; metric_value_at_issue: number }>(
    page,
    "/warnings/issue/",
    {
      method: "POST",
      body: { student_id: turkiId, warning_type: "UNEXCUSED_FULL_DAY_ABSENCE", level: "LEVEL_2" },
    },
  );
  expect(issued.status).toBe(201);
  expect(issued.body.metric_value_at_issue).toBe(5);

  // إنشاء المستند من تبويب المستندات في ملف الطالب
  await page.goto(`/students/${turkiId}/attendance`);
  await page.getByRole("button", { name: "المستندات" }).click();
  await page.getByTestId("document-type").selectOption("WARNING_LEVEL_2");
  await page.getByTestId("document-warning").selectOption(String(issued.body.id));
  await page.getByTestId("preview-document").click();
  const preview = page.getByTestId("document-preview");
  await expect(preview).toBeVisible({ timeout: 20_000 });
  await expect(preview).toContainText("صدر عند 5 يوم");
  await page.getByTestId("create-document").click();

  const documentRow = page.locator('[data-testid^="doc-row-"]').first();
  await expect(documentRow).toContainText("الإنذار الثاني", { timeout: 60_000 });
  await expect(documentRow).toContainText("جاهز");
  await expect(documentRow).toContainText("warning_level_2:v2");

  const listing = await api<{ results: { id: number; checksum: string; status: string }[] }>(
    page,
    `/documents/?student=${turkiId}`,
  );
  const document = listing.body.results[0];
  expect(document.status).toBe("READY");

  const first = await downloadDocument(page, document.id);
  expect(first.status).toBe(200);
  expect(first.contentType).toContain("application/pdf");
  expect(first.header).toBe("%PDF-");
  expect(first.size).toBeGreaterThan(1000);

  // تتغير المقاييس الحالية: عذر معتمد ليومين → القيمة الحالية تنخفض
  const excuse = await api<{ id: number }>(page, "/excuses/", {
    method: "POST",
    body: {
      student_id: turkiId,
      reason_type: "MEDICAL_REPORT",
      notes: "تقرير طبي",
      targets: seededDays.slice(0, 2).map((day) => ({ attendance_date: day })),
    },
  });
  expect(excuse.status).toBe(201);
  const previewExcuse = await api<{ preview_hash: string }>(
    page,
    `/excuses/${excuse.body.id}/preview/`,
    { method: "POST" },
  );
  const approved = await api(page, `/excuses/${excuse.body.id}/approve/`, {
    method: "POST",
    body: { preview_hash: previewExcuse.body.preview_hash },
  });
  expect(approved.status).toBe(200);

  // إعادة الطباعة: نفس الملف المخزن حرفيًا ونفس البصمة (البند 132)
  const second = await downloadDocument(page, document.id);
  expect(second.size).toBe(first.size);
  expect(second.fingerprint).toBe(first.fingerprint);
  const after = await api<{ checksum: string; snapshot: { warning: { metric_value_at_issue: number } } }>(
    page,
    `/documents/${document.id}/`,
  );
  expect(after.body.checksum).toBe(document.checksum);
  expect(after.body.snapshot.warning.metric_value_at_issue).toBe(5);
});

test("commitment document creates the commitment action and both appear in the profile", async ({
  page,
}) => {
  const m = meta();
  const [turki] = m.documents_students;
  await login(page, "0550000003", "ثانوية الأندلس");
  const turkiId = studentIds[turki];
  expect(turkiId).toBeTruthy();

  await page.goto(`/students/${turkiId}/attendance`);
  await page.getByRole("button", { name: "المستندات" }).click();
  await page.getByTestId("document-type").selectOption("ATTENDANCE_COMMITMENT");
  await page.getByTestId("document-from").fill(seededDays[4]);
  await page.getByTestId("document-to").fill(seededDays[0]);
  await page.getByTestId("preview-document").click();
  await expect(page.getByTestId("document-preview")).toContainText("غياب بدون عذر", {
    timeout: 20_000,
  });
  await page.getByTestId("create-document").click();

  const commitment = page.locator('[data-testid^="doc-row-"]', { hasText: "تعهد" }).first();
  await expect(commitment).toContainText("جاهز", { timeout: 60_000 });

  // الإجراء المرتبط ظهر تلقائيًا في تبويب الإجراءات
  await page.getByRole("button", { name: "الإجراءات" }).click();
  await expect(page.getByTestId("student-actions-tab")).toContainText("أخذ تعهد", {
    timeout: 20_000,
  });

  // ويبقى بعد إعادة التحميل (البند 128)
  await page.reload();
  await page.getByRole("button", { name: "الإجراءات" }).click();
  await expect(page.getByTestId("student-actions-tab")).toContainText("أخذ تعهد");
});

test("parent contact action persists and can be cancelled without deletion", async ({ page }) => {
  const m = meta();
  const [turki] = m.documents_students;
  await login(page, "0550000003", "ثانوية الأندلس");
  const turkiId = studentIds[turki];

  await page.goto(`/students/${turkiId}/attendance`);
  await page.getByRole("button", { name: "الإجراءات" }).click();
  await page.getByTestId("new-action").click();
  await page.getByTestId("action-type").selectOption("PARENT_CONTACT");
  await page.getByTestId("action-notes").fill("تم التواصل مع ولي الأمر هاتفيًا");
  await page.getByTestId("save-action").click();

  const row = page.locator('[data-testid^="action-"]', { hasText: "التواصل مع ولي الأمر" }).first();
  await expect(row).toBeVisible({ timeout: 20_000 });

  await page.reload();
  await page.getByRole("button", { name: "الإجراءات" }).click();
  await expect(
    page.locator('[data-testid^="action-"]', { hasText: "التواصل مع ولي الأمر" }).first(),
  ).toBeVisible({ timeout: 20_000 });

  // الإلغاء يبقي الصف بحالته الجديدة (لا حذف)
  const actions = await api<{ results: { id: number; action_type: string }[] }>(
    page,
    `/student-actions/?student=${turkiId}`,
  );
  const contact = actions.body.results.find((a) => a.action_type === "PARENT_CONTACT");
  expect(contact).toBeTruthy();
  await page.getByTestId(`cancel-action-${contact!.id}`).click();
  await page.getByTestId("cancel-reason").fill("سجل بالخطأ");
  await page.getByTestId("confirm-cancel-action").click();
  await expect(page.getByTestId(`action-status-${contact!.id}`)).toHaveText("ملغى", {
    timeout: 20_000,
  });
});

test("absence report keeps excused and unexcused classification, morning report stays separate", async ({
  page,
}) => {
  const m = meta();
  const [turki] = m.documents_students;
  await login(page, "0550000003", "ثانوية الأندلس");
  const turkiId = studentIds[turki];

  // كشف الغياب للفترة المبذورة: يومان بعذر (اعتمدا في السيناريو الأول) وثلاثة بدونه
  const report = await api<{ id: number }>(page, "/documents/generate/", {
    method: "POST",
    body: {
      student_id: turkiId,
      document_type: "ABSENCE_DETAIL_REPORT",
      from_date: seededDays[4],
      to_date: seededDays[0],
    },
  });
  expect(report.status).toBe(201);
  const detail = await api<{
    status: string;
    snapshot: {
      totals: { full_absence_days: number; excused_absent_periods: number };
      rows: { classification: string }[];
    };
  }>(page, `/documents/${report.body.id}/`);
  expect(detail.body.status).toBe("READY");
  expect(detail.body.snapshot.totals.full_absence_days).toBe(5);
  expect(detail.body.snapshot.rows.filter((r) => r.classification === "EXCUSED").length).toBe(2);
  expect(detail.body.snapshot.rows.filter((r) => r.classification === "UNEXCUSED").length).toBe(3);

  const pdf = await downloadDocument(page, report.body.id);
  expect(pdf.header).toBe("%PDF-");

  // تأخر صباحي يدوي ×3 ثم كشف التأخر الصباحي
  for (const day of seededDays.slice(0, 3)) {
    const arrival = await api(page, "/morning/arrivals/", {
      method: "POST",
      body: {
        student_id: turkiId,
        date: day,
        arrival_time: "07:40",
      },
    });
    expect([201, 409]).toContain(arrival.status);
  }
  const morning = await api<{ id: number }>(page, "/documents/generate/", {
    method: "POST",
    body: {
      student_id: turkiId,
      document_type: "MORNING_LATE_DETAIL_REPORT",
      from_date: seededDays[4],
      to_date: seededDays[0],
    },
  });
  expect(morning.status).toBe(201);
  const morningDetail = await api<{
    snapshot: { totals: { occurrences: number; counted_late_minutes: number } };
  }>(page, `/documents/${morning.body.id}/`);
  expect(morningDetail.body.snapshot.totals.occurrences).toBe(3);
  expect(morningDetail.body.snapshot.totals.counted_late_minutes).toBeGreaterThan(0);

});

test("isolation: a manager of another school sees and downloads nothing", async ({ page }) => {
  const m = meta();
  const [turki] = m.documents_students;
  await login(page, "0550000003", "ثانوية الأندلس");
  const turkiId = studentIds[turki];
  const listing = await api<{ results: { id: number }[] }>(
    page,
    `/documents/?student=${turkiId}`,
  );
  const documentId = listing.body.results[0].id;

  await logout(page);
  await login(page, "0550000006", "ثانوية المستقبل"); // مديرة مدرسة أخرى

  const foreignDetail = await api(page, `/documents/${documentId}/`);
  expect(foreignDetail.status).toBe(404);
  const foreignDownload = await downloadDocument(page, documentId);
  expect(foreignDownload.status).toBe(404);
  const foreignAction = await api(page, "/student-actions/", {
    method: "POST",
    body: { student_id: turkiId, action_type: "PARENT_CONTACT" },
  });
  expect(foreignAction.status).toBe(404);
  const foreignList = await api<{ count: number }>(page, `/documents/?student=${turkiId}`);
  expect(foreignList.body.count).toBe(0);
});
