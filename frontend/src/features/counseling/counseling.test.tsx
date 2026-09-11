import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import { queryClient } from "@/app/queryClient";
import { buildMe, membership, mockApi } from "@/test/mockApi";
import { renderApp } from "@/test/renderApp";

type Role = "SCHOOL_MANAGER" | "VICE_PRINCIPAL" | "COUNSELOR" | "TEACHER";

function roleMe(roles: Role[]) {
  return buildMe({
    active_school: { id: 10, name: "ثانوية الأندلس", slug: "andalus" },
    roles,
    memberships: [membership(1, 10, "ثانوية الأندلس", roles)],
  });
}

const KPIS = {
  new_referrals: 2,
  open_cases: 3,
  under_assessment: 1,
  follow_up_active: 2,
  resolved: 0,
  waiting_teacher_response: 1,
  due_activities: 4,
  closed_this_month: 5,
};

const CASE_ROW = {
  id: 7,
  student_id: 5,
  student_name: "محمد أحمد",
  grade_name: "الأول الثانوي",
  section_name: "2",
  status: "FOLLOW_UP_ACTIVE",
  status_label: "متابعة جارية",
  priority: "NORMAL",
  priority_label: "عادية",
  referral_id: 3,
  referral_category: "ATTENDANCE",
  referral_category_label: "المواظبة",
  referral_reason_label: "غياب متكرر",
  counselor_name: "ليان المرشدة",
  counselor_membership_id: 4,
  opened_at: "2026-08-10T08:00:00Z",
  last_activity_at: "2026-08-19T09:00:00Z",
  next_activity_due: "2026-08-25",
};

const CASE_DETAIL = {
  ...CASE_ROW,
  summary: "",
  opened_by_name: "ليان المرشدة",
  closed_by_name: null,
  closed_at: null,
  closure_reason: "",
  outcome_summary: "",
  improvement_status: "",
  snapshot_at_opening: {
    unexcused_full_absence_days: 5,
    morning_late_occurrences: 6,
    warnings_count: 2,
  },
  current_metrics: {
    unexcused_full_absence_days: 3,
    morning_late_occurrences: 2,
    warnings_count: 2,
  },
  referral: {
    id: 3,
    category_label: "المواظبة",
    reason_label: "غياب متكرر",
    description: "غياب متكرر يحتاج متابعة.",
    created_at: "2026-08-09T08:00:00Z",
    snapshot_at_referral: { unexcused_full_absence_days: 5 },
  },
  can_manage: true,
};

const PLAN = {
  id: 11,
  title: "خطة الحضور",
  status: "ACTIVE",
  status_label: "نشطة",
  start_date: "2026-08-10",
  target_end_date: null,
  notes: "",
  created_by_name: "ليان المرشدة",
  activated_at: "2026-08-10T08:00:00Z",
  completed_at: null,
  goals: [
    {
      id: 21,
      goal_type: "MORNING_LATENESS",
      goal_type_label: "التأخر الصباحي",
      title: "خفض التأخر الصباحي",
      description: "",
      baseline_value: 6,
      target_value: 1,
      unit: "مرات",
      status: "OPEN",
      status_label: "قائم",
      completed_at: null,
    },
  ],
  activities: [
    {
      id: 31,
      activity_type: "STUDENT_CHECK_IN",
      activity_type_label: "متابعة مع الطالب",
      title: "متابعة أسبوعية",
      description: "",
      due_date: "2026-08-25",
      status: "PENDING",
      status_label: "قيد التنفيذ",
      completed_at: null,
    },
  ],
};

const TEACHER_REQUEST = {
  id: 41,
  request_type: "CLASSROOM_BEHAVIOR",
  request_type_label: "سلوك صفي",
  question: "كيف كان تفاعله خلال الأسبوع؟",
  due_date: "2026-08-25",
  status: "PENDING",
  status_label: "بانتظار الرد",
  teacher_name: "أحمد المعلم",
  requested_by_name: "ليان المرشدة",
  created_at: "2026-08-19T08:00:00Z",
  responded_at: null,
  student_name: "محمد أحمد",
  student_id: 5,
};

