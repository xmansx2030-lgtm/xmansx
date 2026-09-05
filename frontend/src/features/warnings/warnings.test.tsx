import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import { queryClient } from "@/app/queryClient";
import { buildMe, membership, mockApi } from "@/test/mockApi";
import { renderApp } from "@/test/renderApp";

function roleMe(roles: ("SCHOOL_MANAGER" | "VICE_PRINCIPAL" | "TEACHER")[]) {
  return buildMe({
    active_school: { id: 10, name: "ثانوية الأندلس", slug: "andalus" },
    roles,
    memberships: [membership(1, 10, "ثانوية الأندلس", roles)],
  });
}

const RULES = {
  UNEXCUSED_FULL_DAY_ABSENCE: {
    is_enabled: true,
    levels: { LEVEL_1: 3, LEVEL_2: 5, LEVEL_3: 10 },
  },
  MORNING_LATE_OCCURRENCES: {
    is_enabled: true,
    levels: { LEVEL_1: 3, LEVEL_2: 5, LEVEL_3: 10 },
  },
};

const ELIGIBILITY = {
  academic_year: { id: 1, name: "2026/2027" },
  summary: {
    UNEXCUSED_FULL_DAY_ABSENCE: { due_students: 4, issued_students: 1 },
    MORNING_LATE_OCCURRENCES: { due_students: 7, issued_students: 0 },
  },
  results: [
    {
      student_id: 5,
      full_name: "محمد أحمد",
      grade_id: 100,
      grade_name: "الثاني الثانوي",
      section_name: "1",
      warning_type: "UNEXCUSED_FULL_DAY_ABSENCE",
      is_enabled: true,
      current_value: 5,
      highest_reached_level: "LEVEL_2",
      highest_due_level: "LEVEL_2",
      issued_levels: ["LEVEL_1"],
      issued_warnings: [
        { id: 20, level: "LEVEL_1", document: { id: 40, status: "READY" } },
      ],
      levels: {
        LEVEL_1: { threshold: 3, state: "ISSUED" },
        LEVEL_2: { threshold: 5, state: "DUE" },
        LEVEL_3: { threshold: 10, state: "NOT_DUE" },
      },
    },
  ],
  count: 1,
  page: 1,
  page_size: 25,
};

const WARNING_ROW = {
  id: 21,
  student_id: 5,
  student_name: "محمد أحمد",
  grade_name: "الثاني الثانوي",
  section_name: "1",
  warning_type: "UNEXCUSED_FULL_DAY_ABSENCE",
  warning_type_label: "غياب يوم كامل بدون عذر",
  level: "LEVEL_2",
  level_label: "الإنذار الثاني",
  status: "ISSUED",
  threshold_at_issue: 5,
  metric_value_at_issue: 5,
  issued_at: "2026-08-19T09:00:00Z",
  issued_by: "سعد الوكيل",
  notes: "",
  voided_at: null,
  voided_by: null,
  void_reason: "",
};

const WARNING_DOCUMENT = {
  id: 41,
  student_id: 5,
  document_type: "WARNING_LEVEL_2",
  document_type_label: "الإنذار الثاني",
  status: "READY",
  status_label: "جاهز",
  template: "warning_level_2:1",
  warning_id: 21,
  action_id: null,
  generated_at: "2026-08-19T09:01:00Z",
  generated_by_name: "سعد الوكيل",
  size_bytes: 1234,
  checksum: "abc",
  error_code: "",
  can_download: true,
};

function parseBody(init?: RequestInit): Record<string, unknown> {
  return JSON.parse(String(init?.body ?? "{}")) as Record<string, unknown>;
}

