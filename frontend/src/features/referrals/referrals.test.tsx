import { screen, waitFor, within } from "@testing-library/react";
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

const TEACHER_OPTIONS = {
  source_type: "TEACHER",
  can_assign: false,
  categories: [
    {
      value: "ACADEMIC",
      label: "الأداء الدراسي",
      reasons: [
        { value: "ACADEMIC_WEAKNESS", label: "ضعف دراسي" },
        { value: "OTHER_ACADEMIC", label: "سبب دراسي آخر" },
      ],
    },
    {
      value: "CLASSROOM_BEHAVIOR",
      label: "سلوك صفي",
      reasons: [{ value: "SLEEPING_IN_CLASS", label: "النوم داخل الحصة" }],
    },
  ],
  observation_types: [{ value: "OTHER_OBSERVATION", label: "ملاحظة أخرى" }],
};

const VICE_OPTIONS = {
  source_type: "VICE_PRINCIPAL",
  can_assign: true,
  categories: [
    {
      value: "ATTENDANCE",
      label: "المواظبة",
      reasons: [{ value: "REPEATED_ABSENCE", label: "غياب متكرر" }],
    },
    ...TEACHER_OPTIONS.categories,
  ],
  observation_types: TEACHER_OPTIONS.observation_types,
};

const ROW = {
  id: 7,
  student: {
    id: 5,
    full_name: "محمد أحمد",
    grade_name: "الأول الثانوي",
    section_name: "2",
  },
  source_type: "TEACHER",
  source_type_label: "معلم",
  category: "CLASSROOM_BEHAVIOR",
  category_label: "سلوك صفي",
  reason_code: "SLEEPING_IN_CLASS",
  reason_label: "النوم داخل الحصة",
  status: "REFERRED",
  status_label: "محوّلة للمرشد",
  priority: "NORMAL",
  priority_label: "عادية",
  created_at: "2026-08-19T09:00:00Z",
  created_by_name: "أحمد المعلم",
  assigned_vice_principal_id: 24,
  assigned_vice_principal_name: "سلمان الوكيل",
  assigned_counselor_id: 42,
  assigned_counselor_name: "ليان المرشدة",
  counseling_case_id: null,
};

const DETAIL = {
  ...ROW,
  can_cancel: true,
  can_assign_vice_principal: false,
  can_start_vice_review: false,
  can_forward_to_counselor: false,
  can_acknowledge: false,
  can_close: false,
  description: "نام داخل الحصة ثلاث مرات هذا الأسبوع.",
  snapshot_at_referral: {
    student_name: "محمد أحمد",
    grade_name: "الأول الثانوي",
    section_name: "2",
  },
  current_metrics: null,
  source_warning: null,
  accepted_at: null,
  vice_reviewed_at: "2026-08-19T09:10:00Z",
  recommended_counselor_id: 42,
  recommended_counselor_name: "ليان المرشدة",
  closed_at: null,
  closed_by_name: null,
  closure_reason: "",
  contributions: [],
  events: [
    {
      id: 1,
      event_type: "CREATED",
      event_type_label: "أنشئت الإحالة",
      actor_name: "أحمد المعلم",
      created_at: "2026-08-19T09:00:00Z",
      metadata: {},
    },
  ],
};

const LIST = { count: 1, next: null, previous: null, results: [ROW] };
const KPIS = {
  pending_vice_count: 0,
  under_vice_review_count: 0,
  referred_count: 1,
  acknowledged_count: 0,
  unassigned_vice_count: 0,
};
const ZERO_KPIS = {
  pending_vice_count: 0,
  under_vice_review_count: 0,
  referred_count: 0,
  acknowledged_count: 0,
  unassigned_vice_count: 0,
};

const SECTIONS = [
  { id: 3, name: "1", grade_id: 9, grade_name: "الأول الثانوي", students_count: 2 },
  { id: 4, name: "2", grade_id: 9, grade_name: "الأول الثانوي", students_count: 1 },
];
const CANDIDATES = {
  count: 2,
  next: null,
  previous: null,
  results: [
    { id: 11, full_name: "طالب أول", grade: { id: 9, name: "الأول الثانوي" }, section: { id: 3, name: "1" } },
    { id: 12, full_name: "طالب ثانٍ", grade: { id: 9, name: "الأول الثانوي" }, section: { id: 4, name: "2" } },
  ],
};

