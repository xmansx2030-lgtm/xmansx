import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import { queryClient } from "@/app/queryClient";
import { buildMe, membership, mockApi } from "@/test/mockApi";
import { renderApp } from "@/test/renderApp";

function roleMe(roles: string[]) {
  return buildMe({
    active_school: { id: 10, name: "ثانوية الأندلس", slug: "andalus" },
    roles: roles as never,
    memberships: [membership(1, 10, "ثانوية الأندلس", roles as never)],
  });
}

const OVERVIEW = {
  context: {
    academic_year: { id: 1, name: "1447/1448" },
    semester: { id: 2, name: "الفصل الأول" },
    timezone: "Asia/Riyadh",
    today: "2026-08-19",
    range: { from_date: "2026-08-13", to_date: "2026-08-19", days: 7, preset: "LAST_7_DAYS" },
    previous_range: {
      from_date: "2026-08-06",
      to_date: "2026-08-12",
      days: 7,
      preset: "LAST_7_DAYS",
    },
    scope: { grade_id: null, section_id: null },
  },
  today_operations: {
    school_time: "09:15",
    date: "2026-08-19",
    period: { sequence: 3, name: "الحصة الثالثة", start_time: "09:00", end_time: "09:45" },
    alert: null,
    summary: { total: 12, submitted: 9, in_progress: 1, not_started: 2, overdue_total: 2 },
    submission_completion_pct: 75,
    has_active_period: true,
    live_attendance: {
      status: "AVAILABLE",
      total_students: 320,
      covered_students: 280,
      pending_students: 40,
      present_students: 250,
      absent_students: 18,
      leave_students: 5,
      late_students: 12,
      morning_late_students: 7,
      daily_absent_students: 9,
      daily_covered_students: 260,
      daily_pending_sections: 3,
      covered_sections: 10,
      pending_sections: 2,
      current_period_sequence: 3,
    },
    daily_attendance: {
      total_students: 320,
      present_students: 297,
      absent_students: 23,
      unrecorded_students: 0,
    },
  },
  attendance: {
    unit: "STUDENT_DAYS",
    student_days: 400,
    distinct_students: 80,
    full_absence_days: 30,
    partial_absence_days: 12,
    no_absence_days: 340,
    undetermined_days: 18,
    unexcused_full_absence_days: 21,
    excused_full_absence_days: 8,
    mixed_full_absence_days: 1,
    absent_periods: 260,
    unexcused_absent_periods: 200,
    excused_absent_periods: 60,
    period_late_occurrences: 14,
    period_late_minutes: 90,
    morning_late_occurrences: 25,
    morning_late_minutes: 180,
    morning_arrivals: 350,
    completeness: {
      complete_student_days: 382,
      incomplete_student_days: 18,
      incomplete_pct: 4.5,
      is_significant: false,
    },
  },
  comparison: {
    unexcused_full_absence_days: {
      current: 21,
      previous: 14,
      delta: 7,
      change_pct: 50,
      is_new: false,
    },
    full_absence_days: { current: 30, previous: 30, delta: 0, change_pct: 0, is_new: false },
    partial_absence_days: {
      current: 12,
      previous: 0,
      delta: 12,
      change_pct: null,
      is_new: true,
    },
    morning_late_occurrences: {
      current: 25,
      previous: 40,
      delta: -15,
      change_pct: -37.5,
      is_new: false,
    },
    absent_periods: { current: 260, previous: 250, delta: 10, change_pct: 4, is_new: false },
  },
  warnings: {
    academic_year: { id: 1, name: "1447/1448" },
    due_is_point_in_time: true,
    due_students_by_type: {
      UNEXCUSED_FULL_DAY_ABSENCE: 4,
      MORNING_LATE_OCCURRENCES: 2,
    },
    issued_students_by_type: { UNEXCUSED_FULL_DAY_ABSENCE: 3, MORNING_LATE_OCCURRENCES: 1 },
    issued_in_range: {
      total: 5,
      level_1: 3,
      level_2: 2,
      level_3: 0,
      by_type: { UNEXCUSED_FULL_DAY_ABSENCE: 4, MORNING_LATE_OCCURRENCES: 1 },
    },
  },
  actions: { total: 9, by_type: { GUARDIAN_CALL: 6, GUARDIAN_SUMMON: 3 } },
  documents: { ready: 6, pending: 1, failed: 0, by_type: { WARNING_NOTICE: 6 } },
  referrals: {
    created_in_range: { total: 4, new: 2, acknowledged: 1, closed: 1, cancelled: 0 },
    by_category: { ATTENDANCE: 3, ACADEMIC: 1 },
    by_source: { TEACHER: 3, VICE_PRINCIPAL: 1 },
    open_now: 3,
    unassigned_now: 1,
  },
  counseling: {
    available: true,
    reason: null,
    open_cases: 7,
    waiting_teacher_responses: 2,
    overdue_activities: 1,
  },
};