function parseBody(init?: RequestInit): Record<string, unknown> {
  return JSON.parse(String(init?.body ?? "{}")) as Record<string, unknown>;
}

describe("counselor dashboard (Phase 14)", () => {
  beforeEach(() => {
    queryClient.clear();
    document.cookie = "csrftoken=test-token";
  });

  it("uses the counselor dashboard as the counselor's real home page", async () => {
    mockApi({
      "/auth/me/": { body: roleMe(["COUNSELOR"]) },
      "/counselor/dashboard/": { body: KPIS },
      "/counselor/cases/": {
        body: { count: 0, next: null, previous: null, results: [] },
      },
    });

    renderApp("/");
    expect(await screen.findByRole("heading", { name: "لوحة الإرشاد الطلابي" })).toBeInTheDocument();
    expect(screen.queryByText(/تأتي في المراحل القادمة/)).toBeNull();
  });

  it("shows KPIs and the case list", async () => {
    mockApi({
      "/auth/me/": { body: roleMe(["COUNSELOR"]) },
      "/counselor/dashboard/": { body: KPIS },
      "/counselor/cases/": {
        body: { count: 1, next: null, previous: null, results: [CASE_ROW] },
      },
    });

    renderApp("/counselor");
    expect(await screen.findByTestId("kpi-open_cases")).toHaveTextContent("3");
    expect(screen.getByTestId("kpi-waiting_teacher_response")).toHaveTextContent("1");
    expect(screen.getByTestId("kpi-new_referrals")).toHaveTextContent("2");
    const row = await screen.findByTestId("case-row-7");
    expect(row).toHaveTextContent("محمد أحمد");
    expect(row).toHaveTextContent("متابعة جارية");
    expect(row).toHaveTextContent("غياب متكرر");
  });

  it("applies status and category filters through the API", async () => {
    const { calls } = mockApi({
      "/auth/me/": { body: roleMe(["COUNSELOR"]) },
      "/counselor/dashboard/": { body: KPIS },
      "/counselor/cases/": {
        body: { count: 0, next: null, previous: null, results: [] },
      },
    });

    renderApp("/counselor");
    const user = userEvent.setup();
    await user.selectOptions(await screen.findByTestId("case-status-filter"), "RESOLVED");
    await user.selectOptions(screen.getByTestId("case-category-filter"), "ACADEMIC");
    await user.selectOptions(screen.getByTestId("case-sort"), "oldest_unattended");

    await waitFor(() => {
      const url = calls.map((call) => call.url).reverse().find((u) => u.includes("/counselor/cases/"));
      expect(url).toContain("status=RESOLVED");
      expect(url).toContain("category=ACADEMIC");
      expect(url).toContain("sort=oldest_unattended");
    });
    expect(await screen.findByTestId("no-cases")).toBeInTheDocument();
  });

  it("hides the counselor dashboard link from the teacher", async () => {
    mockApi({ "/auth/me/": { body: roleMe(["TEACHER"]) } });
    renderApp("/");
    expect(await screen.findByRole("link", { name: "طلبات المتابعة" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "الإرشاد" })).not.toBeInTheDocument();
  });

  it("shows the counseling link to the counselor", async () => {
    mockApi({ "/auth/me/": { body: roleMe(["COUNSELOR"]) } });
    renderApp("/");
    expect(await screen.findByRole("link", { name: "الإرشاد" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "طلبات المتابعة" })).not.toBeInTheDocument();
  });
});

