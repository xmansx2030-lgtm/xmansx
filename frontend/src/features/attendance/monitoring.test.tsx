import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import { queryClient } from "@/app/queryClient";
import type { MonitoringResponse, MonitoringSection } from "@/features/attendance/api";
import { buildMe, membership, mockApi } from "@/test/mockApi";
import { renderApp } from "@/test/renderApp";

function viceMe() {
  return buildMe({
    active_school: { id: 10, name: "ثانوية الأندلس", slug: "andalus" },
    roles: ["VICE_PRINCIPAL"],
    memberships: [membership(1, 10, "ثانوية الأندلس", ["VICE_PRINCIPAL"])],
  });
}

function teacherMe() {
  return buildMe({
    active_school: { id: 10, name: "ثانوية الأندلس", slug: "andalus" },
    roles: ["TEACHER"],
    memberships: [membership(1, 10, "ثانوية الأندلس", ["TEACHER"])],
  });
}

function section(overrides: Partial<MonitoringSection>): MonitoringSection {
  return {
    section_id: 1,
    section_name: "1",
    grade_id: 100,
    grade_name: "الأول الثانوي",
    students_count: 25,
    attendance_status: "SUBMITTED",
    timeliness_status: "ON_TIME",
    started_at: "08:37",
    submitted_at: "08:42",
    minutes_overdue: null,
    teacher_name: "أحمد محمد",
    session_id: 11,
    ...overrides,
  };
}

const SECTIONS: MonitoringSection[] = [
  section({
    section_id: 3,
    section_name: "3",
    attendance_status: "NOT_STARTED",
    timeliness_status: "OVERDUE",
    started_at: null,
    submitted_at: null,
    minutes_overdue: 6,
    teacher_name: null,
    session_id: null,
  }),
  section({
    section_id: 2,
    section_name: "2",
    grade_id: 200,
    grade_name: "الثاني الثانوي",
    attendance_status: "IN_PROGRESS",
    timeliness_status: "OVERDUE",
    started_at: "08:45",
    submitted_at: null,
    minutes_overdue: 6,
    teacher_name: "محمد علي",
    session_id: 12,
  }),
  section({ section_id: 1 }),
];

function monitoringBody(overrides: Partial<MonitoringResponse> = {}): MonitoringResponse {
  return {
    school_time: "2026-08-19T09:01:00+03:00",
    date: "2026-08-19",
    period: { sequence: 3, name: "الحصة الثالثة", start_time: "08:30", end_time: "09:15" },
    alert: { minutes: 25, alert_at: "08:55" },
    summary: {
      total: 3,
      submitted: 1,
      in_progress: 1,
      not_started: 1,
      overdue_total: 2,
      overdue_submitted: 0,
      overdue_in_progress: 1,
      overdue_not_started: 1,
    },
    sections: SECTIONS,
    ...overrides,
  };
}

