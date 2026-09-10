import { expect, test, type Page, type Route, type TestInfo } from "@playwright/test";

const TEACHER_ME = {
  id: 71,
  mobile: "+966550000001",
  name: "أحمد المعلم",
  is_platform_admin: false,
  must_change_password: false,
  active_school: { id: 10, name: "ثانوية الأندلس", slug: "andalus", school_type: "BOYS" },
  roles: ["TEACHER"],
  memberships: [{
    id: 71,
    school: { id: 10, name: "ثانوية الأندلس", slug: "andalus", school_type: "BOYS" },
    roles: ["TEACHER"],
    status: "ACTIVE",
  }],
  invitations: [],
};

const SECTION = {
  id: 3,
  name: "فصل الموهوبين ١",
  grade_name: "الأول الثانوي - المسار العام",
  students_count: 3,
};

const PERIOD = {
  sequence: 2,
  name: "الحصة الثانية",
  start_time: "08:05",
  end_time: "08:50",
  timezone: "Asia/Riyadh",
};

const SESSION = {
  id: 5,
  status: "IN_PROGRESS",
  attendance_date: "2026-09-10",
  section: SECTION,
  period: PERIOD,
  submitted_by: null,
  submitted_at: null,
  can_edit: true,
  roster: [
    { student_id: 11, full_name: "عبدالرحمن محمد عبدالله القحطاني", national_id_masked: "******0011" },
    { student_id: 12, full_name: "محمد أحمد السبيعي", national_id_masked: "******0012" },
    { student_id: 13, full_name: "سلمان علي الشهري", national_id_masked: "******0013" },
  ],
  marks: [],
};

const REFERRAL_ROW = {
  id: 7,
  student: { id: 5, full_name: "محمد أحمد السبيعي", grade_name: "الأول الثانوي", section_name: "2" },
  source_type: "TEACHER",
  source_type_label: "معلم",
  category: "CLASSROOM_BEHAVIOR",
  category_label: "سلوك صفي",
  reason_code: "SLEEPING_IN_CLASS",
  reason_label: "النوم داخل الحصة",
  status: "NEW",
  status_label: "جديدة",
  priority: "NORMAL",
  priority_label: "عادية",
  created_at: "2026-09-10T09:00:00+03:00",
  created_by_name: "أحمد المعلم",
  assigned_counselor_id: null,
  assigned_counselor_name: null,
  counseling_case_id: null,
};

const REFERRAL_DETAIL = {
  ...REFERRAL_ROW,
  can_cancel: true,
  description: "لاحظت تكرار النوم داخل الحصة ثلاث مرات خلال هذا الأسبوع.",
  snapshot_at_referral: {
    student_name: "محمد أحمد السبيعي",
    grade_name: "الأول الثانوي",
    section_name: "2",
    full_absence_days: 2,
    unexcused_full_absence_days: 1,
    absent_periods: 4,
    morning_late_occurrences: 3,
    period_late_occurrences: 2,
  },
  current_metrics: {
    full_absence_days: 2,
    unexcused_full_absence_days: 1,
    absent_periods: 5,
    morning_late_occurrences: 3,
    period_late_occurrences: 2,
  },
  source_warning: null,
  accepted_at: null,
  closed_at: null,
  closed_by_name: null,
  closure_reason: "",
  contributions: [{
    id: 20,
    observation_type: "CLASSROOM_OBSERVATION",
    observation_type_label: "ملاحظة صفية",
    notes: "تحسن تفاعله في بداية الحصة ويحتاج متابعة مستمرة.",
    created_at: "2026-09-10T10:00:00+03:00",
    created_by_name: "أحمد المعلم",
  }],
  events: [{
    id: 1,
    event_type: "CREATED",
    event_type_label: "أنشئت الإحالة",
    actor_name: "أحمد المعلم",
    created_at: "2026-09-10T09:00:00+03:00",
    metadata: {},
  }],
};

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
}