describe("case detail (Phase 14)", () => {
  beforeEach(() => {
    queryClient.clear();
    document.cookie = "csrftoken=test-token";
  });

  it("shows opening snapshot next to current metrics", async () => {
    mockApi({
      "/auth/me/": { body: roleMe(["COUNSELOR"]) },
      "/counselor/cases/7/": { body: CASE_DETAIL },
    });

    renderApp("/counselor/cases/7");
    const row = await screen.findByTestId("metric-unexcused_full_absence_days");
    expect(within(row).getByText("5")).toBeInTheDocument();
    expect(within(row).getByText("3")).toBeInTheDocument();
    expect(screen.getByTestId("case-status")).toHaveTextContent("متابعة جارية");
  });

  it("records a session with an intent-only payload", async () => {
    const { calls } = mockApi({
      "/auth/me/": { body: roleMe(["COUNSELOR"]) },
      "/counselor/cases/7/sessions/": (init) =>
        init?.method === "POST" ? { status: 201, body: {} } : { body: [] },
      "/counselor/cases/7/": { body: CASE_DETAIL },
    });

    renderApp("/counselor/cases/7");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("tab", { name: "الجلسات" }));
    await user.selectOptions(await screen.findByTestId("session-type"), "STUDENT_MEETING");
    await user.type(screen.getByTestId("session-summary"), "مقابلة أولى");
    await user.click(screen.getByTestId("save-session"));

    await waitFor(() => {
      const post = calls.find(
        (call) => call.init?.method === "POST" && call.url.includes("/sessions/"),
      );
      expect(post).toBeDefined();
      const body = parseBody(post?.init);
      expect(body).toEqual({ session_type: "STUDENT_MEETING", summary: "مقابلة أولى" });
      expect(body).not.toHaveProperty("created_by_membership");
      expect(body).not.toHaveProperty("school");
    });
  });

  it("shows the professional observation and outcome in the session record", async () => {
    mockApi({
      "/auth/me/": { body: roleMe(["COUNSELOR"]) },
      "/counselor/cases/7/sessions/": {
        body: [
          {
            id: 17,
            session_type: "STUDENT_MEETING",
            session_type_label: "مقابلة الطالب",
            occurred_at: "2026-08-19T08:00:00Z",
            summary: "ناقشنا أسباب الغياب.",
            observations: "تفاعل الطالب بوضوح مع الأسئلة.",
            outcome: "متابعة الالتزام لأسبوع جديد.",
            status: "RECORDED",
            status_label: "مسجلة",
            created_by_name: "ليان المرشدة",
            void_reason: "",
          },
        ],
      },
      "/counselor/cases/7/": { body: CASE_DETAIL },
    });

    renderApp("/counselor/cases/7");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("tab", { name: "الجلسات" }));

    const row = await screen.findByTestId("session-17");
    expect(row).toHaveTextContent("تفاعل الطالب بوضوح مع الأسئلة");
    expect(row).toHaveTextContent("متابعة الالتزام لأسبوع جديد");
  });

  it("shows the plan with quantitative goal and completes an activity", async () => {
    const { calls } = mockApi({
      "/auth/me/": { body: roleMe(["COUNSELOR"]) },
      "/counselor/cases/7/plans/": { body: [PLAN] },
      "/counselor/activities/31/complete/": { body: { ...PLAN.activities[0], status: "COMPLETED" } },
      "/counselor/cases/7/": { body: CASE_DETAIL },
    });

    renderApp("/counselor/cases/7");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("tab", { name: "خطة المتابعة" }));
    const goal = await screen.findByTestId("goal-21");
    expect(goal).toHaveTextContent("خفض التأخر الصباحي");
    expect(goal).toHaveTextContent("من 6 إلى 1");

    await user.click(screen.getByTestId("complete-activity-31"));
    await waitFor(() => {
      expect(
        calls.some((call) => call.url.includes("/counselor/activities/31/complete/")),
      ).toBe(true);
    });
  });

  it("adds a planned action with its due date", async () => {
    const { calls } = mockApi({
      "/auth/me/": { body: roleMe(["COUNSELOR"]) },
      "/counselor/cases/7/plans/": { body: [PLAN] },
      "/counselor/plans/11/activities/": { status: 201, body: PLAN.activities[0] },
      "/counselor/cases/7/": { body: CASE_DETAIL },
    });

    renderApp("/counselor/cases/7");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("tab", { name: "خطة المتابعة" }));
    await user.type(await screen.findByTestId("activity-title"), "اتصال متابعة");
    await user.type(screen.getByTestId("activity-due-date"), "2026-09-01");
    await user.click(screen.getByTestId("add-activity"));

    await waitFor(() => {
      const post = calls.find(
        (call) => call.init?.method === "POST" && call.url.includes("/plans/11/activities/"),
      );
      expect(parseBody(post?.init)).toEqual({
        activity_type: "STUDENT_CHECK_IN",
        title: "اتصال متابعة",
        due_date: "2026-09-01",
      });
    });
  });

  it("keeps goals and activities read-only after the plan is completed", async () => {
    mockApi({
      "/auth/me/": { body: roleMe(["COUNSELOR"]) },
      "/counselor/cases/7/plans/": {
        body: [{ ...PLAN, status: "COMPLETED", status_label: "مكتملة" }],
      },
      "/counselor/cases/7/": { body: CASE_DETAIL },
    });

    renderApp("/counselor/cases/7");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("tab", { name: "خطة المتابعة" }));
    expect(await screen.findByTestId("plan-status-11")).toHaveTextContent("مكتملة");
    expect(screen.queryByTestId("complete-goal-21")).toBeNull();
    expect(screen.queryByTestId("complete-activity-31")).toBeNull();
  });

  it("creates a teacher follow-up request", async () => {
    const { calls } = mockApi({
      "/auth/me/": { body: roleMe(["COUNSELOR"]) },
      "/counselor/teachers/": { body: [{ membership_id: 9, name: "أحمد المعلم" }] },
      "/counselor/cases/7/teacher-requests/": (init) =>
        init?.method === "POST" ? { status: 201, body: TEACHER_REQUEST } : { body: [] },
      "/counselor/cases/7/": { body: CASE_DETAIL },
    });

    renderApp("/counselor/cases/7");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("tab", { name: "طلبات المعلمين" }));
    await user.selectOptions(await screen.findByTestId("request-teacher"), "9");
    await user.selectOptions(screen.getByTestId("request-type"), "CLASSROOM_BEHAVIOR");
    await user.type(screen.getByTestId("request-question"), "كيف كان تفاعله؟");
    await user.type(screen.getByTestId("request-due-date"), "2026-09-01");
    await user.click(screen.getByTestId("send-request"));

    await waitFor(() => {
      const post = calls.find(
        (call) => call.init?.method === "POST" && call.url.includes("teacher-requests"),
      );
      expect(parseBody(post?.init)).toEqual({
        teacher_membership_id: 9,
        request_type: "CLASSROOM_BEHAVIOR",
        question: "كيف كان تفاعله؟",
        due_date: "2026-09-01",
      });
    });
  });

  it("filters a long teacher list before creating a follow-up request", async () => {
    const teacherRows = Array.from({ length: 9 }, (_, index) => ({
      membership_id: index + 1,
      name: index === 8 ? "أحمد المعلم" : `معلم تجريبي ${index + 1}`,
    }));
    mockApi({
      "/auth/me/": { body: roleMe(["COUNSELOR"]) },
      "/counselor/teachers/": { body: teacherRows },
      "/counselor/cases/7/teacher-requests/": { body: [] },
      "/counselor/cases/7/": { body: CASE_DETAIL },
    });

    renderApp("/counselor/cases/7");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("tab", { name: "طلبات المعلمين" }));
    await user.type(await screen.findByTestId("teacher-search"), "أحمد");

    const picker = screen.getByTestId("request-teacher");
    expect(within(picker).getByRole("option", { name: "أحمد المعلم" })).toBeInTheDocument();
    expect(within(picker).queryByRole("option", { name: "معلم تجريبي 1" })).toBeNull();
  });

  it("closes the case with a reason and offers reopen afterwards", async () => {
    const closed = { ...CASE_DETAIL, status: "CLOSED", status_label: "مغلقة", closed_at: "2026-08-20T08:00:00Z", closure_reason: "IMPROVED" };
    const { calls } = mockApi({
      "/auth/me/": { body: roleMe(["COUNSELOR"]) },
      "/counselor/cases/7/close/": { body: closed },
      "/counselor/cases/7/": { body: CASE_DETAIL },
    });

    renderApp("/counselor/cases/7");
    const user = userEvent.setup();
    await user.selectOptions(await screen.findByTestId("closure-reason"), "GOALS_MET");
    await user.selectOptions(screen.getByTestId("closure-improvement"), "IMPROVED");
    await user.click(screen.getByTestId("close-case"));

    await waitFor(() => {
      const post = calls.find((call) => call.url.includes("/close/"));
      expect(parseBody(post?.init)).toEqual({
        closure_reason: "GOALS_MET",
        improvement_status: "IMPROVED",
      });
    });
  });

  it("shows a read-only case to the vice principal", async () => {
    mockApi({
      "/auth/me/": { body: roleMe(["VICE_PRINCIPAL"]) },
      "/counselor/cases/7/": { body: { ...CASE_DETAIL, can_manage: false } },
    });

    renderApp("/counselor/cases/7");
    await screen.findByTestId("case-detail");
    expect(screen.queryByTestId("case-actions")).not.toBeInTheDocument();
    expect(screen.queryByTestId("close-case")).not.toBeInTheDocument();
    expect(screen.getByText("سجل الجلسات")).toBeInTheDocument();
    expect(screen.getByText("راجع اللقاءات والاتصالات الموثقة دون تعديل.")).toBeInTheDocument();
    expect(screen.getByText("خطة المتابعة", { selector: "span" })).toBeInTheDocument();
    expect(screen.getByText("طلبات المعلمين", { selector: "span" })).toBeInTheDocument();
    expect(screen.queryByText("وثّق جلسة")).not.toBeInTheDocument();
    expect(screen.queryByText("اطلب متابعة")).not.toBeInTheDocument();
  });
});

