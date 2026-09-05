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
  status: "NEW",
  status_label: "جديدة",
  priority: "NORMAL",
  priority_label: "عادية",
  created_at: "2026-08-19T09:00:00Z",
  created_by_name: "أحمد المعلم",
  assigned_counselor_id: null,
  assigned_counselor_name: null,
  counseling_case_id: null,
};

const DETAIL = {
  ...ROW,
  can_cancel: true,
  description: "نام داخل الحصة ثلاث مرات هذا الأسبوع.",
  snapshot_at_referral: {
    student_name: "محمد أحمد",
    grade_name: "الأول الثانوي",
    section_name: "2",
  },
  current_metrics: null,
  source_warning: null,
  accepted_at: null,
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
const KPIS = { new_count: 1, acknowledged_count: 0, unassigned_count: 1 };

/** جلسة تحضير مفتوحة — نقطة دخول المعلم للإحالة من قائمة الفصل. */
const SESSION = {
  id: 5,
  status: "IN_PROGRESS",
  attendance_date: "2026-08-19",
  section: { id: 3, name: "1", grade_name: "الأول الثانوي", students_count: 2 },
  period: { sequence: 2, name: "الثانية", start_time: "08:05", end_time: "08:50" },
  submitted_by: null,
  submitted_at: null,
  can_edit: true,
  roster: [
    { student_id: 11, full_name: "طالب أول", national_id_masked: "******0011" },
    { student_id: 12, full_name: "طالب ثانٍ", national_id_masked: "******0012" },
  ],
  marks: [],
};

describe("referrals (Phase 13)", () => {
  beforeEach(() => {
    queryClient.clear();
    document.cookie = "csrftoken=test-token";
  });

  // ---- نموذج المعلم ----

  it("offers a teacher only academic/classroom reasons from the class roster", async () => {
    mockApi({
      "/auth/me/": { body: roleMe(["TEACHER"]) },
      "/referrals/options/": { body: TEACHER_OPTIONS },
      "/attendance/sections/": {
        body: { sections: [{ id: 3, name: "1", grade_name: "الأول الثانوي" }] },
      },
      "/referrals/mine/": { body: { count: 0, next: null, previous: null, results: [] } },
    });
    renderApp("/referrals/mine");
    expect(await screen.findByRole("heading", { name: "إحالاتي" })).toBeInTheDocument();
    expect(await screen.findByTestId("no-referrals")).toHaveTextContent(
      "لم تنشئ أي إحالة بعد",
    );
  });

  it("teacher refers a student from the class roster", async () => {
    const { calls } = mockApi({
      "/auth/me/": { body: roleMe(["TEACHER"]) },
      "/attendance/sessions/start/": { body: SESSION },
      "/referrals/options/": { body: TEACHER_OPTIONS },
      "/referrals/": { status: 201, body: DETAIL },
    });
    renderApp("/attendance/section/3");
    const user = userEvent.setup();

    await user.click(await screen.findByTestId("refer-student-11"));
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
      "/attendance/sessions/start/": { body: SESSION },
      "/referrals/options/": { body: TEACHER_OPTIONS },
    });
    renderApp("/attendance/section/3");
    const user = userEvent.setup();

    await user.click(await screen.findByTestId("refer-student-11"));
    await user.selectOptions(await screen.findByTestId("referral-category"), "ACADEMIC");
    await user.selectOptions(screen.getByTestId("referral-reason"), "OTHER_ACADEMIC");
    expect(screen.getByTestId("save-referral")).toBeDisabled();

    await user.type(screen.getByTestId("referral-description"), "يحتاج متابعة.");
    expect(screen.getByTestId("save-referral")).toBeEnabled();
  });

  it("offers adding a note when a duplicate open case exists", async () => {
    const { calls } = mockApi({
      "/auth/me/": { body: roleMe(["TEACHER"]) },
      "/attendance/sessions/start/": { body: SESSION },
      "/referrals/options/": { body: TEACHER_OPTIONS },
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
    renderApp("/attendance/section/3");
    const user = userEvent.setup();

    await user.click(await screen.findByTestId("refer-student-11"));
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
    expect(within(kpis).getByText("جديدة").nextSibling).toHaveTextContent("1");
    expect(within(kpis).getByText("غير معينة").nextSibling).toHaveTextContent("1");
    const row = await screen.findByTestId("referral-row-7");
    expect(row).toHaveTextContent("محمد أحمد");
    expect(row).toHaveTextContent("النوم داخل الحصة");
    expect(row).toHaveTextContent("غير معيّن");
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
      "/referrals/7/": { body: DETAIL },
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
      "/referrals/7/": { body: DETAIL },
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

  it("closes a referral with a reason", async () => {
    const { calls } = mockApi({
      "/auth/me/": { body: roleMe(["SCHOOL_MANAGER"]) },
      "/referrals/kpis/": { body: KPIS },
      "/referrals/options/": { body: VICE_OPTIONS },
      "/referrals/counselors/": { body: { counselors: [], has_counselors: false } },
      "/referrals/7/close/": { body: { ...DETAIL, status: "CLOSED" } },
      "/referrals/7/": { body: DETAIL },
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

  it("denies a teacher the counselor inbox with an Arabic message", async () => {
    mockApi({
      "/auth/me/": { body: roleMe(["TEACHER"]) },
      "/referrals/kpis/": {
        status: 403,
        body: { code: "PERMISSION_DENIED", message: "ليست لديك صلاحية.", details: {} },
      },
      "/referrals/": {
        status: 403,
        body: { code: "PERMISSION_DENIED", message: "ليست لديك صلاحية.", details: {} },
      },
    });
    renderApp("/referrals");
    expect(
      await screen.findByRole("heading", { name: "لا تملك صلاحية عرض الإحالات" }),
    ).toBeInTheDocument();
  });
});