describe("warning rules settings (Phase 11)", () => {
  beforeEach(() => {
    queryClient.clear();
    document.cookie = "csrftoken=test-token";
  });

  it("renders absence and late thresholds for the manager", async () => {
    mockApi({
      "/auth/me/": { body: roleMe(["SCHOOL_MANAGER"]) },
      "/warning-rules/": { body: RULES },
    });

    renderApp("/settings");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("tab", { name: "الإنذارات" }));

    const absence = await screen.findByTestId("rule-UNEXCUSED_FULL_DAY_ABSENCE");
    expect(within(absence).getByTestId("threshold-UNEXCUSED_FULL_DAY_ABSENCE-LEVEL_1")).toHaveValue(3);
    expect(within(absence).getByTestId("threshold-UNEXCUSED_FULL_DAY_ABSENCE-LEVEL_3")).toHaveValue(10);
    expect(absence).toHaveTextContent("أيام");
    const late = screen.getByTestId("rule-MORNING_LATE_OCCURRENCES");
    expect(within(late).getByTestId("threshold-MORNING_LATE_OCCURRENCES-LEVEL_2")).toHaveValue(5);
    expect(late).toHaveTextContent("مرات");
  });

  it("blocks saving when thresholds are not ascending", async () => {
    mockApi({
      "/auth/me/": { body: roleMe(["SCHOOL_MANAGER"]) },
      "/warning-rules/": { body: RULES },
    });

    renderApp("/settings");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("tab", { name: "الإنذارات" }));
    const input = await screen.findByTestId("threshold-UNEXCUSED_FULL_DAY_ABSENCE-LEVEL_1");
    await user.clear(input);
    await user.type(input, "9");

    expect(
      await screen.findByTestId("order-error-UNEXCUSED_FULL_DAY_ABSENCE"),
    ).toHaveTextContent("أكبر من الإنذار الأول");
    expect(screen.getByTestId("save-warning-rules")).toBeDisabled();
  });

  it("saves valid thresholds", async () => {
    const { calls } = mockApi({
      "/auth/me/": { body: roleMe(["SCHOOL_MANAGER"]) },
      "/warning-rules/": { body: RULES },
    });

    renderApp("/settings");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("tab", { name: "الإنذارات" }));
    const input = await screen.findByTestId("threshold-UNEXCUSED_FULL_DAY_ABSENCE-LEVEL_1");
    await user.clear(input);
    await user.type(input, "2");
    await user.click(screen.getByTestId("save-warning-rules"));

    await waitFor(() => {
      const patch = calls.find((c) => c.init?.method === "PATCH");
      expect(patch).toBeDefined();
      const body = parseBody(patch?.init) as { UNEXCUSED_FULL_DAY_ABSENCE: { levels: Record<string, number> } };
      expect(body.UNEXCUSED_FULL_DAY_ABSENCE.levels.LEVEL_1).toBe(2);
    });
  });

  it("vice principal sees rules read-only", async () => {
    mockApi({
      "/auth/me/": { body: roleMe(["VICE_PRINCIPAL"]) },
      "/warning-rules/": { body: RULES },
    });

    renderApp("/settings");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("tab", { name: "الإنذارات" }));
    expect(await screen.findByTestId("threshold-UNEXCUSED_FULL_DAY_ABSENCE-LEVEL_1")).toBeDisabled();
    expect(screen.queryByTestId("save-warning-rules")).not.toBeInTheDocument();
  });
});