describe("teacher follow-up inbox (Phase 14)", () => {
  beforeEach(() => {
    queryClient.clear();
    document.cookie = "csrftoken=test-token";
  });

  it("lists only the question and student, without case content", async () => {
    mockApi({
      "/auth/me/": { body: roleMe(["TEACHER"]) },
      "/teacher/follow-up-requests/": { body: [TEACHER_REQUEST] },
    });

    renderApp("/teacher/follow-ups");
    const row = await screen.findByTestId("follow-up-41");
    expect(row).toHaveTextContent("محمد أحمد");
    expect(row).toHaveTextContent("كيف كان تفاعله خلال الأسبوع؟");
    expect(row).toHaveTextContent("ليان المرشدة");
    expect(screen.queryByTestId("case-detail")).not.toBeInTheDocument();
    expect(screen.queryByText(/الجلسات/)).not.toBeInTheDocument();
  });

  it("submits a response with the improvement status", async () => {
    const { calls } = mockApi({
      "/auth/me/": { body: roleMe(["TEACHER"]) },
      "/teacher/follow-up-requests/41/respond/": { status: 201, body: TEACHER_REQUEST },
      "/teacher/follow-up-requests/": { body: [TEACHER_REQUEST] },
    });

    renderApp("/teacher/follow-ups");
    const user = userEvent.setup();
    await user.click(await screen.findByTestId("respond-41"));
    await user.type(screen.getByTestId("response-observation"), "تحسن ملحوظ");
    await user.selectOptions(screen.getByTestId("response-improvement"), "IMPROVED");
    await user.click(screen.getByTestId("submit-response"));

    await waitFor(() => {
      const post = calls.find((call) => call.url.includes("/respond/"));
      expect(parseBody(post?.init)).toEqual({
        observation: "تحسن ملحوظ",
        improvement_status: "IMPROVED",
      });
    });
  });

  it("lets the teacher cancel an unfinished response without sending it", async () => {
    const { calls } = mockApi({
      "/auth/me/": { body: roleMe(["TEACHER"]) },
      "/teacher/follow-up-requests/": { body: [TEACHER_REQUEST] },
    });

    renderApp("/teacher/follow-ups");
    const user = userEvent.setup();
    await user.click(await screen.findByTestId("respond-41"));
    await user.type(screen.getByTestId("response-observation"), "ملاحظة لم تكتمل");
    await user.click(screen.getByTestId("cancel-response"));

    expect(screen.queryByTestId("response-observation")).toBeNull();
    expect(screen.getByTestId("respond-41")).toBeInTheDocument();
    expect(calls.some((call) => call.url.includes("/respond/"))).toBe(false);
  });

  it("shows an answered request as read-only", async () => {
    mockApi({
      "/auth/me/": { body: roleMe(["TEACHER"]) },
      "/teacher/follow-up-requests/": {
        body: [
          {
            ...TEACHER_REQUEST,
            status: "ANSWERED",
            status_label: "تم الرد",
            response: {
              observation: "تحسن واضح",
              improvement_status: "IMPROVED",
              improvement_status_label: "تحسن",
              notes: "",
              responded_by_name: "أحمد المعلم",
              created_at: "2026-08-19T10:00:00Z",
            },
          },
        ],
      },
    });

    renderApp("/teacher/follow-ups");
    expect(await screen.findByTestId("my-response-41")).toHaveTextContent("تحسن واضح");
    expect(screen.queryByTestId("respond-41")).not.toBeInTheDocument();
  });
});