const TREND = {
  unit: "STUDENT_DAYS",
  granularity: "DAY",
  context: { range: OVERVIEW.context.range, scope: OVERVIEW.context.scope },
  points: [
    {
      date: "2026-08-17",
      full_absence: 10,
      partial_absence: 4,
      unexcused_full_absence: 7,
      undetermined: 6,
      morning_late: 9,
    },
    {
      date: "2026-08-18",
      full_absence: 12,
      partial_absence: 5,
      unexcused_full_absence: 8,
      undetermined: 6,
      morning_late: 8,
    },
    {
      date: "2026-08-19",
      full_absence: 8,
      partial_absence: 3,
      unexcused_full_absence: 6,
      undetermined: 6,
      morning_late: 8,
    },
  ],
};

const SECTIONS = {
  unit: "STUDENT_DAYS",
  context: { range: OVERVIEW.context.range, scope: OVERVIEW.context.scope },
  sections: [
    {
      section_id: 3,
      section_name: "2",
      grade_name: "الأول الثانوي",
      students: 28,
      student_days: 140,
      full_absence_days: 18,
      partial_absence_days: 7,
      unexcused_full_absence_days: 13,
      period_late_occurrences: 6,
      morning_late_occurrences: 11,
    },
  ],
};

const ATTENTION = {
  total: 2,
  item_cap_per_kind: 10,
  counts: {
    attendance_overdue: 1,
    warning_due: 1,
    excuse_pending: 0,
    referral_unassigned: 0,
    counseling: 0,
  },
  items: [
    {
      kind: "ATTENDANCE_OVERDUE",
      entity_type: "SECTION",
      entity_id: 3,
      reason_code: "SECTION_NOT_SUBMITTED",
      display_text: "الأول الثانوي / 2 — متأخر 14 دقيقة",
      priority: "HIGH",
      target_url: "/attendance/monitoring",
      occurred_at: null,
    },
    {
      kind: "WARNING_DUE",
      entity_type: "STUDENT",
      entity_id: 5,
      reason_code: "WARNING_THRESHOLD_REACHED",
      display_text: "محمد أحمد — بلغ عتبة LEVEL_1 (5)",
      priority: "HIGH",
      target_url: "/warnings",
      occurred_at: null,
    },
  ],
};

function mockDashboard(overrides: Record<string, unknown> = {}) {
  return mockApi({
    "/auth/me/": { body: roleMe(["SCHOOL_MANAGER"]) },
    "/attendance/sections/": {
      body: [
        { id: 3, name: "2", grade_id: 1, grade_name: "الأول الثانوي", students_count: 28 },
        { id: 4, name: "1", grade_id: 2, grade_name: "الثاني الثانوي", students_count: 25 },
      ],
    },
    "/dashboard/today/": { body: OVERVIEW.today_operations },
    "/dashboard/overview/": { body: OVERVIEW },
    "/dashboard/attendance-trend/": { body: TREND },
    "/dashboard/sections/": { body: SECTIONS },
    "/dashboard/attention/": { body: ATTENTION },
    "/staff/": { body: { count: 4, next: null, previous: null, results: [] } },
    ...overrides,
  });
}