describe("attendance monitoring", () => {
  beforeEach(() => {
    queryClient.clear();
    document.cookie = "csrftoken=test-token";
  });

  it("renders period header, alert time and KPI cards", async () => {
    mockApi({
      "/auth/me/": { body: viceMe() },
      "/attendance/monitoring/current/": { body: monitoringBody() },
    });

    renderApp("/attendance/monitoring");
    expect(await screen.findByTestId("monitoring-period")).toHaveTextContent("الحصة الثالثة");
    expect(screen.getByTestId("monitoring-period")).toHaveTextContent("08:55");
    const kpis = screen.getByTestId("monitoring-kpis");
    expect(within(kpis).getByText("متأخر").previousSibling).toHaveTextContent("2");
    expect(within(kpis).getByText("تم التحضير").previousSibling).toHaveTextContent("1");
  });

  it("shows the three row states with icon + text (not color only)", async () => {
    mockApi({
      "/auth/me/": { body: viceMe() },
      "/attendance/monitoring/current/": { body: monitoringBody() },
    });

    renderApp("/attendance/monitoring");
    const submitted = await screen.findByTestId("monitoring-section-1");
    expect(submitted).toHaveTextContent("✅ تم التحضير");
    expect(submitted).toHaveTextContent("أحمد محمد");
    const inProgress = screen.getByTestId("monitoring-section-2");
    expect(inProgress).toHaveTextContent("بدأ ولم يعتمد — متأخر 6 دقيقة");
    const notStarted = screen.getByTestId("monitoring-section-3");
    expect(notStarted).toHaveTextContent("🔴 لم يتم التحضير — متأخر 6 دقيقة");
    expect(notStarted).toHaveTextContent("—"); // لا معلم لفصل لم يبدأ
    // الترتيب من الخادم يحفظ كما هو: المتأخرون أولًا
    const list = screen.getByTestId("monitoring-list");
    const ids = within(list)
      .getAllByTestId(/monitoring-section-/)
      .map((el) => el.getAttribute("data-testid"));
    expect(ids).toEqual([
      "monitoring-section-3",
      "monitoring-section-2",
      "monitoring-section-1",
    ]);
  });

  it("shows clear empty state when there is no current period", async () => {
    mockApi({
      "/auth/me/": { body: viceMe() },
      "/attendance/monitoring/current/": {
        body: monitoringBody({ period: null, alert: null, summary: null, sections: [] }),
      },
    });

    renderApp("/attendance/monitoring");
    expect(await screen.findByTestId("monitoring-no-period")).toHaveTextContent(
      "لا توجد حصة دراسية نشطة حاليًا",
    );
    expect(screen.queryByTestId("monitoring-kpis")).not.toBeInTheDocument();
  });

  it("KPIs follow the active filters and clear-filters restores them", async () => {
    mockApi({
      "/auth/me/": { body: viceMe() },
      "/attendance/monitoring/current/": { body: monitoringBody() },
    });

    renderApp("/attendance/monitoring");
    const user = userEvent.setup();
    await screen.findByTestId("monitoring-list");

    await user.selectOptions(screen.getByTestId("status-filter"), "OVERDUE");
    expect(screen.queryByTestId("monitoring-section-1")).not.toBeInTheDocument();
    expect(screen.getByTestId("monitoring-section-2")).toBeInTheDocument();
    const kpis = screen.getByTestId("monitoring-kpis");
    expect(within(kpis).getByText("الفصول").previousSibling).toHaveTextContent("2");

    await user.click(screen.getByTestId("clear-filters"));
    expect(screen.getByTestId("monitoring-section-1")).toBeInTheDocument();
    expect(within(screen.getByTestId("monitoring-kpis")).getByText("الفصول").previousSibling)
      .toHaveTextContent("3");
  });

  it("filters by status and by grade", async () => {
    mockApi({
      "/auth/me/": { body: viceMe() },
      "/attendance/monitoring/current/": { body: monitoringBody() },
    });

    renderApp("/attendance/monitoring");
    const user = userEvent.setup();
    await screen.findByTestId("monitoring-list");

    await user.selectOptions(screen.getByTestId("status-filter"), "NOT_STARTED");
    expect(screen.getByTestId("monitoring-section-3")).toBeInTheDocument();
    expect(screen.queryByTestId("monitoring-section-2")).not.toBeInTheDocument();

    await user.selectOptions(screen.getByTestId("status-filter"), "ALL");
    await user.selectOptions(screen.getByTestId("grade-filter"), "200");
    expect(screen.getByTestId("monitoring-section-2")).toBeInTheDocument();
    expect(screen.queryByTestId("monitoring-section-1")).not.toBeInTheDocument();
  });

  it("submitted-late filter shows only late submissions", async () => {
    const late = section({
      section_id: 5,
      section_name: "5",
      timeliness_status: "OVERDUE",
      minutes_overdue: 7,
      submitted_at: "09:02",
    });
    mockApi({
      "/auth/me/": { body: viceMe() },
      "/attendance/monitoring/current/": {
        body: monitoringBody({ sections: [...SECTIONS, late] }),
      },
    });

    renderApp("/attendance/monitoring");
    const user = userEvent.setup();
    await screen.findByTestId("monitoring-list");
    await user.selectOptions(screen.getByTestId("status-filter"), "SUBMITTED_LATE");
    expect(screen.getByTestId("monitoring-section-5")).toHaveTextContent(
      "تم التحضير متأخرًا 7 دقيقة",
    );
    expect(screen.queryByTestId("monitoring-section-1")).not.toBeInTheDocument();
    expect(screen.queryByTestId("monitoring-section-3")).not.toBeInTheDocument();
  });

  it("manual refresh refetches and updates last-updated stamp", async () => {
    let calls = 0;
    mockApi({
      "/auth/me/": { body: viceMe() },
      "/attendance/monitoring/current/": () => {
        calls += 1;
        return { body: monitoringBody() };
      },
    });

    renderApp("/attendance/monitoring");
    const user = userEvent.setup();
    await screen.findByTestId("monitoring-list");
    const before = calls;
    await user.click(screen.getByTestId("manual-refresh"));
    await waitFor(() => expect(calls).toBe(before + 1));
    expect(screen.getByTestId("last-updated")).toHaveTextContent("آخر تحديث");
  });

  it("vice principal sees the home summary card with counts", async () => {
    mockApi({
      "/auth/me/": { body: viceMe() },
      "/attendance/monitoring/current/": { body: monitoringBody() },
    });

    renderApp("/");
    const card = await screen.findByTestId("monitoring-summary-card");
    expect(await within(card).findByTestId("monitoring-summary-line")).toHaveTextContent(
      "3 فصلًا",
    );
    expect(within(card).getByRole("link", { name: "عرض تفاصيل الفصول" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "متابعة التحضير" })).toBeInTheDocument();
  });

  it("teacher sees neither the monitoring nav link nor the summary card", async () => {
    mockApi({
      "/auth/me/": { body: teacherMe() },
      "/attendance/current-period/": { body: { period: null, date: "2026-08-19" } },
      "/attendance/sections/": { body: [] },
    });

    renderApp("/");
    await screen.findByTestId("active-school-name");
    expect(screen.queryByRole("link", { name: "متابعة التحضير" })).not.toBeInTheDocument();
    expect(screen.queryByTestId("monitoring-summary-card")).not.toBeInTheDocument();
  });

  it("shows the API error when monitoring is denied or unavailable", async () => {
    mockApi({
      "/auth/me/": { body: viceMe() },
      "/attendance/monitoring/current/": {
        status: 409,
        body: {
          code: "ACTIVE_ACADEMIC_YEAR_REQUIRED",
          message: "لم يتم العثور على عام دراسي نشط لهذه المدرسة.",
          details: {},
        },
      },
    });

    renderApp("/attendance/monitoring");
    expect(await screen.findByRole("alert")).toHaveTextContent("عام دراسي نشط");
  });
});
