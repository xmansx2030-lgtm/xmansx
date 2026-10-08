import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import { BinaryBitmap, DecodeHintType, HybridBinarizer, QRCodeReader, RGBLuminanceSource } from "@zxing/library";
import { execFile } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { basename, dirname, resolve } from "node:path";
import { promisify } from "node:util";
import { FRONTEND_URL } from "./compose";

interface FixtureSchool {
  id: number;
  name: string;
  student_id: number;
  student_name: string;
  identifier: string;
  staff_mobile: string;
  registration_path: string;
  draft_session_id?: number;
  absent_session_id?: number;
  warning_id?: number;
  document_id?: number;
}
interface Fixture {
  run: string;
  date: string;
  parent_mobile: string;
  rejected_mobile: string;
  expired_activation_url: string;
  employee: { id: number; mobile: string; student_id: number; student_name: string; identifier: string; membership_id: number; school_id: number; document_id: number };
  schools: FixtureSchool[];
  acceptance?: {
    parent_mobile: string;
    switch_actor: { id: number; mobile: string; student_name: string; relation_id: number; membership_id: number };
    children: Array<{
      relation_id: number;
      student_id: number;
      student_name: string;
      school_id: number;
      not_started_date?: string;
      file_publication_id?: number;
      excuses?: Array<{ id: number; status: string }>;
      correction_id?: number;
    }>;
  };
}
const fixturePath =
  process.env.PARENT_E2E_FIXTURE ??
  resolve("..", "artifacts", "parent-e2e-fixture.json");
if (!existsSync(fixturePath)) throw new Error("Run seed_parent_e2e on the isolated localhost database before Parent E2E.");
const fixture = JSON.parse(readFileSync(fixturePath, "utf-8")) as Fixture;
const password = process.env.E2E_SEED_PASSWORD;
const execFileAsync = promisify(execFile);
const syntheticTLS = process.env.PARENT_E2E_SYNTHETIC_STAGING === "1";
if (syntheticTLS && FRONTEND_URL !== "https://localhost:8445") {
  throw new Error("Synthetic staging E2E requires exactly https://localhost:8445.");
}
if (!password) throw new Error("E2E_SEED_PASSWORD must explicitly match the synthetic seed command password.");
if (fixture.schools.length !== 3 || !fixture.employee || !fixture.expired_activation_url) throw new Error("Recreate the expanded synthetic Parent E2E fixture before running.");