describe("لوحة إدارة المدرسة", () => {
  beforeEach(() => {
    queryClient.clear();
  });

  it("تعرض المؤشرات بوحدتها والمقارنة كما حسبها الخادم", async () => {
    mockDashboard();
    renderApp("/dashboard");

    expect(await screen.findByTestId("kpi-unexcused-full")).toHaveTextContent("21");
    expect(screen.getByTestId("kpi-excused-full")).toHaveTextContent("8");
    expect(screen.getByTestId("kpi-undetermined")).toHaveTextContent("18");
    expect(screen.getByTestId("unit-note")).toHaveTextContent("أيام-طالب");

    // المؤشران الصباحي والحصصي منفصلان — رقمان مختلفان لا مجموع واحد
    expect(screen.getByTestId("kpi-morning-late")).toHaveTextContent("25");
    expect(screen.getByTestId("kpi-period-late")).toHaveTextContent("14");

    expect(
      within(screen.getByTestId("kpi-unexcused-full")).getByTestId("comparison-pct"),
    ).toHaveTextContent("50%");
  });

  it("أساس صفري يظهر «جديد» لا نسبة لا نهائية", async () => {
    mockDashboard();
    renderApp("/dashboard");

    const partial = await screen.findByTestId("kpi-partial");
    expect(within(partial).getByTestId("comparison-new")).toHaveTextContent("جديد");
    expect(within(partial).queryByTestId("comparison-pct")).toBeNull();
  });

  it("تعلن الفترة المقارَن بها صراحةً بطولها", async () => {
    mockDashboard();
    renderApp("/dashboard");

    const range = await screen.findByTestId("dashboard-range");
    expect(range).toHaveTextContent("2026-08-13");
    expect(range).toHaveTextContent("2026-08-06");
    expect(range).toHaveTextContent("7 يومًا");
  });

  it("تحذر من نقص البيانات حين يكون النقص جوهريًا", async () => {
    mockDashboard();
    renderApp("/dashboard");
    await screen.findByTestId("kpi-unexcused-full");
    expect(screen.queryByTestId("completeness-warning")).toBeNull();

    queryClient.clear();
    mockDashboard({
      "/dashboard/overview/": {
        body: {
          ...OVERVIEW,
          attendance: {
            ...OVERVIEW.attendance,
            completeness: {
              complete_student_days: 200,
              incomplete_student_days: 200,
              incomplete_pct: 50,
              is_significant: true,
            },
          },
        },
      },
    });
    renderApp("/dashboard");
    expect(await screen.findByTestId("completeness-warning")).toHaveTextContent("50%");
  });

  it("تفصل «المستحق» عن «الصادر» ولا تجمعهما", async () => {
    mockDashboard();
    renderApp("/dashboard");

    const card = await screen.findByTestId("card-warnings");
    expect(within(card).getByTestId("warnings-issued")).toHaveTextContent("5");
    expect(within(card).getByTestId("warnings-due")).toHaveTextContent("6");
    expect(card).toHaveTextContent("لحظية");
    expect(card).toHaveTextContent("لا إصدار تلقائي");
  });

  it("تعرض أعداد الحالات الإرشادية بعد دمج م14 وبلا أي نص إرشادي", async () => {
    mockDashboard();
    renderApp("/dashboard");

    const card = await screen.findByTestId("card-counseling");
    expect(within(card).getByTestId("counseling-open")).toHaveTextContent("7");
    // الإحالة ≠ الحالة: العددان مستقلان في اللوحة
    const referrals = await screen.findByTestId("card-referrals");
    expect(within(referrals).getByTestId("referrals-open")).toHaveTextContent("3");
  });

  it("تعلن غياب وحدة الإرشاد بدل رقم بديل", async () => {
    mockDashboard({
      "/dashboard/overview/": {
        body: {
          ...OVERVIEW,
          counseling: {
            available: false,
            reason: "COUNSELING_MODULE_NOT_INSTALLED",
            open_cases: null,
            waiting_teacher_responses: null,
            overdue_activities: null,
          },
        },
      },
    });
    renderApp("/dashboard");
    expect(await screen.findByTestId("counseling-unavailable")).toHaveTextContent(
      "غير مفعّلة",
    );
  });

  it("تعرض الإحالات كأعداد بلا أي نص وصف", async () => {
    mockDashboard();
    renderApp("/dashboard");

    const card = await screen.findByTestId("card-referrals");
    expect(within(card).getByTestId("referrals-created")).toHaveTextContent("4");
    expect(within(card).getByTestId("referrals-open")).toHaveTextContent("3");
    expect(card).toHaveTextContent("لا تُعرض في لوحة الإدارة");
  });

  it("تعرض طابور المتابعة بروابط الانتقال وبلا حكم على الطالب", async () => {
    mockDashboard();
    renderApp("/dashboard");

    const section = await screen.findByTestId("attention-section");
    expect(section).toHaveTextContent("ليست تصنيفًا للطلاب");
    // ترويسة القسم تظهر قبل وصول البيانات — ننتظر العدّاد نفسه
    expect(await screen.findByTestId("attention-count-attendance_overdue")).toHaveTextContent(
      "1",
    );
    const row = screen.getByTestId("attention-item-ATTENDANCE_OVERDUE-3");
    expect(row).toHaveTextContent("أولوية عالية");
    expect(within(row).getByRole("link", { name: "متابعة التحضير" })).toHaveAttribute(
      "href",
      "/attendance/monitoring",
    );
  });

  it("تعرض حالة المدرسة والحصة بتغطية واضحة بدل دمج الطلاب غير المحضّرين", async () => {
    mockDashboard();
    renderApp("/dashboard");

    const card = await screen.findByTestId("school-today-status-card");
    expect(screen.getByTestId("school-daily-present")).toHaveTextContent("297");
    expect(screen.getByTestId("school-continuous-absent")).toHaveTextContent("9");
    expect(screen.getByTestId("school-current-leave")).toHaveTextContent("5");
    expect(screen.getByTestId("school-current-period-line")).toHaveTextContent("250 حاضرًا");
    expect(screen.getByTestId("school-current-period-line")).toHaveTextContent("18 غائبًا عن الحصة");
    expect(screen.getByTestId("school-current-period-line")).toHaveTextContent("12 متأخرًا");
    expect(screen.getByTestId("school-current-period-line")).toHaveTextContent("بانتظار تحضير 2 فصل");
    expect(screen.getByTestId("school-coverage-line")).toHaveTextContent("260 من 320 طالبًا");
    expect(card).not.toHaveTextContent("الغياب اليوم");
  });

  it("لا تعرض غياب حصة واحدة كأنه الغياب المتتابع لليوم", async () => {
    mockDashboard();
    renderApp("/dashboard");

    const card = await screen.findByTestId("school-today-status-card");
    expect(screen.getByTestId("school-continuous-absent")).toHaveTextContent("9");
    expect(card).not.toHaveTextContent("23");
    expect(card).toHaveTextContent("الغياب المتتابع لا يشمل غياب حصة واحدة فقط");
  });

  it("لا تبقي الاعتماد المتأخر كمهمة مفتوحة بعد اكتمال كل الفصول", async () => {
    const completedLate = {
      ...OVERVIEW.today_operations,
      operational_state: "ON_TRACK",
      headline: "اكتمل تحضير جميع فصول الحصة الثالثة (اعتمد 1 فصل متأخرًا).",
      submission_completion_pct: 100,
      summary: {
        total: 12,
        submitted: 12,
        in_progress: 0,
        not_started: 0,
        overdue_total: 1,
        overdue_submitted: 1,
        overdue_in_progress: 0,
        overdue_not_started: 0,
      },
    };
    mockDashboard({
      "/dashboard/today/": { body: completedLate },
      "/dashboard/overview/": { body: { ...OVERVIEW, today_operations: completedLate } },
      "/dashboard/attention/": {
        body: {
          total: 0,
          counts: { attendance_overdue: 0, warning_due: 0, excuse_pending: 0, referral_unassigned: 0, counseling: 0 },
          items: [],
          item_cap_per_kind: 10,
        },
      },
    });
    renderApp("/dashboard");

    expect(await screen.findByTestId("today-card")).toHaveAttribute("data-state", "ON_TRACK");
    expect(screen.getByTestId("overdue-total")).toHaveTextContent("0");
    expect(screen.getByText(/اعتمد متأخرًا: 1 فصل/)).toBeInTheDocument();
    expect(screen.getByText("التشغيل مكتمل")).toBeInTheDocument();
  });

  it("تعطي الوكيل محطة تشغيل مختلفة مع نفس التحليلات والتقارير", async () => {
    mockDashboard();
    const managerView = renderApp("/dashboard");
    expect(await within(managerView.container).findByTestId("school-today-status-card")).toBeInTheDocument();
    expect(screen.queryByTestId("role-workspace")).not.toBeInTheDocument();
    const managerQuickActions = screen.getByRole("navigation", { name: "إجراءات سريعة" });
    expect(within(managerQuickActions).getAllByRole("link")).toHaveLength(3);
    expect(within(managerQuickActions).getByRole("link", { name: "متابعة التحضير" })).toBeInTheDocument();
    expect(within(managerQuickActions).getByRole("link", { name: "فريق المدرسة" })).toBeInTheDocument();
    expect(within(managerQuickActions).getByRole("link", { name: "إعدادات المدرسة" })).toBeInTheDocument();
    expect(screen.getByTestId("manager-analytics")).not.toHaveAttribute("open");
    expect(screen.getByTestId("additional-navigation")).not.toHaveAttribute("open");
    managerView.unmount();

    queryClient.clear();
    const { calls } = mockDashboard({ "/auth/me/": { body: roleMe(["VICE_PRINCIPAL"]) } });
    renderApp("/dashboard");
    await screen.findByTestId("school-today-status-card");
    const vicePrincipalWorkspace = await screen.findByTestId("role-workspace");
    expect(vicePrincipalWorkspace).toHaveAttribute("data-role", "VICE_PRINCIPAL");
    expect(vicePrincipalWorkspace).toHaveTextContent("محطة عمل الوكيل");
    expect(within(vicePrincipalWorkspace).getByRole("link", { name: /معالجة التحضير المتأخر/ })).toHaveAttribute("href", "/attendance/monitoring");
    expect(within(vicePrincipalWorkspace).getByRole("link", { name: "مراجعة الأعذار" })).toHaveAttribute("href", "/excuses");
    expect(within(vicePrincipalWorkspace).getByRole("link", { name: "استئذان طالب" })).toHaveAttribute("href", "/student-leaves");

    const additionalNavigation = screen.getByTestId("additional-navigation");
    expect(additionalNavigation).not.toHaveAttribute("open");
    await userEvent.click(within(additionalNavigation).getByText("أدوات إضافية"));
    expect(within(additionalNavigation).getByRole("link", { name: "الموظفون" })).toHaveAttribute("href", "/staff");

    expect(screen.queryByRole("navigation", { name: "إجراءات سريعة" })).not.toBeInTheDocument();
    expect(screen.queryByTestId("role-workspace-metric")).not.toBeInTheDocument();
    expect(screen.queryByTestId("daily-attendance-card")).not.toBeInTheDocument();
    expect(screen.queryByTestId("live-school-attendance")).not.toBeInTheDocument();
    expect(screen.getByTestId("manager-analytics")).not.toHaveAttribute("open");
    expect(screen.getByTestId("dashboard-preset")).toBeInTheDocument();
    expect(screen.getByText("اتجاه الغياب")).toBeInTheDocument();
    expect(screen.getByText("الفصول الأكثر احتياجًا للمتابعة")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "ما يحتاج تدخلك" })).toBeInTheDocument();
    expect(screen.queryByTestId("attention-count-excuse_pending")).not.toBeInTheDocument();
    expect(calls.some((call) => call.url.includes("/dashboard/overview/"))).toBe(true);
    expect(calls.some((call) => call.url.includes("/dashboard/attendance-trend/"))).toBe(true);
    expect(calls.some((call) => call.url.includes("/dashboard/sections/"))).toBe(true);
    expect(calls.some((call) => call.url.includes("/staff/"))).toBe(false);
  });

  it("تنبه المدير إلى استيراد الطلاب والفصول والمعلمين عند غياب بياناتهم", async () => {
    mockDashboard({
      "/attendance/sections/": { body: [] },
      "/staff/": { body: { count: 0, next: null, previous: null, results: [] } },
    });
    renderApp("/dashboard");

    const alerts = await screen.findByTestId("school-setup-alerts");
    expect(alerts).toHaveTextContent("استكمل بيانات المدرسة");
    expect(within(alerts).getByTestId("setup-alert-students")).toHaveTextContent(
      "استورد بيانات الطلاب والفصول من ملف إكسل (نور)",
    );
    expect(within(alerts).getByTestId("setup-alert-teachers")).toHaveTextContent(
      "استورد بيانات المعلمين من ملف إكسل (نور)",
    );
    expect(within(alerts).getAllByRole("link", { name: "بدء الاستيراد" })[0]).toHaveAttribute(
      "href",
      "/students/import",
    );
    expect(within(alerts).getAllByRole("link", { name: "بدء الاستيراد" })[1]).toHaveAttribute(
      "href",
      "/staff/import",
    );
  });

  it("لا تعرض تنبيهات الاستيراد للمدير بعد توفر الطلاب والمعلمين", async () => {
    mockDashboard();
    renderApp("/dashboard");

    await screen.findByTestId("school-today-status-card");
    expect(screen.queryByTestId("school-setup-alerts")).not.toBeInTheDocument();
  });

  it("تعرض للمدير والوكيل الحضور اليومي والغياب المتتابع والاستئذان بالدلالة نفسها", async () => {
    const scenario = {
      ...OVERVIEW.today_operations,
      summary: { total: 10, submitted: 10, in_progress: 0, not_started: 0, overdue_total: 0 },
      submission_completion_pct: 100,
      daily_attendance: {
        total_students: 800,
        present_students: 500,
        // غاب بعض هؤلاء عن حصة واحدة فقط؛ لا ينبغي عرضه كغياب متتابع.
        absent_students: 380,
        unrecorded_students: 0,
      },
      live_attendance: {
        ...OVERVIEW.today_operations.live_attendance,
        total_students: 800,
        covered_students: 800,
        pending_students: 0,
        present_students: 420,
        absent_students: 330,
        leave_students: 50,
        late_students: 0,
        daily_absent_students: 300,
        daily_covered_students: 800,
        daily_pending_sections: 0,
        covered_sections: 10,
        pending_sections: 0,
      },
    };
    for (const role of ["SCHOOL_MANAGER", "VICE_PRINCIPAL"] as const) {
      mockDashboard({
        "/auth/me/": { body: roleMe([role]) },
        "/dashboard/today/": { body: scenario },
        "/dashboard/overview/": { body: { ...OVERVIEW, today_operations: scenario } },
      });
      const view = renderApp("/dashboard");

      const card = await screen.findByTestId("school-today-status-card");
      expect(within(card).getByTestId("school-daily-present")).toHaveTextContent("500");
      expect(within(card).getByTestId("school-continuous-absent")).toHaveTextContent("300");
      expect(within(card).getByTestId("school-current-leave")).toHaveTextContent("50");
      expect(within(card).getByTestId("school-current-period-line")).toHaveTextContent("420 حاضرًا");
      expect(within(card).getByTestId("school-current-period-line")).toHaveTextContent("330 غائبًا عن الحصة");
      expect(within(card).getByTestId("school-current-period-line")).toHaveTextContent("50 مستأذنًا");
      expect(within(card).getByTestId("school-coverage-line")).toHaveTextContent("مكتملة لجميع 800 طالبًا");
      expect(card).not.toHaveTextContent("380");

      view.unmount();
      queryClient.clear();
    }
  });

  it("ترسم الاتجاه بنقطة لكل يوم مع جدول مكافئ", async () => {
    mockDashboard();
    renderApp("/dashboard");

    const chart = await screen.findByTestId("trend-chart");
    expect(chart).toHaveAttribute("data-points", "3");
    expect(chart).toHaveAttribute("data-granularity", "DAY");
    const table = screen.getByTestId("trend-table");
    expect(within(table).getByText("2026-08-18")).toBeInTheDocument();
  });

  it("تخفي سلسلة عند إطفائها من المفتاح", async () => {
    mockDashboard();
    renderApp("/dashboard");
    await screen.findByTestId("trend-chart");

    expect(screen.getByTestId("trend-series-morning_late")).toBeInTheDocument();
    await userEvent.click(screen.getByTestId("trend-toggle-morning_late"));
    expect(screen.queryByTestId("trend-series-morning_late")).toBeNull();
  });

  it("تنبّه إلى التجميع الأسبوعي في الفترات الطويلة", async () => {
    mockDashboard({
      "/dashboard/attendance-trend/": { body: { ...TREND, granularity: "WEEK" } },
    });
    renderApp("/dashboard");
    expect(await screen.findByTestId("trend-aggregated")).toHaveTextContent("أسبوعيًا");
  });

  it("تمرر فلاتر الفترة والفصل إلى الخادم ولا تحسبها محليًا", async () => {
    const { calls } = mockDashboard();
    renderApp("/dashboard");
    await screen.findByTestId("kpi-unexcused-full");

    await userEvent.selectOptions(screen.getByTestId("dashboard-preset"), "THIS_MONTH");
    await userEvent.selectOptions(screen.getByTestId("dashboard-section"), "3");

    const overviewCalls = calls.filter((c) => c.url.includes("/dashboard/overview/"));
    const last = overviewCalls[overviewCalls.length - 1]?.url ?? "";
    expect(last).toContain("preset=THIS_MONTH");
    expect(last).toContain("section=3");
  });

  it("اختيار صف يصفّر الفصل حتى لا يُرسل فصل من صف آخر", async () => {
    mockDashboard();
    renderApp("/dashboard");
    await screen.findByTestId("kpi-unexcused-full");

    await userEvent.selectOptions(screen.getByTestId("dashboard-section"), "3");
    expect(screen.getByTestId("dashboard-section")).toHaveValue("3");

    await userEvent.selectOptions(screen.getByTestId("dashboard-grade"), "2");
    expect(screen.getByTestId("dashboard-section")).toHaveValue("");
    // وقائمة الفصول تنحصر في الصف المختار
    expect(within(screen.getByTestId("dashboard-section")).queryByText(/الأول الثانوي/)).toBeNull();
  });

  it("تعرض جدول الفصول بترتيب وصفي مع تنويه عدم عدالة المقارنة المباشرة", async () => {
    mockDashboard();
    renderApp("/dashboard");

    const table = await screen.findByTestId("sections-table");
    expect(within(table).getByTestId("section-row-3")).toHaveTextContent("13");
    expect(screen.getByText(/لا يقيس أداء معلم/)).toBeInTheDocument();
  });

  it("تُظهر خطأ الخادم بدل أرقام فارغة", async () => {
    mockDashboard({
      "/dashboard/overview/": {
        status: 400,
        body: {
          code: "DASHBOARD_INVALID_DATE_RANGE",
          message: "تاريخ البداية بعد تاريخ النهاية.",
          details: {},
        },
      },
    });
    renderApp("/dashboard");
    expect(await screen.findByText("تاريخ البداية بعد تاريخ النهاية.")).toBeInTheDocument();
    expect(screen.queryByTestId("dashboard-kpis")).toBeNull();
  });

  it("تجمع غياب العام الدراسي في حالة إعداد واحدة قابلة للتصرف", async () => {
    const noActiveYear = {
      status: 409,
      body: {
        code: "ACTIVE_ACADEMIC_YEAR_REQUIRED",
        message: "لم يتم العثور على عام دراسي نشط لهذه المدرسة.",
        details: {},
      },
    };
    mockDashboard({
      "/dashboard/overview/": noActiveYear,
      "/dashboard/attendance-trend/": noActiveYear,
      "/dashboard/sections/": noActiveYear,
      "/dashboard/attention/": noActiveYear,
    });

    renderApp("/dashboard");
    const setup = await screen.findByTestId("academic-setup-required");
    expect(setup).toHaveTextContent("يلزم تفعيل عام دراسي");
    expect(within(setup).getByRole("link", { name: "إعداد العام الدراسي" })).toHaveAttribute(
      "href",
      "/settings?section=calendar",
    );
    expect(screen.queryByText("اتجاه الغياب")).toBeNull();
    expect(screen.queryByTestId("attention-section")).toBeNull();
  });

  it("لا حصة جارية: حالة مفهومة لا خطأ", async () => {
    const noActivePeriod = {
      ...OVERVIEW.today_operations,
      period: null,
      summary: null,
      submission_completion_pct: null,
      has_active_period: false,
      operational_state: "IDLE",
      headline: "لا توجد حصة جارية الآن",
    };
    mockDashboard({
      "/dashboard/today/": { body: noActivePeriod },
      "/dashboard/overview/": {
        body: {
          ...OVERVIEW,
          today_operations: noActivePeriod,
        },
      },
    });
    renderApp("/dashboard");
    expect(await screen.findByTestId("no-active-period")).toHaveTextContent("لا توجد حصة جارية");
  });

  it("رابط اللوحة يظهر للمدير ويختفي عن المعلم والمرشد", async () => {
    mockDashboard();
    renderApp("/");
    expect(await screen.findByRole("link", { name: "لوحة الإدارة" })).toBeInTheDocument();

    for (const role of ["TEACHER", "COUNSELOR"]) {
      queryClient.clear();
      mockDashboard({ "/auth/me/": { body: roleMe([role]) } });
      const view = renderApp("/");
      await within(view.container).findByTestId("active-school-name");
      expect(within(view.container).queryByRole("link", { name: "لوحة الإدارة" })).toBeNull();
      view.unmount();
    }
  });
});