describe("warnings dashboard (Phase 11)", () => {
  beforeEach(() => {
    queryClient.clear();
    document.cookie = "csrftoken=test-token";
  });

  it("shows KPI cards and a due row with issued levels", async () => {
    mockApi({
      "/auth/me/": { body: roleMe(["VICE_PRINCIPAL"]) },
      "/warnings/eligibility/": { body: ELIGIBILITY },
    });

    renderApp("/warnings");
    const kpis = await screen.findByTestId("warning-kpis");
    expect(within(kpis).getByTestId("kpi-UNEXCUSED_FULL_DAY_ABSENCE")).toHaveTextContent("4");
    expect(within(kpis).getByTestId("kpi-MORNING_LATE_OCCURRENCES")).toHaveTextContent("7");

    const row = screen.getByTestId("row-5-UNEXCUSED_FULL_DAY_ABSENCE");
    expect(row).toHaveTextContent("محمد أحمد");
    expect(row).toHaveTextContent("5 أيام");
    expect(row).toHaveTextContent("وصل: الإنذار الثاني");
    expect(row).toHaveTextContent("صدر: الإنذار الأول");
    // زر الإصدار للمستحق فقط — لا زر للمستوى الصادر ولا لغير المستحق
    expect(within(row).getByTestId("issue-5-UNEXCUSED_FULL_DAY_ABSENCE-LEVEL_2")).toBeInTheDocument();
    expect(within(row).queryByTestId("issue-5-UNEXCUSED_FULL_DAY_ABSENCE-LEVEL_1")).not.toBeInTheDocument();
    expect(within(row).queryByTestId("issue-5-UNEXCUSED_FULL_DAY_ABSENCE-LEVEL_3")).not.toBeInTheDocument();
    expect(within(row).getByTestId("print-warning-20")).toHaveAttribute(
      "href",
      "/api/v1/documents/40/download/?inline=1",
    );
  });

  it("issues a warning with only student/type/level in the payload", async () => {
    const { calls } = mockApi({
      "/auth/me/": { body: roleMe(["VICE_PRINCIPAL"]) },
      "/warnings/eligibility/": { body: ELIGIBILITY },
      "/warnings/issue/": { status: 201, body: WARNING_ROW },
      "/documents/generate/": { status: 201, body: WARNING_DOCUMENT },
    });

    renderApp("/warnings");
    const user = userEvent.setup();
    await user.click(await screen.findByTestId("issue-5-UNEXCUSED_FULL_DAY_ABSENCE-LEVEL_2"));

    expect(await screen.findByTestId("issue-result")).toHaveTextContent("الإنذار الثاني");
    expect(await screen.findByTestId("issued-warning-print")).toHaveAttribute(
      "href",
      "/api/v1/documents/41/download/?inline=1",
    );
    const post = calls.find((c) => c.url.includes("/warnings/issue/"));
    const body = parseBody(post?.init);
    expect(body).toEqual({
      student_id: 5,
      warning_type: "UNEXCUSED_FULL_DAY_ABSENCE",
      level: "LEVEL_2",
    });
    // القيم الموثوقة لا ترسل من العميل إطلاقًا
    expect(body).not.toHaveProperty("threshold_at_issue");
    expect(body).not.toHaveProperty("metric_value_at_issue");
    const documentPost = calls.find((c) => c.url.includes("/documents/generate/"));
    expect(parseBody(documentPost?.init)).toEqual({
      student_id: 5,
      document_type: "WARNING_LEVEL_2",
      warning_id: 21,
    });
  });

  it("filters by type and empty state message", async () => {
    const { calls } = mockApi({
      "/auth/me/": { body: roleMe(["SCHOOL_MANAGER"]) },
      "warning_type=MORNING_LATE_OCCURRENCES": {
        body: { ...ELIGIBILITY, results: [], count: 0 },
      },
      "/warnings/eligibility/": { body: ELIGIBILITY },
    });

    renderApp("/warnings");
    const user = userEvent.setup();
    await screen.findByTestId("eligibility-list");
    await user.selectOptions(screen.getByTestId("type-filter"), "MORNING_LATE_OCCURRENCES");

    expect(await screen.findByTestId("no-due-students")).toBeInTheDocument();
    expect(
      calls.some((c) => c.url.includes("warning_type=MORNING_LATE_OCCURRENCES")),
    ).toBe(true);
  });

  it("teacher has no warnings nav link", async () => {
    mockApi({
      "/auth/me/": { body: roleMe(["TEACHER"]) },
      "/attendance/current-period/": { body: { period: null, date: "2026-08-19" } },
      "/attendance/sections/": { body: [] },
    });

    renderApp("/");
    await screen.findByTestId("active-school-name");
    expect(screen.queryByRole("link", { name: "الإنذارات" })).not.toBeInTheDocument();
  });
});