describe("student profile counseling tab (Phase 14)", () => {
  beforeEach(() => {
    queryClient.clear();
    document.cookie = "csrftoken=test-token";
  });

  const PROFILE = {
    student: {
      id: 5,
      full_name: "محمد أحمد",
      status: "ACTIVE",
      status_label: "نشط",
      national_id_masked: "******5678",
      student_number: "1001",
      grade: { id: 1, name: "الأول الثانوي" },
      section: { id: 2, name: "2" },
    },
    period: { from: "2026-08-19", to: "2026-08-19" },
    attendance: {
      full_absence_days: 5,
      partial_absence_days: 0,
      undetermined_days: 0,
      absent_periods: 35,
      excused_absent_periods: 0,
      unexcused_absent_periods: 35,
      excused_full_absence_days: 0,
      unexcused_full_absence_days: 5,
      mixed_full_absence_days: 0,
    },
    morning_attendance: {
      status: "AVAILABLE",
      morning_late_occurrences: 0,
      morning_late_minutes: 0,
    },
  };

  it("summarises the student's cases without counselor notes", async () => {
    mockApi({
      "/auth/me/": { body: roleMe(["COUNSELOR"]) },
      "/attendance-profile/": { body: PROFILE },
      "/students/5/counseling/": {
        body: {
          open_cases: 1,
          total_cases: 1,
          cases: [
            {
              id: 7,
              status: "FOLLOW_UP_ACTIVE",
              status_label: "متابعة جارية",
              opened_at: "2026-08-10",
              closed_at: null,
              counselor_name: "ليان المرشدة",
              last_activity_at: "2026-08-19",
              improvement_status: null,
            },
          ],
        },
      },
    });

    renderApp("/students/5/attendance");
    const user = userEvent.setup();
    await screen.findByRole("heading", { name: "محمد أحمد" });
    await user.click(screen.getByRole("button", { name: "الإرشاد والمتابعة" }));

    expect(await screen.findByTestId("counseling-summary")).toHaveTextContent(
      "ملفات متابعة مفتوحة: 1",
    );
    const row = await screen.findByTestId("counseling-case-7");
    expect(row).toHaveTextContent("متابعة جارية");
    expect(row).toHaveTextContent("ليان المرشدة");
    expect(row).not.toHaveTextContent("مقابلة");
  });
});