async function installTeacherApi(page: Page) {
  await page.route("**/api/v1/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    if (path.endsWith("/auth/me/")) return fulfillJson(route, TEACHER_ME);
    if (path.endsWith("/attendance/current-period/")) {
      return fulfillJson(route, { period: PERIOD, date: "2026-09-10" });
    }
    if (path.endsWith("/attendance/sections/")) {
      return fulfillJson(route, [
        SECTION,
        { id: 4, name: "2", grade_name: "الأول الثانوي", students_count: 26 },
        { id: 5, name: "1", grade_name: "الثاني الثانوي", students_count: 24 },
      ]);
    }
    if (path.endsWith("/attendance/sections/3/preview/")) {
      return fulfillJson(route, {
        attendance_date: "2026-09-10",
        section: SECTION,
        period: PERIOD,
        session: null,
      });
    }
    if (path.endsWith("/attendance/sessions/start/") && route.request().method() === "POST") {
      return fulfillJson(route, SESSION, 201);
    }
    if (path.endsWith("/teacher/follow-up-requests/")) {
      return fulfillJson(route, [{
        id: 41,
        request_type: "CLASSROOM_BEHAVIOR",
        request_type_label: "سلوك صفي",
        question: "كيف كان تفاعل الطالب داخل الحصة خلال الأسبوع؟ وهل طرأ تحسن يمكن توثيقه؟",
        due_date: "2026-09-12",
        status: "PENDING",
        status_label: "بانتظار الرد",
        teacher_name: "أحمد المعلم",
        requested_by_name: "ليان المرشدة",
        created_at: "2026-09-10T08:00:00+03:00",
        responded_at: null,
        response: null,
        student_name: "محمد أحمد السبيعي",
        student_id: 5,
      }]);
    }
    if (path.endsWith("/referrals/mine/")) {
      return fulfillJson(route, { count: 1, next: null, previous: null, results: [REFERRAL_ROW] });
    }
    if (path.endsWith("/referrals/7/")) return fulfillJson(route, REFERRAL_DETAIL);
    if (path.endsWith("/referrals/options/")) {
      return fulfillJson(route, {
        source_type: "TEACHER",
        can_assign: false,
        categories: [{
          value: "CLASSROOM_BEHAVIOR",
          label: "سلوك صفي",
          reasons: [{ value: "SLEEPING_IN_CLASS", label: "النوم داخل الحصة" }],
        }],
        observation_types: [{ value: "OTHER_OBSERVATION", label: "ملاحظة أخرى" }],
      });
    }
    return fulfillJson(route, { code: "NOT_FOUND", message: "المورد المطلوب غير موجود.", details: {} }, 404);
  });
}

async function assertNoPageOverflow(page: Page) {
  const dimensions = await page.evaluate(() => ({
    viewport: document.documentElement.clientWidth,
    content: document.documentElement.scrollWidth,
  }));
  expect(dimensions.content).toBeLessThanOrEqual(dimensions.viewport + 1);
}

async function screenshot(page: Page, testInfo: TestInfo, name: string) {
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: testInfo.outputPath(name), fullPage: true });
}

test("teacher mobile templates remain focused and responsive with realistic data", async ({ page }, testInfo) => {
  await installTeacherApi(page);
  await page.setViewportSize({ width: 390, height: 844 });

  await page.goto("/");
  await expect(page.getByRole("heading", { name: "مرحبًا أحمد المعلم" })).toBeVisible();
  await expect(page.getByTestId("sections-list")).toContainText("فصل الموهوبين ١");
  await assertNoPageOverflow(page);
  await screenshot(page, testInfo, "teacher-home-phone.png");

  await page.goto("/attendance/section/3");
  await expect(page.getByTestId("attendance-start-confirmation")).toContainText("الأول الثانوي - المسار العام");
  await assertNoPageOverflow(page);
  await page.getByTestId("start-attendance").click();
  await expect(page.getByTestId("roster-list")).toContainText("عبدالرحمن محمد عبدالله القحطاني");
  await expect(page.getByTestId("roster-student-11").getByRole("button", { name: "حاضر" })).toBeVisible();
  await assertNoPageOverflow(page);
  await screenshot(page, testInfo, "teacher-attendance-phone.png");

  await page.setViewportSize({ width: 360, height: 800 });
  await page.goto("/teacher/follow-ups");
  await expect(page.getByTestId("follow-up-41")).toContainText("كيف كان تفاعل الطالب");
  await page.getByTestId("respond-41").click();
  await expect(page.getByTestId("response-observation")).toBeVisible();
  await assertNoPageOverflow(page);
  await screenshot(page, testInfo, "teacher-follow-up-phone.png");

  await page.goto("/referrals/mine");
  await expect(page.getByTestId("referral-row-7")).toContainText("محمد أحمد السبيعي");
  await page.getByTestId("open-referral-7").click();
  await expect(page.getByTestId("referral-metrics-list")).toBeVisible();
  await expect(page.getByTestId("metric-card-absent_periods")).toContainText("5");
  await assertNoPageOverflow(page);
  await screenshot(page, testInfo, "teacher-referral-phone.png");

  await page.getByRole("button", { name: "فتح قائمة التنقل" }).click();
  const navigation = page.locator("#mobile-navigation");
  await expect(navigation.getByRole("link")).toHaveCount(3);
  await expect(navigation.getByRole("link", { name: "التحضير" })).toBeVisible();
  await expect(navigation.getByRole("link", { name: "طلبات المتابعة" })).toBeVisible();
  await expect(navigation.getByRole("link", { name: "إحالاتي" })).toBeVisible();
  await expect(page.getByTestId("user-roles-mobile")).toHaveText("معلم");
  await assertNoPageOverflow(page);
});