describe("student warnings tab (Phase 11)", () => {
  beforeEach(() => {
    queryClient.clear();
    document.cookie = "csrftoken=test-token";
  });

  const PROFILE = {
    student: {
      id: 5, full_name: "محمد أحمد", status: "ACTIVE", status_label: "نشط",
      national_id_masked: "******5678", student_number: "1001",
      grade: { id: 1, name: "الثاني الثانوي" }, section: { id: 2, name: "1" },
    },
    period: { from: "2026-08-19", to: "2026-08-19" },
    attendance: {
      full_absence_days: 5, partial_absence_days: 0, undetermined_days: 0,
      absent_periods: 35, period_late_occurrences: 0, period_late_minutes: 0,
    },
    morning_attendance: {
      status: "AVAILABLE", morning_late_occurrences: 0, morning_late_minutes: 0,
    },
  };

  it("lists warnings and shows issue-time vs current metric drift", async () => {
    mockApi({
      "/auth/me/": { body: roleMe(["SCHOOL_MANAGER"]) },
      "/attendance-profile/": { body: PROFILE },
      "/warnings/21/": {
        body: {
          ...WARNING_ROW,
          academic_year: "2026/2027",
          current_metric_value: 3,
          metric_drifted: true,
          snapshot: { unexcused_full_absence_days: 5 },
        },
      },
      "/warnings/?student=5": { body: { count: 1, next: null, previous: null, results: [WARNING_ROW] } },
    });

    renderApp("/students/5/attendance");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "الإنذارات" }));

    expect(await screen.findByTestId("warnings-summary")).toHaveTextContent(
      "إنذارات الغياب: 1",
    );
    const row = screen.getByTestId("warning-21");
    expect(row).toHaveTextContent("الإنذار الثاني");
    expect(row).toHaveTextContent("صدر عند 5 أيام");

    await user.click(within(row).getByTestId("details-21"));
    const detail = await screen.findByTestId("detail-21");
    expect(detail).toHaveTextContent("عند الإصدار: 5");
    expect(detail).toHaveTextContent("حاليًا: 3");
    expect(screen.getByTestId("drift-21")).toHaveTextContent("الإنذار يبقى كما صدر");
  });

  it("manager can void with a reason; vice principal cannot", async () => {
    const detailBody = {
      ...WARNING_ROW,
      academic_year: "2026/2027",
      current_metric_value: 5,
      metric_drifted: false,
      snapshot: {},
    };
    const { calls } = mockApi({
      "/auth/me/": { body: roleMe(["SCHOOL_MANAGER"]) },
      "/attendance-profile/": { body: PROFILE },
      "/warnings/21/void/": { body: { ...WARNING_ROW, status: "VOIDED" } },
      "/warnings/21/": { body: detailBody },
      "/warnings/?student=5": { body: { count: 1, next: null, previous: null, results: [WARNING_ROW] } },
    });

    renderApp("/students/5/attendance");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "الإنذارات" }));
    await user.click(await screen.findByTestId("details-21"));
    await user.type(await screen.findByTestId("void-reason-21"), "صدر بالخطأ");
    await user.click(screen.getByTestId("void-21"));

    await waitFor(() => {
      const post = calls.find((c) => c.url.includes("/void/"));
      expect(parseBody(post?.init)).toEqual({ reason: "صدر بالخطأ" });
    });
  });

  it("hides void controls from the vice principal", async () => {
    mockApi({
      "/auth/me/": { body: roleMe(["VICE_PRINCIPAL"]) },
      "/attendance-profile/": { body: PROFILE },
      "/warnings/21/": {
        body: { ...WARNING_ROW, academic_year: "2026/2027", current_metric_value: 5, metric_drifted: false, snapshot: {} },
      },
      "/warnings/?student=5": { body: { count: 1, next: null, previous: null, results: [WARNING_ROW] } },
    });

    renderApp("/students/5/attendance");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "الإنذارات" }));
    await user.click(await screen.findByTestId("details-21"));
    expect(screen.queryByTestId("void-21")).not.toBeInTheDocument();
  });
});
