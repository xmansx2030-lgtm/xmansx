import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import { queryClient } from "@/app/queryClient";
import type {
  DailyAnalyticsResponse,
  MultiPeriodResponse,
} from "@/features/attendance/api";
import { buildMe, membership, mockApi } from "@/test/mockApi";
import { renderApp } from "@/test/renderApp";

function viceMe() {
  return buildMe({
    active_school: { id: 10, name: "ثانوية الأندلس", slug: "andalus" },
    roles: ["VICE_PRINCIPAL"],
    memberships: [membership(1, 10, "ثانوية الأندلس", ["VICE_PRINCIPAL"])],
  });
}

const DAY_PERIODS = [
  { sequence: 1, name: "الحصة الأولى" },
  { sequence: 2, name: "الحصة الثانية" },
  { sequence: 3, name: "الحصة الثالثة" },
];

function dailyBody(overrides: Partial<DailyAnalyticsResponse> = {}): DailyAnalyticsResponse {
  return {
    date: "2026-08-19",
    is_school_day: true,
    expected_periods: 3,
    day_periods: DAY_PERIODS,
    summary: {
      total_students: 60,
      complete_students: 50,
      incomplete_students: 10,
      full_absent: 2,
      partial_absent: 5,
      no_absence: 43,
      undetermined: 8,
      late_students: 4,
      late_occurrences: 6,
      late_minutes: 73,
    },
    students: [],
    page: 1,
    page_size: 25,
    total_students_filtered: 0,
    ...overrides,
  };
}

function multiBody(overrides: Partial<MultiPeriodResponse> = {}): MultiPeriodResponse {
  return {
    date: "2026-08-19",
    periods: DAY_PERIODS.slice(0, 2),
    match: "ALL_ABSENT",
    summary: { matching_students: 1, complete_sections: 2, incomplete_sections: 1 },
    students: [
      {
        student_id: 11,
        full_name: "محمد أحمد",
        grade_name: "الأول الثانوي",
        section_name: "2",
        period_statuses: [
          { sequence: 1, status: "ABSENT" },
          { sequence: 2, status: "ABSENT" },
        ],
      },
    ],
    incomplete_sections: [
      {
        section_id: 3,
        section_name: "3",
        grade_name: "الأول الثانوي",
        missing_sequences: [2],
        reason: "الحصة الثانية: لم يتم التحضير",
      },
    ],
    day_periods: DAY_PERIODS,
    page: 1,
    page_size: 25,
    total_students: 1,
    ...overrides,
  };
}

const SECTIONS = [
  { id: 1, name: "1", grade_id: 100, grade_name: "الأول الثانوي", students_count: 25 },
  { id: 2, name: "1", grade_id: 200, grade_name: "الثاني الثانوي", students_count: 25 },
];

function parseBody(init?: RequestInit): Record<string, unknown> {
  return JSON.parse(String(init?.body ?? "{}")) as Record<string, unknown>;
}