async function signIn(context: APIRequestContext, mobile: string) {
  await context.get("/api/v1/auth/csrf/");
  expect((await post(context, "/auth/login/", { mobile, password })).status()).toBe(200);
  if (syntheticTLS) {
    const cookies = (await context.storageState()).cookies;
    expect(cookies.find((cookie) => cookie.name === "csrftoken")?.secure).toBe(true);
    const session = cookies.find((cookie) => cookie.name === "sessionid");
    expect(session?.secure).toBe(true);
    expect(session?.httpOnly).toBe(true);
    expect(session?.sameSite).toBe("Lax");
  }
}
async function registerOnPage(page: Page, school: FixtureSchool, mobile: string, identifier = school.identifier) {
  await page.goto(school.registration_path);
  await page.getByLabel("اسم ولي الأمر", { exact: true }).fill("ولي اختبار الأسرة");
  await page.getByLabel("رقم الجوال", { exact: true }).fill(mobile);
  await page.getByLabel("معرف الطالب المسجل لدى المدرسة").fill(identifier);
  await page.getByRole("button", { name: "تقديم طلب تسجيل", exact: true }).click();
  await expect(page.getByText("تم استلام طلبك، وستقوم المدرسة بمراجعته.")).toBeVisible();
  await expect(page.getByText(school.student_name, { exact: true })).toHaveCount(0);
  return page.getByLabel("رمز متابعة الطلب", { exact: true }).inputValue();
}
async function csrf(context: APIRequestContext) {
  return (
    (await context.storageState()).cookies.find(
      (cookie) => cookie.name === "csrftoken",
    )?.value ?? ""
  );
}
async function post(context: APIRequestContext, path: string, data: unknown) {
  return context.post(`/api/v1${path}`, {
    data,
    headers: { "X-CSRFToken": await csrf(context), Origin: new URL(FRONTEND_URL).origin },
  });
}
test("real parent lifecycle across schools, attendance, requests and private publication access", async ({
  page,
  playwright,
  browser,
}) => {
  test.setTimeout(210_000);
  await page.clock.install();
  const schoolA = fixture.schools[0];
  const schoolB = fixture.schools[1];
  const schoolC = fixture.schools[2];
  if (!schoolA || !schoolB || !schoolC)
    throw new Error("Three isolated fixture schools are required.");
  const contexts: APIRequestContext[] = [];
  async function staff(school: FixtureSchool) {
    const context = await playwright.request.newContext({
      baseURL: FRONTEND_URL,
      ignoreHTTPSErrors: false,
    });
    contexts.push(context);
    await context.get("/api/v1/auth/csrf/");
    expect(
      (
        await post(context, "/auth/login/", {
          mobile: school.staff_mobile,
          password,
        })
      ).status(),
    ).toBe(200);
    return context;
  }
  const staffA = await staff(schoolA);
  const staffB = await staff(schoolB);
  const staffC = await staff(schoolC);
  const staffBrowser = await browser.newContext({
    storageState: await staffA.storageState(),
    ignoreHTTPSErrors: false,
  });
  const staffPage = await staffBrowser.newPage();
  const consoleErrors: string[] = [];
  page.on("pageerror", (error) => consoleErrors.push(error.message));
  try {
    await staffPage.goto("/settings?section=parents");
    await expect(staffPage.getByLabel("رابط التسجيل", { exact: true })).toHaveValue(new URL(schoolA.registration_path, FRONTEND_URL).href);
    const qrCanvas = staffPage.locator('canvas[aria-label="رمز QR لتسجيل أولياء الأمور"]');
    await expect(qrCanvas).toHaveAttribute("width", "220");
    const qrImage = await qrCanvas.evaluate((canvas: HTMLCanvasElement) => {
      const rgba = canvas.getContext("2d")!.getImageData(0, 0, canvas.width, canvas.height).data;
      const grayscale = Array.from({ length: canvas.width * canvas.height }, (_, index) => Math.round((rgba[index * 4]! + rgba[index * 4 + 1]! * 2 + rgba[index * 4 + 2]!) / 4));
      return { width: canvas.width, height: canvas.height, grayscale };
    });
    const decodedRegistration = new QRCodeReader().decode(new BinaryBitmap(new HybridBinarizer(new RGBLuminanceSource(Uint8ClampedArray.from(qrImage.grayscale), qrImage.width, qrImage.height))), new Map([[DecodeHintType.PURE_BARCODE, true]])).getText();
    expect(decodedRegistration).toBe(new URL(schoolA.registration_path, FRONTEND_URL).href);
    await page.goto(decodedRegistration);
    await expect(page.getByLabel("اسم ولي الأمر", { exact: true })).toBeVisible();
    await expect(page.getByText(schoolA.student_name, { exact: true })).toHaveCount(0);
    await registerOnPage(page, schoolA, fixture.parent_mobile);
    await staffPage.goto("/parent-management");
    await staffPage
      .getByRole("button", { name: /مراجعة الطلب #/ })
      .first()
      .click();
    await staffPage
      .getByLabel("الطالب الذي تعتمد علاقته")
      .selectOption(String(schoolA.student_id));
    await staffPage
      .getByLabel("توثيق التحقق من الهوية والصفة")
      .fill(
        "تم التحقق حضوريّاً من الهوية والصفة ورقم مقدم الطلب في بيئة الاختبار",
      );
    await staffPage
      .getByLabel("تسليم التفعيل", { exact: true })
      .selectOption("MANUAL");
    await staffPage
      .getByRole("button", { name: "حفظ القرار", exact: true })
      .click();
    const activationUrl = await staffPage
      .getByLabel("رابط التفعيل", { exact: true })
      .inputValue();
    await page.goto(activationUrl);
    await expect(page).toHaveURL(/\/parent\/activate$/);
    await page
      .getByLabel("كلمة المرور الجديدة", { exact: true })
      .fill(password);
    await page.getByLabel("تأكيد كلمة المرور", { exact: true }).fill(password);
    await page
      .getByRole("button", { name: "إنشاء الحساب وتفعيل العلاقة" })
      .click();
    await expect(page.getByTestId("parent-shell")).toBeVisible();
    const meFirst = (await (
      await page.request.get("/api/v1/auth/me/")
    ).json()) as { id: number; memberships: unknown[] };
    expect(meFirst.memberships).toHaveLength(0);
    await registerOnPage(page, schoolB, fixture.parent_mobile);
    const registrations = (await (
      await staffB.get("/api/v1/staff/parents/registrations/")
    ).json()) as { results: Array<{ id: number }> };
    const registrationId = registrations.results[0]?.id;
    expect(registrationId).toBeTruthy();
    const approval = await post(
      staffB,
      `/staff/parents/registrations/${registrationId}/decision/`,
      {
        decision: "APPROVE",
        student_id: schoolB.student_id,
        verification_note:
          "تحقق حضوري مستقل من الصفة والرقم في المدرسة الثانية",
        delivery: "MANUAL",
        contact_bound: true,
      },
    );
    expect(approval.status()).toBe(200);
    const secondActivation = (await approval.json()) as {
      activation_url: string;
    };
    await page.goto(secondActivation.activation_url);
    await expect(
      page.getByLabel("كلمة المرور الجديدة", { exact: true }),
    ).toHaveCount(0);
    await page.getByRole("button", { name: "ربط الابن بحسابي" }).click();
    await expect(
      page.getByRole("heading", { name: schoolA.student_name, exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: schoolB.student_name, exact: true }),
    ).toBeVisible();
    const meSecond = (await (
      await page.request.get("/api/v1/auth/me/")
    ).json()) as { id: number };
    expect(meSecond.id).toBe(meFirst.id);
    await registerOnPage(page, schoolC, fixture.parent_mobile);
    const thirdQueue = (await (await staffC.get("/api/v1/staff/parents/registrations/?status=PENDING")).json()) as { results: Array<{ id: number }> };
    const thirdApproval = await post(staffC, `/staff/parents/registrations/${thirdQueue.results[0]?.id}/decision/`, { decision: "APPROVE", student_id: schoolC.student_id, verification_note: "تحقق حضوري مستقل في المدرسة الثالثة الاصطناعية", delivery: "MANUAL", contact_bound: true });
    expect(thirdApproval.status()).toBe(200);
    await page.goto((await thirdApproval.json()).activation_url as string);
    await page.getByRole("button", { name: "ربط الابن بحسابي" }).click();
    await expect(page.getByRole("heading", { name: schoolC.student_name, exact: true })).toBeVisible();
    expect((await (await page.request.get("/api/v1/auth/me/")).json()).id).toBe(meFirst.id);
    const children = (await (
      await page.request.get("/api/v1/parent/children/")
    ).json()) as {
      results: Array<{ relation_id: number; school: { id: number } }>;
    };
    const relationA = children.results.find(
      (child) => child.school.id === schoolA.id,
    )?.relation_id;
    const relationB = children.results.find(
      (child) => child.school.id === schoolB.id,
    )?.relation_id;
    expect(children.results).toHaveLength(3);
    if (!relationA || !relationB)
      throw new Error("Both approved child relations must exist.");
    await page
      .getByRole("link", { name: `تنبيهات وإجراءات ${schoolA.student_name}` })
      .click();
    await expect(page).toHaveURL(new RegExp(`relation_id=${relationA}$`));
    await expect(
      page
        .getByText(`${schoolA.student_name} · ${schoolA.name}`, { exact: true })
        .first(),
    ).toBeVisible();
    const warningNotice = page.locator("article").filter({
      has: page.getByRole("heading", {
        name: "إنذار طالب صادر",
        exact: true,
      }),
    });
    await warningNotice.getByRole("button", { name: "تعليم كمقروء" }).click();
    await expect(
      warningNotice.getByRole("button", { name: "تعليم كمقروء" }),
    ).toHaveCount(0);
    await page.goto(`/parent/children/${relationA}`);
    const firstPeriod = page.locator("li").filter({
      has: page.getByRole("heading", { name: "الحصة 1", exact: true }),
    });
    await expect(firstPeriod).toContainText("بانتظار اعتماد التحضير");
    await expect(page.getByText("تأخر صباحي محتسب: 7 دقيقة")).toBeVisible();
    expect(
      (
        await post(
          staffA,
          `/attendance/admin/sessions/${schoolA.draft_session_id}/submit/`,
          {
            marks: [{ student_id: schoolA.student_id, status: "ABSENT" }],
            reason: "اعتماد تحضير فعلي لاختبار تكامل بوابة الأسرة",
          },
        )
      ).status(),
    ).toBe(200);
    await expect(firstPeriod).toContainText("غائب", { timeout: 40_000 });
    await expect(
      page.getByText("غياب يوم كامل", { exact: true }),
    ).toBeVisible();
    await page.getByRole("tab", { name: "سجل المواظبة" }).click();
    await expect(
      page.getByRole("heading", { name: "ملخص الفترة" }),
    ).toBeVisible();
    await expect(
      page.getByText("غياب كامل مكتمل", { exact: true }).locator(".."),
    ).toContainText("1");
    await expect(
      page.getByText("دقائق التأخر المحتسبة", { exact: true }).locator(".."),
    ).toContainText("7");
    await page.getByRole("tab", { name: "اليوم", exact: true }).click();
    const todayTab = page.getByRole("tab", { name: "اليوم", exact: true });
    await todayTab.focus();
    await page.keyboard.press("ArrowLeft");
    const historyTab = page.getByRole("tab", { name: "سجل المواظبة" });
    await expect(historyTab).toBeFocused();
    await expect(historyTab).toHaveAttribute("aria-selected", "true");
    await expect(page.getByRole("tabpanel")).toHaveAttribute("aria-labelledby", await historyTab.getAttribute("id") ?? "");
    await page.keyboard.press("Home");
    await expect(todayTab).toBeFocused();
    expect(await page.locator("html").getAttribute("dir")).toBe("rtl");
    await page.setViewportSize({ width: 390, height: 844 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
    await page.screenshot({
      path: "../artifacts/parent-portal-mobile.png",
      fullPage: true,
    });
    await page.setViewportSize({ width: 768, height: 1024 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
    expect(consoleErrors).toEqual([]);
    await expect(
      page.getByRole("tablist", { name: "متابعة الابن" }),
    ).toBeVisible();
    await expect(page.getByText("تأخر صباحي محتسب: 7 دقيقة")).toBeVisible();
    await page.screenshot({
      path: "../artifacts/parent-portal-tablet.png",
      fullPage: true,
    });
    await page.setViewportSize({ width: 1366, height: 900 });
    await page.screenshot({
      path: "../artifacts/parent-portal-desktop.png",
      fullPage: true,
    });
    await page.getByRole("tab", { name: "تقديم طلب" }).click();
    await page.getByLabel("نطاق العذر").selectOption("1");
    await page
      .getByLabel("سبب العذر", { exact: true })
      .fill("تقرير طبي لتغطية الحصة الأولى في اختبار الأسرة");
    await page.getByRole("button", { name: "إرسال طلب العذر" }).click();
    await expect(page.getByText(/تم إرسال طلب العذر #/)).toBeVisible();
    const requests = (await (
      await page.request.get("/api/v1/parent/requests/")
    ).json()) as { items: Array<{ id: number; type: string }> };
    const excuse = requests.items.find((request) => request.type === "EXCUSE");
    expect(
      (
        await post(staffA, `/staff/parents/excuses/${excuse?.id}/decision/`, {
          decision: "APPROVED",
          note: "تم التحقق من المستند الطبي في الاختبار",
        })
      ).status(),
    ).toBe(200);
    let facts = (await (
      await page.request.get(`/api/v1/parent/children/${relationA}/`)
    ).json()) as {
      periods: Array<{ sequence: number; status: string; excused: boolean }>;
    };
    expect(facts.periods.find((period) => period.sequence === 1)).toMatchObject(
      { status: "ABSENT", excused: true },
    );
    await page
      .getByLabel("حصة الغياب المطلوب مراجعتها")
      .selectOption(String(schoolA.absent_session_id));
    await page
      .getByLabel("سبب الاعتراض")
      .fill("كان الطالب حاضراً في الحصة الثانية؛ يرجى مراجعة التسجيل");
    await page
      .getByRole("button", { name: "طلب مراجعة الحضور", exact: true })
      .click();
    await expect(page.getByText(/تم إرسال طلب المراجعة #/)).toBeVisible();
    const schoolRequests = (await (
      await staffA.get("/api/v1/staff/parents/requests/")
    ).json()) as {
      corrections: Array<{ id: number; session_updated_at: string }>;
    };
    const correction = schoolRequests.corrections[0];
    expect(
      (
        await post(
          staffA,
          `/staff/parents/corrections/${correction?.id}/decision/`,
          {
            decision: "APPROVED",
            note: "تم التحقق من وجود الطالب بالحصة",
            expected_updated_at: correction?.session_updated_at,
          },
        )
      ).status(),
    ).toBe(200);
    facts = await (
      await page.request.get(`/api/v1/parent/children/${relationA}/`)
    ).json();
    expect(facts.periods.find((period) => period.sequence === 2)?.status).toBe(
      "PRESENT",
    );
    await page.getByRole("tab", { name: "الإنذارات" }).click();
    const unacknowledgedWarnings = (await (
      await page.request.get(`/api/v1/parent/children/${relationA}/warnings/`)
    ).json()) as {
      items: Array<{ id: number; acknowledged_at: string | null }>;
    };
    expect(
      unacknowledgedWarnings.items.find(
        (warning) => warning.id === schoolA.warning_id,
      )?.acknowledged_at,
    ).toBeNull();
    await page
      .getByRole("button", { name: "تأكيد الاطلاع على الإنذار" })
      .click();
    await expect(page.getByText(/تم تأكيد الاطلاع:/)).toBeVisible();
    await staffPage.getByRole("button", { name: "إغلاق", exact: true }).click();
    await staffPage
      .getByRole("button", { name: "المحتوى المنشور", exact: true })
      .click();
    await staffPage
      .getByLabel("رقم سجل الطالب للنشر")
      .fill(String(schoolA.student_id));
    await staffPage
      .getByLabel("عنوان الرسالة للأسرة")
      .fill("توجيه أسري منشور صراحة");
    await staffPage
      .getByLabel("المحتوى المصرح بنشره")
      .fill("نوصي بتنظيم وقت النوم والاستعداد للدوام. هذا محتوى مصرح للأسرة.");
    await staffPage
      .getByLabel("رقم المستند المصرح (اختياري)")
      .fill(String(schoolA.document_id));
    await staffPage.getByRole("button", { name: "نشر المحتوى للأسرة" }).click();
    await expect(
      staffPage.getByText("تم نشر المحتوى داخل بوابة الأسرة"),
    ).toBeVisible();
    await page.getByRole("tab", { name: "رسائل المدرسة" }).click();
    await expect(
      page.getByRole("heading", { name: "توجيه أسري منشور صراحة" }),
    ).toBeVisible();
    const publicationLink = page.getByRole("link", {
      name: "عرض المستند المنشور",
    });
    const downloadPath = await publicationLink.getAttribute("href");
    if (!downloadPath)
      throw new Error(
        "An authenticated publication download path is required.",
      );
    const download = await page.request.get(downloadPath);
    expect(download.status()).toBe(200);
    expect(download.headers()["cache-control"]).toContain("no-store");
    expect(
      (
        await page.request.get(
          downloadPath.replace(
            `/children/${relationA}/`,
            `/children/${relationB}/`,
          ),
        )
      ).status(),
    ).toBe(404);
    await page
      .getByRole("button", { name: "تأكيد الاطلاع على الرسالة" })
      .click();
    await expect(
      page.getByText("تم تأكيد الاطلاع", { exact: true }),
    ).toBeVisible();
    const revokedMessage = await post(staffA, "/staff/parents/publications/", { student_id: schoolA.student_id, title: "رسالة ستسحب أثناء عرضها", body: "نص خاص مسحوب من الأسرة", required_action: "", document_id: schoolA.document_id });
    expect(revokedMessage.status()).toBe(201);
    const revokedPublication = (await revokedMessage.json()) as { id: number };
    await page.goto(`/parent/children/${relationA}?tab=family`);
    const withdrawnCard = page.locator("article").filter({ has: page.getByRole("heading", { name: "رسالة ستسحب أثناء عرضها" }) });
    await expect(withdrawnCard).toBeVisible();
    const withdrawnDownload = await withdrawnCard.getByRole("link", { name: "عرض المستند المنشور" }).getAttribute("href");
    expect((await post(staffA, `/staff/parents/publications/${revokedPublication.id}/revoke/`, { reason: "سحب نشر اصطناعي أثناء العرض في الاختبار" })).status()).toBe(200);
    if (!withdrawnDownload) throw new Error("Withdrawn private file path must exist.");
    expect((await page.request.get(withdrawnDownload)).status()).toBe(404);
    await withdrawnCard.getByRole("button", { name: "تأكيد الاطلاع على الرسالة" }).click();
    await expect(page.getByText("نص خاص مسحوب من الأسرة", { exact: true })).toHaveCount(0);
    await expect(page.getByRole("heading", { name: schoolA.student_name, exact: true })).toBeVisible();
    await page.evaluate(async (path) => {
      const cache = await caches.open("parent-e2e-legacy-private");
      await cache.put(path, new Response("SYNTHETIC_OLD_PRIVATE_PDF"));
      await cache.put("/api/v1/parent/children/legacy-synthetic/", new Response("SYNTHETIC_OLD_CHILD_DATA"));
    }, downloadPath);
    expect(
      (
        await post(staffA, `/staff/parents/relations/${relationA}/decision/`, {
          status: "SUSPENDED_CONTACT_REVIEW",
          reason: "مراجعة موثقة لتغيير التواصل في الاختبار",
        })
      ).status(),
    ).toBe(200);
    expect((await page.request.get(downloadPath)).status()).toBe(404);
    await expect(page.getByText("تعذر عرض بيانات الابن")).toBeVisible({ timeout: 40_000 });
    await expect(page.getByRole("heading", { name: schoolA.student_name, exact: true })).toHaveCount(0);
    expect(await page.evaluate(async () => (await (await caches.open("parent-e2e-legacy-private")).keys()).length)).toBe(0);
    const deniedChildRequests: string[] = [];
    page.on("request", (request) => { if (request.url().includes(`/api/v1/parent/children/${relationA}/`)) deniedChildRequests.push(request.url()); });
    await page.clock.fastForward(40_000);
    expect(deniedChildRequests).toEqual([]);
    await page.goto("/parent");
    await expect(page.getByTestId(`parent-child-${relationA}`)).toContainText(
      "معلقة لمراجعة التواصل",
    );
    await expect(
      page.getByRole("heading", { name: schoolB.student_name, exact: true }),
    ).toBeVisible();
    expect(
      (
        await post(page.request, "/student-leaves/", {
          student_id: schoolB.student_id,
        })
      ).status(),
    ).toBe(403);
    expect(
      (await page.request.get("/api/v1/gate/student-leaves/")).status(),
    ).toBe(403);
    await expect(
      page.getByRole("button", { name: /طلب استئذان|طلب خروج/ }),
    ).toHaveCount(0);
    expect(consoleErrors).toEqual([]);
  } finally {
    await staffBrowser.close();
    await Promise.all(contexts.map((context) => context.dispose()));
  }
});

test("existing employee activation keeps the same account, password and employment", async ({ page, playwright }) => {
  const school = fixture.schools[0]!;
  const staff = await playwright.request.newContext({ baseURL: FRONTEND_URL, ignoreHTTPSErrors: false });
  const existing = await playwright.request.newContext({ baseURL: FRONTEND_URL, ignoreHTTPSErrors: false });
  try {
    await signIn(staff, school.staff_mobile);
    await signIn(existing, fixture.employee.mobile);
    const before = await (await existing.get("/api/v1/auth/me/")).json() as { id: number; memberships: unknown[]; active_school: unknown; roles: string[] };
    expect(before.id).toBe(fixture.employee.id);
    expect(before.roles).toContain("TEACHER");
    await registerOnPage(page, school, fixture.employee.mobile, fixture.employee.identifier);
    const queue = await (await staff.get("/api/v1/staff/parents/registrations/?status=PENDING")).json() as { results: Array<{ id: number }> };
    const approval = await post(staff, `/staff/parents/registrations/${queue.results[0]?.id}/decision/`, { decision: "APPROVE", student_id: fixture.employee.student_id, verification_note: "تحقق حضوري اصطناعي من المعلم ولي الأمر وحسابه الحالي", delivery: "MANUAL", contact_bound: true });
    expect(approval.status()).toBe(200);
    const activationUrl = (await approval.json()).activation_url as string;
    // Keep a different signed-in user present to exercise authoritative requires_login.
    await signIn(page.request, school.staff_mobile);
    await page.goto(activationUrl);
    await expect(page.getByLabel("كلمة المرور الحالية", { exact: true })).toBeVisible();
    await expect(page.getByLabel("كلمة المرور الجديدة", { exact: true })).toHaveCount(0);
    await page.getByLabel("رقم جوال الحساب الحالي").fill(fixture.employee.mobile);
    await page.getByLabel("كلمة المرور الحالية", { exact: true }).fill(password!);
    await page.getByRole("button", { name: "الدخول واستكمال التفعيل" }).click();
    await page.getByRole("button", { name: "ربط الابن بحسابي" }).click();
    await expect(page.getByRole("heading", { name: fixture.employee.student_name, exact: true })).toBeVisible();
    const after = await (await page.request.get("/api/v1/auth/me/")).json() as typeof before;
    expect(after.id).toBe(before.id);
    expect(after.memberships).toEqual(before.memberships);
    expect(after.active_school).toEqual(before.active_school);
    expect(after.roles).toEqual(before.roles);
    const parentChildren = await (await page.request.get("/api/v1/parent/children/")).json() as { results: Array<{ relation_id: number; student: { id: number } }> };
    expect(parentChildren.results).toHaveLength(1);
    expect(parentChildren.results[0]?.student.id).toBe(fixture.employee.student_id);
    const reusedToken = new URL(activationUrl).hash.slice("#token=".length);
    expect((await post(page.request, "/parent/activation/", { token: reusedToken })).status()).toBe(409);
    await page.getByRole("button", { name: "مساحة العمل", exact: true }).click();
    await expect(page).toHaveURL(/\/workspace$/);
    await expect(page.getByRole("button", { name: "بوابة ولي الأمر", exact: true })).toBeVisible();
    // The original employee password still authenticates after linking.
    const fresh = await playwright.request.newContext({ baseURL: FRONTEND_URL, ignoreHTTPSErrors: false });
    try { await signIn(fresh, fixture.employee.mobile); expect((await (await fresh.get("/api/v1/auth/me/")).json()).id).toBe(before.id); } finally { await fresh.dispose(); }
  } finally { await staff.dispose(); await existing.dispose(); }
});

test("rejected registration and expired activation expose no child data", async ({ page, playwright }) => {
  const school = fixture.schools[1]!;
  const staff = await playwright.request.newContext({ baseURL: FRONTEND_URL, ignoreHTTPSErrors: false });
  try {
    await signIn(staff, school.staff_mobile);
    const receipt = await registerOnPage(page, school, fixture.rejected_mobile);
    const queue = await (await staff.get("/api/v1/staff/parents/registrations/?status=PENDING")).json() as { results: Array<{ id: number }> };
    expect((await post(staff, `/staff/parents/registrations/${queue.results[0]?.id}/decision/`, { decision: "REJECT", decision_reason: "تعذر إثبات الصفة في الاختبار الاصطناعي", verification_note: "", delivery: "MANUAL", contact_bound: false })).status()).toBe(200);
    await page.getByLabel("رمز المتابعة", { exact: true }).fill(receipt);
    await page.getByRole("button", { name: "عرض حالة الطلب" }).click();
    await expect(page.getByText("تعذر إثبات الصفة في الاختبار الاصطناعي", { exact: true })).toBeVisible();
    await expect(page.getByText(school.student_name, { exact: true })).toHaveCount(0);
    expect((await page.request.get("/api/v1/parent/children/")).status()).toBe(403);
    const receiptResult = await post(page.request, "/parent/registration/status/", { receipt_token: receipt });
    expect(await receiptResult.json()).toEqual({ status: "REJECTED", message: "تعذر إثبات الصفة في الاختبار الاصطناعي" });
    await page.goto(fixture.expired_activation_url);
    await expect(page.getByText("رابط التفعيل غير صالح أو انتهت صلاحيته.", { exact: true })).toBeVisible();
    await expect(page.getByLabel("كلمة المرور الجديدة", { exact: true })).toHaveCount(0);
    const expiredToken = new URL(fixture.expired_activation_url).hash.slice("#token=".length);
    expect((await post(page.request, "/parent/activation/", { token: expiredToken, new_password: password, confirm_password: password })).status()).toBe(409);
    expect((await page.request.get("/api/v1/parent/children/")).status()).toBe(403);
  } finally { await staff.dispose(); }
});

test("production service worker keeps private data unavailable after suspension and offline reload", async ({ page, context, playwright }) => {
  if (process.env.PARENT_E2E_PREVIEW !== "1") throw new Error("Offline privacy requires PARENT_E2E_PREVIEW=1 and a built production PWA.");
  const serviceWorkerErrors: string[] = [];
  page.on("console", (message) => { if (message.type() === "error") serviceWorkerErrors.push(message.text()); });
  page.on("pageerror", (error) => serviceWorkerErrors.push(error.message));
  page.on("requestfailed", (request) => serviceWorkerErrors.push(`${request.url()}: ${request.failure()?.errorText}`));
  await signIn(page.request, fixture.employee.mobile);
  await page.goto("/parent");
  try {
    await expect.poll(async () => page.evaluate(async () => (await navigator.serviceWorker.getRegistration())?.active?.state), { timeout: 20_000 }).toBe("activated");
    await page.reload();
    await page.waitForFunction(() => !!navigator.serviceWorker.controller, undefined, { timeout: 20_000 });
  } catch (error) {
    const state = await page.evaluate(async () => ({ url: location.href, controller: navigator.serviceWorker.controller?.scriptURL, registrations: (await navigator.serviceWorker.getRegistrations()).map((registration) => ({ scope: registration.scope, scriptURL: registration.active?.scriptURL, active: registration.active?.state, installing: registration.installing?.state, waiting: registration.waiting?.state })) }));
    throw new Error(`Production PWA installation failed: ${JSON.stringify({ state, errors: serviceWorkerErrors })}`, { cause: error });
  }
  const children = await (await page.request.get("/api/v1/parent/children/")).json() as { results: Array<{ relation_id: number }> };
  const relation = children.results[0]?.relation_id;
  if (!relation) throw new Error("Employee's activated synthetic relation is required.");
  const school = fixture.schools[0]!;
  const staff = await playwright.request.newContext({ baseURL: FRONTEND_URL, ignoreHTTPSErrors: false });
  try {
    await signIn(staff, school.staff_mobile);
    const publication = await post(staff, "/staff/parents/publications/", { student_id: fixture.employee.student_id, title: "خصوصية PWA الاصطناعية", body: "بيانات خاصة لا تعرض دون اتصال بعد التعليق", required_action: "", document_id: fixture.employee.document_id });
    expect(publication.status()).toBe(201);
    await page.goto(`/parent/children/${relation}?tab=family`);
    await expect(page.getByText("بيانات خاصة لا تعرض دون اتصال بعد التعليق", { exact: true })).toBeVisible();
    const privatePdfPath = await page.getByRole("link", { name: "عرض المستند المنشور" }).getAttribute("href");
    if (!privatePdfPath) throw new Error("A synthetic authenticated PDF download is required.");
    const pdfDownload = await page.request.get(privatePdfPath);
    expect(pdfDownload.status()).toBe(200);
    expect((await pdfDownload.body()).subarray(0, 5).toString()).toBe("%PDF-");
    expect(pdfDownload.headers()["cache-control"]).toContain("no-store");
    const privatePath = `/api/v1/parent/children/${relation}/publications/`;
    await page.evaluate(async (paths) => { const cache = await caches.open("legacy-parent-offline"); for (const path of paths) await cache.put(path, new Response("SYNTHETIC_REVOKED_PRIVATE_DATA")); }, [privatePath, privatePdfPath]);
    expect((await post(staff, `/staff/parents/relations/${relation}/decision/`, { status: "SUSPENDED_CONTACT_REVIEW", reason: "تعليق اصطناعي للتحقق من خصوصية وضع دون اتصال" })).status()).toBe(200);
    await page.getByRole("button", { name: "تأكيد الاطلاع على الرسالة" }).click();
    await expect(page.getByText("تعذر عرض بيانات الابن", { exact: true })).toBeVisible();
    expect((await page.request.get(privatePath)).status()).toBe(404);
    expect((await page.request.get(privatePdfPath)).status()).toBe(404);
    expect(await page.evaluate(async () => { const urls = await Promise.all((await caches.keys()).map(async (key) => (await (await caches.open(key)).keys()).map((request) => new URL(request.url).pathname))); return urls.flat().filter((path) => path.startsWith("/api/") || path.startsWith("/media/") || path.startsWith("/private/")); })).toEqual([]);
    await context.setOffline(true);
    const offlineResult = await page.evaluate(async (path) => { try { const response = await fetch(path); return { ok: response.ok, content: await response.text() }; } catch { return { ok: false, content: "network denied" }; } }, privatePath);
    expect(offlineResult.ok).toBe(false);
    expect(offlineResult.content).not.toContain("SYNTHETIC_REVOKED_PRIVATE_DATA");
    const offlinePdf = await page.evaluate(async (path) => { try { const response = await fetch(path); return { ok: response.ok, content: await response.text() }; } catch { return { ok: false, content: "network denied" }; } }, privatePdfPath);
    expect(offlinePdf.ok).toBe(false);
    expect(offlinePdf.content).not.toContain("SYNTHETIC_REVOKED_PRIVATE_DATA");
    await page.reload();
    await expect(page.getByText("بيانات خاصة لا تعرض دون اتصال بعد التعليق", { exact: true })).toHaveCount(0);
    await expect(page.getByRole("heading", { name: fixture.employee.student_name, exact: true })).toHaveCount(0);
  } finally { await context.setOffline(false); await staff.dispose(); }
});

test("an actually expired server session during excuse submission never reports success", async ({ page }) => {
  const verificationCompose = resolve("..", "docker-compose.parent-verification.yml");
  const releaseVerification = process.env.PARENT_E2E_RELEASE_VERIFICATION === "1";
  const composeArgs = ["compose"];
  if (syntheticTLS) {
    composeArgs.push("--env-file", resolve("..", "artifacts", "parent-staging", ".env"));
  }
  composeArgs.push("-f", verificationCompose);
  if (releaseVerification || syntheticTLS) {
    composeArgs.push("-f", resolve("..", "docker-compose.parent-release-verification.yml"));
  }
  if (syntheticTLS) {
    composeArgs.push("-f", resolve("..", "docker-compose.parent-staging.yml"));
  }
  if (process.env.PARENT_VERIFICATION_LOCAL_ONLY !== "1" || !existsSync(verificationCompose)) throw new Error("Server-session expiry requires PARENT_VERIFICATION_LOCAL_ONLY=1 and the isolated verification Compose stack.");
  await signIn(page.request, fixture.parent_mobile);
  const children = await (await page.request.get("/api/v1/parent/children/")).json() as { results: Array<{ relation_id: number; school: { id: number }; status: string }> };
  const school = fixture.schools[1]!;
  const relation = children.results.find((child) => child.status === "ACTIVE" && child.school.id === school.id)?.relation_id;
  if (!relation || !school.absent_session_id) throw new Error("An active synthetic relation with submitted absence is required for session-expiry proof.");
  await page.goto(`/parent/children/${relation}?tab=requests`);
  await page.getByLabel("نطاق العذر").selectOption("1");
  await page.getByLabel("سبب العذر", { exact: true }).fill("عذر اصطناعي لاختبار انتهاء جلسة الخادم");
  // Expire the real session while the completed form remains open, before submission.
  // Docker/Django setup is separate from the product POST timeout; Windows runs measured around 45s.
  const { stdout } = await execFileAsync("docker", [...composeArgs, "run", "--rm", "--no-deps", "--volume", `${dirname(fixturePath)}:/fixtures:ro`, "-e", "DJANGO_SETTINGS_MODULE=config.settings.local", "tests", "python", "manage.py", "seed_parent_e2e", "--password", password!, "--output", `/fixtures/${basename(fixturePath)}`, "--expire-session-for", fixture.parent_mobile], { cwd: resolve(".."), timeout: 60_000, encoding: "utf8" });
  const expiredSessionCount = Number(stdout.match(/Expired (\d+) synthetic account sessions\./)?.[1]);
  expect(expiredSessionCount, "The guarded helper must delete a real synthetic session.").toBeGreaterThan(0);
  const responsePromise = page.waitForResponse((response) => response.url().includes(`/parent/children/${relation}/excuses/`) && response.request().method() === "POST");
  await page.getByRole("button", { name: "إرسال طلب العذر" }).click();
  expect((await responsePromise).status()).toBe(403);
  await expect(page.getByRole("heading", { name: "تسجيل الدخول", exact: true })).toBeVisible();
  await expect(page.getByText(/تم إرسال طلب العذر #/)).toHaveCount(0);
  expect((await page.request.get("/api/v1/parent/children/")).status()).toBe(403);
});

test("synthetic acceptance states and same-device account switching preserve isolation", async ({ page }) => {
  const acceptance = fixture.acceptance;
  if (!acceptance || acceptance.children.length !== 3 || !acceptance.switch_actor) {
    throw new Error("Run the expanded seed_parent_staging fixture before release acceptance.");
  }
  await signIn(page.request, acceptance.parent_mobile);
  await page.goto("/parent");
  const owned = await (await page.request.get("/api/v1/parent/children/")).json() as { results: Array<{ relation_id: number }> };
  expect(owned.results.map((child) => child.relation_id).sort()).toEqual(acceptance.children.map((child) => child.relation_id).sort());
  const first = acceptance.children[0]!;
  const second = acceptance.children[1]!;
  const third = acceptance.children[2]!;
  const firstDetailResponse = await page.request.get(`/api/v1/parent/children/${first.relation_id}/?date=${fixture.date}`);
  expect(firstDetailResponse.status()).toBe(200);
  const firstDetail = await firstDetailResponse.json() as { periods: Array<{ status: string; excused: boolean }>; morning: { counted_late_minutes: number }; today: { present_periods: number; absent_periods: number; excused_absent_periods: number } };
  expect(firstDetail.periods.map((period) => period.status)).toEqual(["ABSENT", "PRESENT"]);
  expect(firstDetail.periods[0]?.excused).toBe(true);
  expect(firstDetail.today).toMatchObject({ present_periods: 1, absent_periods: 1, excused_absent_periods: 1 });
  expect(firstDetail.morning.counted_late_minutes).toBe(7);
  const secondDetail = await (await page.request.get(`/api/v1/parent/children/${second.relation_id}/?date=${fixture.date}`)).json() as { periods: Array<{ status: string }>; morning: { counted_late_minutes: number } };
  expect(secondDetail.periods.map((period) => period.status)).toEqual(["ABSENT", "IN_PROGRESS"]);
  expect(secondDetail.morning.counted_late_minutes).toBe(0);
  const future = await (await page.request.get(`/api/v1/parent/children/${third.relation_id}/?date=${third.not_started_date}`)).json() as { periods: Array<{ status: string }>; morning: { arrival_time: string | null }; today: { absent_periods: number } };
  expect(future.periods.every((period) => period.status === "NOT_STARTED")).toBe(true);
  expect(future.periods).toHaveLength(2);
  expect(future.morning.arrival_time).toBeNull();
  expect(future.today.absent_periods).toBe(0);
  const requests = await (await page.request.get("/api/v1/parent/requests/")).json() as { items: Array<{ id: number; type: string; status: string }> };
  for (const expected of first.excuses ?? []) {
    expect(requests.items.find((item) => item.type === "EXCUSE" && item.id === expected.id)?.status).toBe(expected.status);
  }
  expect(requests.items.find((item) => item.type === "CORRECTION" && item.id === first.correction_id)?.status).toBe("APPROVED");
  expect(requests.items.find((item) => item.type === "CORRECTION" && item.id === second.correction_id)?.status).toBe("PENDING");
  const publications = await page.request.get(`/api/v1/parent/children/${first.relation_id}/publications/`);
  expect(publications.status()).toBe(200);
  expect(await publications.text()).not.toContain("STAGING_INTERNAL_COUNSELOR_NOTE_MUST_NOT_LEAK");
  const download = await page.request.get(`/api/v1/parent/children/${first.relation_id}/publications/${first.file_publication_id}/download/`);
  expect(download.status()).toBe(200);
  expect(download.headers()["cache-control"]).toContain("no-store");
  expect((await download.body()).subarray(0, 5).toString()).toBe("%PDF-");
  await page.goto(`/parent/children/${third.relation_id}`);
  await expect(page.getByText("لم تسجل بصمة وصول", { exact: true })).toBeVisible();
  await expect(page.getByText("غياب بصمة الوصول لا يعني غياب الطالب عن المدرسة.", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "تسجيل الخروج", exact: true }).click();
  await expect(page.getByRole("heading", { name: "تسجيل الدخول", exact: true })).toBeVisible();
  expect((await page.request.get(`/api/v1/parent/children/${first.relation_id}/`)).status()).toBe(403);
  await signIn(page.request, acceptance.switch_actor.mobile);
  const switchedAccount = await (await page.request.get("/api/v1/auth/me/")).json() as { id: number; roles: string[] };
  expect(switchedAccount.id).toBe(acceptance.switch_actor.id);
  expect(switchedAccount.roles).toContain("TEACHER");
  await page.goto("/parent");
  await expect(page.getByRole("heading", { name: acceptance.switch_actor.student_name, exact: true })).toBeVisible();
  expect((await page.request.get(`/api/v1/parent/children/${acceptance.switch_actor.relation_id}/`)).status()).toBe(200);
  for (const child of acceptance.children) {
    await expect(page.getByText(child.student_name, { exact: true })).toHaveCount(0);
    expect((await page.request.get(`/api/v1/parent/children/${child.relation_id}/`)).status()).toBe(404);
  }
  const cacheUrls = await page.evaluate(async () => {
    const keys = await caches.keys();
    return (await Promise.all(keys.map(async (key) => (await (await caches.open(key)).keys()).map((request) => request.url)))).flat();
  });
  expect(cacheUrls.some((url) => url.includes("/api/v1/parent/") || url.includes("/download/"))).toBe(false);
});
