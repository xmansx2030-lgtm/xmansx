import { expect, test, type Page, type Route, type TestInfo } from "@playwright/test";

const TODAY = "2026-09-10";
const GUARD_ME = {
  id: 70,
  mobile: "+966550000007",
  name: "ناصر حارس البوابة",
  is_platform_admin: false,
  must_change_password: false,
  active_school: { id: 10, name: "ثانوية الأندلس", slug: "school-a", school_type: "BOYS" },
  roles: ["GATE_GUARD"],
  memberships: [{
    id: 70,
    school: { id: 10, name: "ثانوية الأندلس", slug: "school-a", school_type: "BOYS" },
    roles: ["GATE_GUARD"],
    status: "ACTIVE",
  }],
  invitations: [],
};

const PENDING = {
  id: 981,
  student: {
    id: 501,
    full_name: "عبدالرحمن محمد عبدالله القحطاني",
    student_number: "GATE-2026-100045",
  },
  leave_date: TODAY,
  leave_time: "10:35",
  grade_name: "الأول الثانوي - المسار العام",
  section_name: "2",
  recorded_by_name: "سعد الوكيل",
  recipient_name: "أحمد عبدالله القحطاني",
  recipient_relationship: "والد الطالب",
  recipient_id_last4: "4321",
  gate_release: null,
};

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
}

async function installGuardApi(page: Page) {
  let released = false;
  await page.route("**/api/v1/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    if (path.endsWith("/auth/me/")) {
      await fulfillJson(route, GUARD_ME);
      return;
    }
    if (path.endsWith("/gate/student-leaves/981/release/") && route.request().method() === "POST") {
      released = true;
      await fulfillJson(route, {
        ...PENDING,
        gate_release: { released_at: `${TODAY}T10:37:00+03:00`, released_by_name: GUARD_ME.name },
      }, 201);
      return;
    }
    if (path.endsWith("/gate/student-leaves/")) {
      await fulfillJson(route, {
        date: TODAY,
        summary: { total: 1, pending: released ? 0 : 1, released: released ? 1 : 0 },
        results: [{
          ...PENDING,
          gate_release: released
            ? { released_at: `${TODAY}T10:37:00+03:00`, released_by_name: GUARD_ME.name }
            : null,
        }],
      });
      return;
    }
    await fulfillJson(route, {
      code: "NOT_FOUND",
      message: "المورد المطلوب غير موجود.",
      details: {},
    }, 404);
  });
}

async function assertNoPageOverflow(page: Page) {
  const dimensions = await page.evaluate(() => ({
    viewport: document.documentElement.clientWidth,
    content: document.documentElement.scrollWidth,
  }));
  expect(dimensions.content).toBeLessThanOrEqual(dimensions.viewport + 1);
}

async function screenshot(page: Page, testInfo: TestInfo, name: string, fullPage = true) {
  await page.screenshot({ path: testInfo.outputPath(name), fullPage });
}

test("gate guard phone workspace is focused, responsive, and safe", async ({ page, context }, testInfo) => {
  await installGuardApi(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/gate");

  await expect(page.getByRole("heading", { name: "خروج الطلاب" })).toBeVisible();
  await expect(page.getByTestId("gate-last-updated")).toContainText("آخر مزامنة");
  const card = page.getByTestId("gate-leave-981");
  await expect(card).toContainText(PENDING.student.full_name);
  await expect(card).toContainText(PENDING.student.student_number);
  await expect(card.getByTestId("gate-release-facts")).toContainText("سعد الوكيل");
  await assertNoPageOverflow(page);
  await screenshot(page, testInfo, "gate-guard-phone-queue.png");

  await page.setViewportSize({ width: 360, height: 800 });
  await assertNoPageOverflow(page);
  await context.setOffline(true);
  await expect(page.getByText("غير متصل — التأكيد متوقف")).toBeVisible();
  await expect(card.getByRole("button", { name: "تحقق واسمح بخروج الطالب" })).toBeDisabled();
  await context.setOffline(false);
  await expect(page.getByText("متصل", { exact: true })).toBeVisible();

  await card.getByRole("button", { name: "تحقق واسمح بخروج الطالب" }).click();
  const dialog = page.getByRole("dialog", { name: `تأكيد خروج ${PENDING.student.full_name}` });
  await expect(dialog.getByTestId("gate-release-facts")).toContainText("سعد الوكيل");
  await expect(dialog).toContainText("4321");
  await assertNoPageOverflow(page);
  await screenshot(page, testInfo, "gate-guard-phone-confirmation.png", false);
  await dialog.getByRole("button", { name: "تم التحقق والسماح بالخروج" }).click();

  await page.getByRole("button", { name: "خرج اليوم" }).click();
  await expect(page.getByText(/سُجّل الخروج/)).toBeVisible();
  await expect(page.getByText(`بواسطة ${GUARD_ME.name}`)).toBeVisible();

  await page.getByRole("button", { name: "فتح قائمة التنقل" }).click();
  const navigation = page.locator("#mobile-navigation");
  await expect(navigation.getByRole("link", { name: "بوابة المدرسة" })).toBeVisible();
  await expect(navigation.getByRole("link")).toHaveCount(1);
  await expect(page.getByTestId("user-roles-mobile")).toHaveText("حارس البوابة");
  await assertNoPageOverflow(page);

  await page.goto("/student-leaves");
  await expect(page).toHaveURL(/\/gate$/);
  await expect(page.getByTestId("gate-page")).toBeVisible();
});