describe("attendance analytics", () => {
  beforeEach(() => {
    queryClient.clear();
    document.cookie = "csrftoken=test-token";
  });

  it("runs a single-period report and shows absentees with incomplete warning", async () => {
    const { calls } = mockApi({
      "/auth/me/": { body: viceMe() },
      "/attendance/analytics/daily/": { body: dailyBody() },
      "/attendance/analytics/multi-period/": { body: multiBody() },
      "/attendance/sections/": { body: SECTIONS },
    });

    renderApp("/attendance/analytics");
    const user = userEvent.setup();

    await user.click(await screen.findByTestId("period-option-1"));
    await user.click(screen.getByTestId("run-report"));

    expect(await screen.findByTestId("report-summary")).toHaveTextContent("1 طالبًا");
    expect(screen.getByTestId("analytics-student-11")).toHaveTextContent("محمد أحمد");
    expect(screen.getByTestId("analytics-student-11")).toHaveTextContent(
      "الحصة الأولى: غائب",
    );
    expect(screen.getByTestId("incomplete-warning")).toHaveTextContent(
      "الحصة الثانية: لم يتم التحضير",
    );
    const post = calls.find((c) => c.url.includes("/multi-period/"));
    expect(parseBody(post?.init).period_sequences).toEqual([1]);
    expect(parseBody(post?.init)).not.toHaveProperty("school_id");
  });

  it("single-period tab keeps exactly one selected period", async () => {
    mockApi({
      "/auth/me/": { body: viceMe() },
      "/attendance/analytics/daily/": { body: dailyBody() },
      "/attendance/sections/": { body: SECTIONS },
    });

    renderApp("/attendance/analytics");
    const user = userEvent.setup();
    await user.click(await screen.findByTestId("period-option-1"));
    await user.click(screen.getByTestId("period-option-3"));
    expect(screen.getByTestId("period-option-3")).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByTestId("period-option-1")).toHaveAttribute("aria-pressed", "false");
  });

  it("multi tab: selects periods, morning preset is editable, match mode sent", async () => {
    const { calls } = mockApi({
      "/auth/me/": { body: viceMe() },
      "/attendance/analytics/daily/": { body: dailyBody() },
      "/attendance/analytics/multi-period/": { body: multiBody() },
      "/attendance/sections/": { body: SECTIONS },
    });

    renderApp("/attendance/analytics");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("tab", { name: "عدة حصص" }));

    // ‏preset صباحي = الأولى+الثانية — ثم يضيف الوكيل الثالثة (ليس hard-code)
    await user.click(await screen.findByTestId("morning-preset"));
    expect(screen.getByTestId("period-option-1")).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByTestId("period-option-2")).toHaveAttribute("aria-pressed", "true");
    await user.click(screen.getByTestId("period-option-3"));

    await user.click(screen.getByTestId("match-any"));
    await user.click(screen.getByTestId("run-report"));
    await screen.findByTestId("report-summary");

    const post = calls.find((c) => c.url.includes("/multi-period/"));
    const body = parseBody(post?.init);
    expect(body.period_sequences).toEqual([1, 2, 3]);
    expect(body.match).toBe("ANY_ABSENT");
  });

  it("sends the grade filter with the report request", async () => {
    const { calls } = mockApi({
      "/auth/me/": { body: viceMe() },
      "/attendance/analytics/daily/": { body: dailyBody() },
      "/attendance/analytics/multi-period/": { body: multiBody() },
      "/attendance/sections/": { body: SECTIONS },
    });

    renderApp("/attendance/analytics");
    const user = userEvent.setup();
    await user.click(await screen.findByTestId("period-option-2"));
    await user.selectOptions(await screen.findByTestId("analytics-grade-filter"), "200");
    await user.click(screen.getByTestId("run-report"));
    await screen.findByTestId("report-summary");
    const post = calls.find((c) => c.url.includes("/multi-period/"));
    expect(parseBody(post?.init).grade_id).toBe(200);
  });

  it("shows empty-state message when no students match", async () => {
    mockApi({
      "/auth/me/": { body: viceMe() },
      "/attendance/analytics/daily/": { body: dailyBody() },
      "/attendance/analytics/multi-period/": {
        body: multiBody({
          students: [],
          summary: { matching_students: 0, complete_sections: 3, incomplete_sections: 0 },
          incomplete_sections: [],
          total_students: 0,
        }),
      },
      "/attendance/sections/": { body: SECTIONS },
    });

    renderApp("/attendance/analytics");
    const user = userEvent.setup();
    await user.click(await screen.findByTestId("period-option-1"));
    await user.click(screen.getByTestId("run-report"));
    expect(await screen.findByTestId("no-matching-students")).toBeInTheDocument();
    expect(screen.queryByTestId("incomplete-warning")).not.toBeInTheDocument();
  });

  it("daily tab shows KPI cards including late totals and incomplete", async () => {
    mockApi({
      "/auth/me/": { body: viceMe() },
      "/attendance/analytics/daily/": { body: dailyBody() },
      "/attendance/sections/": { body: SECTIONS },
    });

    renderApp("/attendance/analytics");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("tab", { name: "ملخص اليوم" }));

    const kpis = await screen.findByTestId("daily-kpis");
    expect(within(kpis).getByTestId("daily-full")).toHaveTextContent("2");
    expect(within(kpis).getByTestId("daily-partial")).toHaveTextContent("5");
    expect(within(kpis).getByTestId("daily-incomplete")).toHaveTextContent("10");
    expect(within(kpis).getByTestId("daily-late-occurrences")).toHaveTextContent("6");
    expect(within(kpis).getByTestId("daily-late-minutes")).toHaveTextContent("73");
  });

  it("daily tab lists students for a selected absence status", async () => {
    mockApi({
      "/auth/me/": { body: viceMe() },
      "/attendance/analytics/daily/": (init) => {
        void init;
        return { body: dailyBody() };
      },
      "/attendance/sections/": { body: SECTIONS },
    });
    // قائمة الحالة تعود من نفس endpoint مع ?status= — نعيد mock أدق
    mockApi({
      "/auth/me/": { body: viceMe() },
      "status=FULL": {
        body: dailyBody({
          students: [
            {
              student_id: 9,
              full_name: "غائب كامل",
              grade_name: "الأول الثانوي",
              section_name: "1",
              absent_periods: 3,
              late_periods: 0,
              total_late_minutes: 0,
              submitted_periods: 3,
              expected_periods: 3,
            },
          ],
          total_students_filtered: 1,
        }),
      },
      "/attendance/analytics/daily/": { body: dailyBody() },
      "/attendance/sections/": { body: SECTIONS },
    });

    renderApp("/attendance/analytics");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("tab", { name: "ملخص اليوم" }));
    await user.selectOptions(await screen.findByTestId("daily-status-filter"), "FULL");
    expect(await screen.findByTestId("daily-student-9")).toHaveTextContent("غائب كامل");
    expect(screen.getByTestId("daily-student-9")).toHaveTextContent("غياب 3 من 3");
  });

  it("non-school day shows a clear message instead of selectors", async () => {
    mockApi({
      "/auth/me/": { body: viceMe() },
      "/attendance/analytics/daily/": {
        body: dailyBody({ is_school_day: false, day_periods: [], expected_periods: 0 }),
      },
      "/attendance/sections/": { body: SECTIONS },
    });

    renderApp("/attendance/analytics");
    expect(await screen.findByTestId("not-school-day")).toBeInTheDocument();
    expect(screen.queryByTestId("run-report")).not.toBeInTheDocument();
  });

  it("teacher does not see the analytics nav link", async () => {
    mockApi({
      "/auth/me/": {
        body: buildMe({
          active_school: { id: 10, name: "ثانوية الأندلس", slug: "andalus" },
          roles: ["TEACHER"],
          memberships: [membership(1, 10, "ثانوية الأندلس", ["TEACHER"])],
        }),
      },
      "/attendance/current-period/": { body: { period: null, date: "2026-08-19" } },
      "/attendance/sections/": { body: [] },
    });

    renderApp("/");
    await screen.findByTestId("active-school-name");
    expect(screen.queryByRole("link", { name: "الغياب والحضور" })).not.toBeInTheDocument();
  });

  it("shows API error state for analytics failures", async () => {
    mockApi({
      "/auth/me/": { body: viceMe() },
      "/attendance/analytics/daily/": {
        status: 409,
        body: {
          code: "ACTIVE_ACADEMIC_YEAR_REQUIRED",
          message: "لم يتم العثور على عام دراسي نشط لهذه المدرسة.",
          details: {},
        },
      },
      "/attendance/sections/": { body: SECTIONS },
    });

    renderApp("/attendance/analytics");
    expect(await screen.findByRole("alert")).toHaveTextContent("عام دراسي نشط");
  });
});