describe("referrals (Phase 13)", () => {
  beforeEach(() => {
    queryClient.clear();
    document.cookie = "csrftoken=test-token";
  });

  // ---- نموذج المعلم ----

  it("shows a dedicated teacher page for creating and tracking referrals", async () => {
    mockApi({
      "/auth/me/": { body: roleMe(["TEACHER"]) },
      "/attendance/sections/": { body: SECTIONS },
      "/referrals/students/": { body: CANDIDATES },
      "/referrals/mine/": { body: { count: 0, next: null, previous: null, results: [] } },
      "/referrals/kpis/": { body: ZERO_KPIS },
    });
    renderApp("/referrals/mine");
    expect(
      await screen.findByRole("heading", { name: "إحالات الطلاب" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "إنشاء تحويل جديد" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "متابعة إحالاتي" })).toBeInTheDocument();
    expect(await screen.findByTestId("no-referrals")).toHaveTextContent(
      "لم تنشئ أي إحالة بعد",
    );
  });

  it("searches referral candidates automatically by name, grade, and section", async () => {
    const { calls } = mockApi({
      "/auth/me/": { body: roleMe(["TEACHER"]) },
      "/attendance/sections/": { body: SECTIONS },
      "/referrals/students/": { body: CANDIDATES },
      "/referrals/mine/": { body: { count: 0, next: null, previous: null, results: [] } },
      "/referrals/kpis/": { body: ZERO_KPIS },
    });
    renderApp("/referrals/mine");
    const user = userEvent.setup();

    await user.type(await screen.findByTestId("referral-student-search"), "طالب أول");
    await user.selectOptions(screen.getByTestId("referral-grade-filter"), "9");
    await user.selectOptions(screen.getByTestId("referral-section-filter"), "3");

    await waitFor(() => {
      expect(calls.some((call) =>
        call.url.includes("/referrals/students/") &&
        call.url.includes("search=") &&
        call.url.includes("grade=9") &&
        call.url.includes("section=3"),
      )).toBe(true);
    });
  });

  it("teacher refers a student from the dedicated referrals page", async () => {
    const { calls } = mockApi({
      "/auth/me/": { body: roleMe(["TEACHER"]) },
      "/attendance/sections/": { body: SECTIONS },
      "/referrals/students/": { body: CANDIDATES },
      "/referrals/options/": { body: TEACHER_OPTIONS },
      "/referrals/mine/": { body: { count: 0, next: null, previous: null, results: [] } },
      "/referrals/kpis/": { body: ZERO_KPIS },
      "/referrals/7/": { body: DETAIL },
      "/referrals/": { status: 201, body: DETAIL },
    });
    renderApp("/referrals/mine");
    const user = userEvent.setup();

    await user.click(await screen.findByTestId("referral-candidate-11"));
    const form = await screen.findByTestId("referral-create");
    expect(within(form).getByTestId("referral-student")).toHaveTextContent("طالب أول");

    // المعلم لا يرى فئة المواظبة إطلاقًا
    const categorySelect = screen.getByTestId("referral-category");
    expect(within(categorySelect).queryByText("المواظبة")).not.toBeInTheDocument();

    await user.selectOptions(categorySelect, "CLASSROOM_BEHAVIOR");
    await user.selectOptions(screen.getByTestId("referral-reason"), "SLEEPING_IN_CLASS");
    await user.type(
      screen.getByTestId("referral-description"),
      "نام داخل الحصة ثلاث مرات هذا الأسبوع.",
    );
    await user.click(screen.getByTestId("save-referral"));

    const post = calls.find(
      (call) => call.url.endsWith("/referrals/") && call.init?.method === "POST",
    );
    expect(JSON.parse(String(post!.init!.body))).toMatchObject({
      student_id: 11,
      category: "CLASSROOM_BEHAVIOR",
      reason_code: "SLEEPING_IN_CLASS",
      description: "نام داخل الحصة ثلاث مرات هذا الأسبوع.",
    });
    expect(await screen.findByTestId("referral-done")).toHaveTextContent(
      "تم إرسال الإحالة",
    );
  });

  it("requires a description when the reason is «other»", async () => {
    mockApi({
      "/auth/me/": { body: roleMe(["TEACHER"]) },
      "/attendance/sections/": { body: SECTIONS },
      "/referrals/students/": { body: CANDIDATES },
      "/referrals/options/": { body: TEACHER_OPTIONS },
      "/referrals/mine/": { body: { count: 0, next: null, previous: null, results: [] } },
      "/referrals/kpis/": { body: ZERO_KPIS },
    });
    renderApp("/referrals/mine");
    const user = userEvent.setup();

    await user.click(await screen.findByTestId("referral-candidate-11"));
    await user.selectOptions(await screen.findByTestId("referral-category"), "ACADEMIC");
    await user.selectOptions(screen.getByTestId("referral-reason"), "OTHER_ACADEMIC");
    expect(screen.getByTestId("save-referral")).toBeDisabled();

    await user.type(screen.getByTestId("referral-description"), "يحتاج متابعة.");
    expect(screen.getByTestId("save-referral")).toBeEnabled();
  });

  it("offers adding a note when a duplicate open case exists", async () => {
    const { calls } = mockApi({
      "/auth/me/": { body: roleMe(["TEACHER"]) },
      "/attendance/sections/": { body: SECTIONS },
      "/referrals/students/": { body: CANDIDATES },
      "/referrals/options/": { body: TEACHER_OPTIONS },
      "/referrals/mine/": { body: { count: 0, next: null, previous: null, results: [] } },
      "/referrals/kpis/": { body: ZERO_KPIS },
      "/referrals/7/": { body: DETAIL },
      "/referrals/contribute/": {
        status: 201,
        body: {
          referral_id: 7,
          contribution: {
            id: 3,
            observation_type: "ACADEMIC_OBSERVATION",
            observation_type_label: "ملاحظة دراسية",
            notes: "نفس الملاحظة في حصتي.",
            created_at: "2026-08-19T10:00:00Z",
            created_by_name: "أحمد المعلم",
          },
        },
      },
      "/referrals/": {
        status: 409,
        body: {
          code: "DUPLICATE_OPEN_REFERRAL",
          message: "يوجد للطالب ملف متابعة مفتوح في نفس الفئة.",
          details: { existing_referral_id: 7, recommended_action: "ADD_CONTRIBUTION" },
        },
      },
    });
    renderApp("/referrals/mine");
    const user = userEvent.setup();

    await user.click(await screen.findByTestId("referral-candidate-11"));
    await user.selectOptions(await screen.findByTestId("referral-category"), "ACADEMIC");
    await user.selectOptions(screen.getByTestId("referral-reason"), "ACADEMIC_WEAKNESS");
    await user.click(screen.getByTestId("save-referral"));

    const duplicate = await screen.findByTestId("referral-duplicate");
    expect(duplicate).toHaveTextContent("يوجد للطالب ملف متابعة مفتوح في نفس الفئة");

    await user.type(screen.getByTestId("duplicate-notes"), "نفس الملاحظة في حصتي.");
    await user.click(screen.getByTestId("add-contribution"));

    // الإرسال بالطالب والفئة لا بمعرف إحالة لا يراها المعلم بعد
    const contribution = calls.find((call) =>
      call.url.includes("/referrals/contribute/"),
    );
    expect(JSON.parse(String(contribution!.init!.body))).toEqual({
      student_id: 11,
      category: "ACADEMIC",
      observation_type: "ACADEMIC_OBSERVATION",
      notes: "نفس الملاحظة في حصتي.",
    });
    expect(await screen.findByTestId("referral-done")).toHaveTextContent(
      "أضيفت ملاحظتك",
    );
  });

  // ---- صندوق وارد المرشد ----

  it("shows the counselor inbox with KPIs and rows", async () => {
    mockApi({
      "/auth/me/": { body: roleMe(["COUNSELOR"]) },
      "/referrals/kpis/": { body: KPIS },
      "/referrals/options/": { body: TEACHER_OPTIONS },
      "/referrals/": { body: LIST },
    });
    renderApp("/referrals");

    expect(await screen.findByRole("heading", { name: "الإحالات" })).toBeInTheDocument();
    const kpis = await screen.findByTestId("referral-kpis");
    expect(within(kpis).getByText("محوّلة للمرشد").nextSibling).toHaveTextContent("1");
    const row = await screen.findByTestId("referral-row-7");
    expect(row).toHaveTextContent("محمد أحمد");
    expect(row).toHaveTextContent("النوم داخل الحصة");
    expect(row).toHaveTextContent("ليان المرشدة");
  });

  it("filters the inbox by status through the API", async () => {
    const { calls } = mockApi({
      "/auth/me/": { body: roleMe(["COUNSELOR"]) },
      "/referrals/kpis/": { body: KPIS },
      "/referrals/options/": { body: TEACHER_OPTIONS },
      "/referrals/": { body: LIST },
    });
    renderApp("/referrals");
    await screen.findByTestId("referral-row-7");
    const user = userEvent.setup();
    await user.selectOptions(screen.getByTestId("filter-status"), "OPEN");
    await screen.findByTestId("referral-row-7");
    expect(calls.some((call) => call.url.includes("status=OPEN"))).toBe(true);
  });

  it("lets the assigned counselor acknowledge from the detail card", async () => {
    const { calls } = mockApi({
      "/auth/me/": { body: roleMe(["COUNSELOR"]) },
      "/referrals/kpis/": { body: KPIS },
      "/referrals/options/": { body: TEACHER_OPTIONS },
      "/referrals/7/acknowledge/": {
        body: { ...DETAIL, status: "ACKNOWLEDGED", status_label: "تم الاستلام" },
      },
      "/referrals/7/": { body: { ...DETAIL, can_acknowledge: true } },
      "/referrals/": { body: LIST },
    });
    renderApp("/referrals");
    const user = userEvent.setup();
    await user.click(await screen.findByTestId("open-referral-7"));
    await user.click(await screen.findByTestId("acknowledge-referral"));

    expect(
      calls.some(
        (call) =>
          call.url.includes("/referrals/7/acknowledge/") && call.init?.method === "POST",
      ),
    ).toBe(true);
  });

  it("lets the counselor open the follow-up case from an acknowledged referral", async () => {
    const acknowledged = { ...DETAIL, status: "ACKNOWLEDGED", status_label: "تم الاستلام" };
    const { calls } = mockApi({
      "/auth/me/": { body: roleMe(["COUNSELOR"]) },
      "/referrals/kpis/": { body: KPIS },
      "/referrals/options/": { body: TEACHER_OPTIONS },
      "/referrals/7/": { body: acknowledged },
      "/referrals/7/open-case/": { status: 201, body: { id: 12 } },
      "/referrals/": { body: { ...LIST, results: [{ ...ROW, status: "ACKNOWLEDGED" }] } },
      "/counselor/cases/12/": { body: { id: 12 } },
    });
    renderApp("/referrals");
    const user = userEvent.setup();
    await user.click(await screen.findByTestId("open-referral-7"));
    await user.click(await screen.findByTestId("create-counseling-case"));
    expect(calls.some((call) => call.url.includes("/referrals/7/open-case/") && call.init?.method === "POST")).toBe(true);
  });

  it("assigns a counselor as vice principal", async () => {
    const { calls } = mockApi({
      "/auth/me/": { body: roleMe(["VICE_PRINCIPAL"]) },
      "/referrals/kpis/": { body: KPIS },
      "/referrals/options/": { body: VICE_OPTIONS },
      "/referrals/counselors/": {
        body: { counselors: [{ id: 42, name: "ليان المرشدة" }], has_counselors: true },
      },
      "/referrals/7/assign/": {
        body: { ...DETAIL, assigned_counselor_id: 42, assigned_counselor_name: "ليان المرشدة" },
      },
      "/referrals/7/": { body: { ...DETAIL, can_forward_to_counselor: true } },
      "/referrals/": { body: LIST },
    });
    renderApp("/referrals");
    const user = userEvent.setup();
    await user.click(await screen.findByTestId("open-referral-7"));
    await user.selectOptions(await screen.findByTestId("assign-counselor"), "42");
    await user.click(screen.getByTestId("save-assign"));

    const assignCall = calls.find((call) => call.url.includes("/referrals/7/assign/"));
    expect(JSON.parse(String(assignCall!.init!.body))).toEqual({
      counselor_membership_id: 42,
    });
  });

  it("lets the responsible vice principal start reviewing the referral", async () => {
    const pending = {
      ...DETAIL,
      status: "PENDING_VICE",
      status_label: "بانتظار الوكيل",
      assigned_counselor_id: null,
      assigned_counselor_name: null,
      vice_reviewed_at: null,
      can_cancel: false,
      can_start_vice_review: true,
      can_forward_to_counselor: true,
    };
    const { calls } = mockApi({
      "/auth/me/": { body: roleMe(["VICE_PRINCIPAL"]) },
      "/referrals/kpis/": { body: { ...ZERO_KPIS, pending_vice_count: 1 } },
      "/referrals/options/": { body: VICE_OPTIONS },
      "/referrals/counselors/": { body: { counselors: [], has_counselors: false } },
      "/referrals/7/start-vice-review/": {
        body: { ...pending, status: "UNDER_VICE_REVIEW", can_start_vice_review: false },
      },
      "/referrals/7/": { body: pending },
      "/referrals/": { body: { ...LIST, results: [pending] } },
    });
    renderApp("/referrals");
    const user = userEvent.setup();
    await user.click(await screen.findByTestId("open-referral-7"));
    await user.click(await screen.findByTestId("start-vice-review"));
    expect(calls.some((call) =>
      call.url.includes("/referrals/7/start-vice-review/") && call.init?.method === "POST"
    )).toBe(true);
  });

  it("lets the manager route an unmapped referral to a vice principal", async () => {
    const unassigned = {
      ...DETAIL,
      status: "PENDING_VICE",
      status_label: "بانتظار الوكيل",
      assigned_vice_principal_id: null,
      assigned_vice_principal_name: null,
      assigned_counselor_id: null,
      assigned_counselor_name: null,
      can_assign_vice_principal: true,
    };
    const { calls } = mockApi({
      "/auth/me/": { body: roleMe(["SCHOOL_MANAGER"]) },
      "/referrals/kpis/": { body: { ...ZERO_KPIS, pending_vice_count: 1, unassigned_vice_count: 1 } },
      "/referrals/options/": { body: VICE_OPTIONS },
      "/referrals/counselors/": { body: { counselors: [], has_counselors: false } },
      "/referrals/vice-principals/": {
        body: { vice_principals: [{ id: 24, name: "سلمان الوكيل" }] },
      },
      "/referrals/7/assign-vice/": {
        body: { ...unassigned, assigned_vice_principal_id: 24, assigned_vice_principal_name: "سلمان الوكيل" },
      },
      "/referrals/7/": { body: unassigned },
      "/referrals/": { body: { ...LIST, results: [unassigned] } },
    });
    renderApp("/referrals");
    const user = userEvent.setup();
    await user.click(await screen.findByTestId("open-referral-7"));
    await user.selectOptions(await screen.findByTestId("assign-vice-principal"), "24");
    await user.click(screen.getByTestId("save-assign-vice"));

    const routeCall = calls.find((call) => call.url.includes("/referrals/7/assign-vice/"));
    expect(JSON.parse(String(routeCall!.init!.body))).toEqual({
      vice_principal_membership_id: 24,
    });
  });

  it("closes a referral with a reason", async () => {
    const { calls } = mockApi({
      "/auth/me/": { body: roleMe(["SCHOOL_MANAGER"]) },
      "/referrals/kpis/": { body: KPIS },
      "/referrals/options/": { body: VICE_OPTIONS },
      "/referrals/counselors/": { body: { counselors: [], has_counselors: false } },
      "/referrals/7/close/": { body: { ...DETAIL, status: "CLOSED" } },
      "/referrals/7/": { body: { ...DETAIL, can_close: true } },
      "/referrals/": { body: LIST },
    });
    renderApp("/referrals");
    const user = userEvent.setup();
    await user.click(await screen.findByTestId("open-referral-7"));
    await user.type(await screen.findByTestId("closure-reason"), "تمت المتابعة.");
    await user.click(screen.getByTestId("close-referral"));

    const closeCall = calls.find((call) => call.url.includes("/referrals/7/close/"));
    expect(JSON.parse(String(closeCall!.init!.body))).toEqual({ reason: "تمت المتابعة." });
  });

  it("shows snapshot vs current metrics for attendance referrals", async () => {
    const attendanceDetail = {
      ...DETAIL,
      category: "ATTENDANCE",
      category_label: "المواظبة",
      reason_code: "REPEATED_ABSENCE",
      reason_label: "غياب متكرر",
      snapshot_at_referral: {
        student_name: "محمد أحمد",
        full_absence_days: 6,
        unexcused_full_absence_days: 5,
        absent_periods: 30,
      },
      current_metrics: {
        full_absence_days: 6,
        unexcused_full_absence_days: 3,
        absent_periods: 30,
      },
    };
    mockApi({
      "/auth/me/": { body: roleMe(["VICE_PRINCIPAL"]) },
      "/referrals/kpis/": { body: KPIS },
      "/referrals/options/": { body: VICE_OPTIONS },
      "/referrals/counselors/": { body: { counselors: [], has_counselors: false } },
      "/referrals/7/": { body: attendanceDetail },
      "/referrals/": { body: LIST },
    });
    renderApp("/referrals");
    const user = userEvent.setup();
    await user.click(await screen.findByTestId("open-referral-7"));

    const row = await screen.findByTestId("metric-unexcused_full_absence_days");
    expect(row).toHaveTextContent("5"); // وقت الإحالة
    expect(row).toHaveTextContent("3"); // حاليًا
  });

  it("يعيد المعلم من صندوق إحالات الإدارة إلى مساحة عمله", async () => {
    mockApi({ "/auth/me/": { body: roleMe(["TEACHER"]) } });
    renderApp("/referrals");
    await screen.findByTestId("active-school-name");
    expect(screen.queryByRole("link", { name: "الإحالات" })).not.toBeInTheDocument();
    expect(screen.queryByTestId("referrals-page")).not.toBeInTheDocument();
  });
});
