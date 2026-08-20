/** E2E م8.5 — الحضور الصباحي عبر الجسر الحقيقي (محاكاة، بلا mock للـSaaS):
 *  حدث بصمة → غير مطابق → ربط من الواجهة → إعادة معالجة → متأخر بالدقائق الصحيحة،
 *  ثم حدث أقدم يصحح الوصول، وطابور offline يسلّم مرة واحدة بالضبط.
 */

import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve } from "node:path";

import { expect, test, type Page } from "@playwright/test";
import { BACKEND_URL } from "./compose";

const PASSWORD = process.env.E2E_SEED_PASSWORD ?? "E2e-Dev-2026!pass";
const ROOT = resolve(import.meta.dirname, "..", "..");
const FIXTURES = resolve(import.meta.dirname, "fixtures");

test.describe.configure({ mode: "serial", timeout: 240_000 });

function yesterdayIso(): string {
  const d = new Date(Date.now() - 24 * 60 * 60 * 1000);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function runBridge(command: string[], expectFailure = false): string {
  // ‏E2E_PYTHON: شجرة موازية بلا venv خاص بها تستعير مفسر الشجرة الرئيسية
  const python =
    process.env.E2E_PYTHON ?? resolve(ROOT, "backend", ".venv", "Scripts", "python.exe");
  try {
    return execFileSync(python, ["-m", "bridge_core", ...command], {
      cwd: resolve(ROOT, "bridge"),
      env: { ...process.env, PYTHONPATH: resolve(ROOT, "bridge") },
      encoding: "utf-8",
      stdio: "pipe",
    });
  } catch (error) {
    if (expectFailure) return "";
    throw error;
  }
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

async function api<T>(page: Page, path: string, init?: { method?: string; body?: unknown }): Promise<T> {
  return page.evaluate(
    async ({ path, method, body }) => {
      const csrf = document.cookie
        .split("; ")
        .find((c) => c.startsWith("csrftoken="))
        ?.split("=")[1];
      const res = await fetch(`/api/v1${path}`, {
        method: method ?? "GET",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrf ?? "",
        },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
      return (await res.json());
    },
    { path, method: init?.method, body: init?.body },
  ) as Promise<T>;
}

test("biometric journey: event → unmatched → map via UI → late, older event corrects", async ({
  page,
}) => {
  const temp = mkdtempSync(resolve(tmpdir(), "xmansx-morning-e2e-"));
  const day = yesterdayIso();
  const externalId = `morn-${Date.now()}`;

  try {
    await login(page, "0550000002", "ثانوية الأندلس");

    // اكتفاء ذاتي: استيراد طلاب هذا التشغيل (لا تغيير لو سبق استيرادهم في السلسلة)
    await page.goto("/students/import");
    await page.getByTestId("import-file-input").setInputFiles(resolve(FIXTURES, "noor-6.xlsx"));
    await page.getByRole("button", { name: "رفع الملف" }).click();
    await expect(page.getByText("مطابقة الأعمدة")).toBeVisible();
    await page.getByRole("button", { name: "بدء التحليل" }).click();
    await expect(page.getByRole("tab", { name: /جدد/ })).toBeVisible({ timeout: 30_000 });
    await page.getByRole("button", { name: "متابعة إلى التأكيد" }).click();
    await page.getByRole("button", { name: "اعتماد الاستيراد" }).click();
    await expect(page.getByTestId("import-result")).toBeVisible({ timeout: 30_000 });

    // جهاز + جسر عبر API (الواجهة مغطاة بـVitest — هنا نختبر المسار الحقيقي)
    const device = await api<{ id: number }>(page, "/devices/", {
      method: "POST",
      body: { name: "بوابة صباح E2E", vendor: "SIMULATOR" },
    });
    const bridge = await api<{ credential: string }>(page, "/device-bridges/", {
      method: "POST",
      body: { name: "جسر صباح E2E" },
    });

    // طالبا هذا التشغيل تحديدًا (فريدان لكل تشغيل — لا تصادم مع وصولات تشغيلات سابقة)
    const meta = JSON.parse(readFileSync(resolve(FIXTURES, "meta.json"), "utf-8")) as {
      analytics_students_1: string[];
    };
    const findStudent = async (name: string) => {
      const found = await api<{ results: { id: number; full_name: string }[] }>(
        page,
        `/students/search/?search=${encodeURIComponent(name)}`,
      );
      expect(found.results.length).toBe(1);
      return found.results[0];
    };
    const target = await findStudent(meta.analytics_students_1[0]);
    const second = await findStudent(meta.analytics_students_1[1]);

    const configPath = resolve(temp, "bridge.json");
    const queuePath = resolve(temp, "queue.sqlite3");
    writeFileSync(
      configPath,
      JSON.stringify({
        saas_url: BACKEND_URL,
        credential: bridge.credential,
        queue_path: queuePath,
        batch_size: 100,
      }),
      "utf8",
    );
    const eventsPath = resolve(temp, "events.json");
    const makeEvent = (id: string, time: string, user: string) => ({
      device_id: device.id,
      external_event_id: id,
      external_user_id: user,
      occurred_at: `${day}T${time}+03:00`,
      verification_method: "FINGERPRINT",
      event_type: "CHECK_IN",
    });

    // (1) بصمة 07:14 لمعرف غير مربوط → غير مطابق (لا وصول)
    writeFileSync(eventsPath, JSON.stringify([makeEvent("m1", "07:14:00", externalId)]), "utf8");
    runBridge(["simulate", "--config", configPath, "--events-file", eventsPath]);

    // الربط من الواجهة: أجهزة الحضور ← غير مطابق ← ربط بطالب
    await page.goto("/devices");
    const identityRow = page
      .locator('[data-testid^="identity-"]', { hasText: externalId })
      .first();
    await expect(identityRow).toBeVisible({ timeout: 15_000 });
    await identityRow.getByRole("button", { name: "ربط بطالب" }).click();
    await identityRow.getByLabel("بحث عن طالب").fill(target.full_name.slice(0, 8));
    await page
      .locator('[data-testid^="pick-student-"]', { hasText: target.full_name })
      .first()
      .click();

    // إعادة المعالجة أنشأت الوصول: المتأخرون يظهرون 07:14 → محتسب 9 دقائق
    await page.goto("/morning");
    await page.getByTestId("morning-date").fill(day);
    await page.getByRole("tab", { name: "المتأخرون" }).click();
    const lateRow = page.locator('[data-testid^="late-row-"]', { hasText: target.full_name });
    await expect(lateRow).toBeVisible({ timeout: 15_000 });
    await expect(lateRow).toContainText("07:14");
    await expect(lateRow).toContainText("متأخر 9 دقيقة");

    // (2) مزامنة متأخرة تجلب حدثًا أقدم 07:12 → الوصول يتصحح والمحتسب 7
    writeFileSync(eventsPath, JSON.stringify([makeEvent("m2", "07:12:00", externalId)]), "utf8");
    runBridge(["simulate", "--config", configPath, "--events-file", eventsPath]);
    await page.reload();
    await page.getByTestId("morning-date").fill(day);
    await page.getByRole("tab", { name: "المتأخرون" }).click();
    await expect(
      page.locator('[data-testid^="late-row-"]', { hasText: target.full_name }),
    ).toContainText("07:12", { timeout: 15_000 });
    await expect(
      page.locator('[data-testid^="late-row-"]', { hasText: target.full_name }),
    ).toContainText("متأخر 7 دقيقة");

    // (3) طابور offline: ‏SaaS غير متاح → الحدث محفوظ محليًا → استعادة → مرة واحدة
    const identity2 = `morn2-${Date.now()}`;
    // ربط مسبق عبر حدث + API (نستخدم الطالب الثاني)
    writeFileSync(
      eventsPath,
      JSON.stringify([makeEvent("m3", "07:30:00", identity2)]),
      "utf8",
    );
    runBridge(["simulate", "--config", configPath, "--events-file", eventsPath]);
    const identities = await api<{ id: number; external_user_id: string }[]>(
      page,
      "/device-identities/?status=UNMATCHED",
    );
    const unmatched = identities.find((i) => i.external_user_id === identity2);
    expect(unmatched).toBeTruthy();
    await api(page, `/device-identities/${unmatched!.id}/map/`, {
      method: "POST",
      body: { student_id: second.id },
    });

    // حدث جديد أثناء انقطاع الاتصال — يبقى في الطابور ولا يفقد
    const offlineConfig = resolve(temp, "bridge-offline.json");
    writeFileSync(
      offlineConfig,
      JSON.stringify({
        saas_url: "http://localhost:59999", // لا خدمة هنا
        credential: bridge.credential,
        queue_path: queuePath,
        batch_size: 100,
      }),
      "utf8",
    );
    writeFileSync(
      eventsPath,
      JSON.stringify([makeEvent("m4", "07:05:30", identity2)]),
      "utf8",
    );
    runBridge(["simulate", "--config", offlineConfig, "--events-file", eventsPath], true);
    const queued = runBridge(["queue-status", "--config", offlineConfig]);
    expect(queued).toContain("FAILED_RETRYABLE");

    // عودة الاتصال: نفس الطابور يفرغ — 07:05:30 أقدم فيصحح وصول الطالب الثاني
    runBridge(["simulate", "--config", configPath, "--events-file", eventsPath]);
    await page.reload();
    await page.getByTestId("morning-date").fill(day);
    await page.getByRole("tab", { name: "المتأخرون" }).click();
    const secondRow = page.locator('[data-testid^="late-row-"]', {
      hasText: second.full_name,
    });
    await expect(secondRow).toBeVisible({ timeout: 15_000 });
    await expect(secondRow).toContainText("07:05");
    // متأخر أقل من دقيقة محتسبة (07:05:30 مع سماح 5) — صف واحد فقط لا اثنان
    await expect(secondRow).toContainText("متأخر 0 دقيقة");
    expect(await page.locator('[data-testid^="late-row-"]', {
      hasText: second.full_name,
    }).count()).toBe(1);
  } finally {
    rmSync(temp, { recursive: true, force: true });
  }
});
