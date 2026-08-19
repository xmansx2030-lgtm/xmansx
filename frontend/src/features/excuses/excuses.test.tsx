import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import { queryClient } from "@/app/queryClient";
import { buildMe, membership, mockApi } from "@/test/mockApi";
import { renderApp } from "@/test/renderApp";

function meWithRoles(roles: string[]) {
  return buildMe({
    active_school: { id: 10, name: "ثانوية الأندلس", slug: "andalus" },
    roles: roles as never,
    memberships: [membership(1, 10, "ثانوية الأندلس", roles as never)],
  });
}

const KPIS = {
  pending_count: 2,
  approved_today_count: 1,
  rejected_count: 0,
  cancelled_count: 0,
};

const ROW = {
  id: 7,
  student: {
    id: 5,
    full_name: "محمد أحمد",
    grade_name: "الأول الثانوي",
    section_name: "2",
  },
  status: "PENDING",
  status_label: "بانتظار الاعتماد",
  reason_type: "MEDICAL_REPORT",
  reason_type_label: "تقرير طبي",
  date_from: "2026-08-17",
  date_to: "2026-08-19",
  targets_count: 3,
  active_coverage_count: 0,
  attachments_count: 0,
  recorded_at: "2026-08-19T09:00:00Z",
  recorded_by_name: "وكيل المدرسة",
  approved_by_name: null,
};

const LIST = { count: 1, next: null, previous: null, results: [ROW] };

const DETAIL = {
  ...ROW,
  notes: "تقرير من المستشفى",
  targets: [
    { id: 1, attendance_date: "2026-08-17", period_sequence: null },
    { id: 2, attendance_date: "2026-08-18", period_sequence: null },
  ],
  coverages: [],
  attachments: [],
  approved_at: null,
  rejected_at: null,
  rejected_by_name: null,
  rejection_reason: "",
  cancelled_at: null,
  cancelled_by_name: null,
  cancellation_reason: "",
};

const PREVIEW = {
  excuse_id: 7,
  days: [
    {
      attendance_date: "2026-08-17",
      scope: "FULL_DAY",
      expected_periods: 7,
      scope_periods: 7,
      submitted_periods: 7,
      missing_periods: 0,
      absent_periods: 7,
      present_periods: 0,
      late_periods: 0,
      complete: true,
    },
    {
      attendance_date: "2026-08-18",
      scope: "FULL_DAY",
      expected_periods: 7,
      scope_periods: 7,
      submitted_periods: 4,
      missing_periods: 3,
      absent_periods: 4,
      present_periods: 0,
      late_periods: 0,
      complete: false,
    },
  ],
  covered_absent_periods: 11,
  already_excused_periods: 0,
  already_excused_dates: [],
  preview_hash: "hash-abc",
};

describe("excuses page (Phase 10)", () => {
  beforeEach(() => {
    queryClient.clear();
    document.cookie = "csrftoken=test-token";
  });

  it("shows KPIs and the excuses list for a vice principal", async () => {
    mockApi({
      "/auth/me/": { body: meWithRoles(["VICE_PRINCIPAL"]) },
      "/excuses/kpis/": { body: KPIS },
      "/excuses/": { body: LIST },
    });
    renderApp("/excuses");

    expect(await screen.findByRole("heading", { name: "الأعذار" })).toBeInTheDocument();
    const kpis = await screen.findByTestId("excuse-kpis");
    expect(within(kpis).getByText("بانتظار الاعتماد").nextSibling).toHaveTextContent("2");
    expect(await screen.findByTestId("excuse-row-7")).toHaveTextContent("محمد أحمد");
    expect(screen.getByTestId("excuse-row-7")).toHaveTextContent("تقرير طبي");
  });

  it("applies status and reason filters through the API", async () => {
    const { calls } = mockApi({
      "/auth/me/": { body: meWithRoles(["VICE_PRINCIPAL"]) },
      "/excuses/kpis/": { body: KPIS },
      "/excuses/": { body: LIST },
    });
    renderApp("/excuses");
    await screen.findByTestId("excuse-row-7");
    const user = userEvent.setup();

    await user.selectOptions(screen.getByTestId("filter-status"), "APPROVED");
    await screen.findByTestId("excuse-row-7");
    expect(calls.some((call) => call.url.includes("status=APPROVED"))).toBe(true);

    await user.selectOptions(screen.getByTestId("filter-reason"), "FAMILY");
    await screen.findByTestId("excuse-row-7");
    expect(calls.some((call) => call.url.includes("reason_type=FAMILY"))).toBe(true);
  });

  it("previews coverage and warns about incomplete days before approval", async () => {
    mockApi({
      "/auth/me/": { body: meWithRoles(["VICE_PRINCIPAL"]) },
      "/excuses/kpis/": { body: KPIS },
      "/excuses/7/preview/": { body: PREVIEW },
      "/excuses/7/": { body: DETAIL },
      "/excuses/": { body: LIST },
    });
    renderApp("/excuses");
    const user = userEvent.setup();

    await user.click(await screen.findByTestId("open-excuse-7"));
    await user.click(await screen.findByTestId("preview-excuse"));

    const preview = await screen.findByTestId("excuse-preview");
    expect(preview).toHaveTextContent("11 حصة غياب سيتحول تصنيفها");
    expect(preview).toHaveTextContent("بيانات اليوم غير مكتملة: 3 حصة لم تعتمد بعد");
  });

  it("sends the preview hash when approving", async () => {
    const { calls } = mockApi({
      "/auth/me/": { body: meWithRoles(["VICE_PRINCIPAL"]) },
      "/excuses/kpis/": { body: KPIS },
      "/excuses/7/preview/": { body: PREVIEW },
      "/excuses/7/approve/": { body: { ...DETAIL, status: "APPROVED" } },
      "/excuses/7/": { body: DETAIL },
      "/excuses/": { body: LIST },
    });
    renderApp("/excuses");
    const user = userEvent.setup();

    await user.click(await screen.findByTestId("open-excuse-7"));
    await user.click(await screen.findByTestId("preview-excuse"));
    await user.click(await screen.findByTestId("confirm-approve"));

    const approveCall = calls.find(
      (call) => call.url.includes("/excuses/7/approve/") && call.init?.method === "POST",
    );
    expect(approveCall).toBeDefined();
    expect(JSON.parse(String(approveCall!.init!.body))).toEqual({
      preview_hash: "hash-abc",
    });
  });

  it("surfaces a stale preview error from the API", async () => {
    mockApi({
      "/auth/me/": { body: meWithRoles(["VICE_PRINCIPAL"]) },
      "/excuses/kpis/": { body: KPIS },
      "/excuses/7/preview/": { body: PREVIEW },
      "/excuses/7/approve/": {
        status: 409,
        body: {
          code: "EXCUSE_PREVIEW_STALE",
          message: "تغير سجل الحضور منذ معاينة العذر. يرجى إعادة المعاينة.",
          details: {},
        },
      },
      "/excuses/7/": { body: DETAIL },
      "/excuses/": { body: LIST },
    });
    renderApp("/excuses");
    const user = userEvent.setup();

    await user.click(await screen.findByTestId("open-excuse-7"));
    await user.click(await screen.findByTestId("preview-excuse"));
    await user.click(await screen.findByTestId("confirm-approve"));

    expect(await screen.findByTestId("excuse-action-error")).toHaveTextContent(
      "تغير سجل الحضور منذ معاينة العذر",
    );
  });

  it("rejects with a reason", async () => {
    const { calls } = mockApi({
      "/auth/me/": { body: meWithRoles(["VICE_PRINCIPAL"]) },
      "/excuses/kpis/": { body: KPIS },
      "/excuses/7/reject/": { body: { ...DETAIL, status: "REJECTED" } },
      "/excuses/7/": { body: DETAIL },
      "/excuses/": { body: LIST },
    });
    renderApp("/excuses");
    const user = userEvent.setup();

    await user.click(await screen.findByTestId("open-excuse-7"));
    await user.type(await screen.findByTestId("decision-reason"), "بلا مستند");
    await user.click(screen.getByTestId("reject-excuse"));

    const rejectCall = calls.find((call) => call.url.includes("/excuses/7/reject/"));
    expect(JSON.parse(String(rejectCall!.init!.body))).toEqual({ reason: "بلا مستند" });
  });

  it("cancels an approved excuse and shows voided coverage", async () => {
    const approved = {
      ...DETAIL,
      status: "APPROVED",
      status_label: "معتمد",
      approved_by_name: "مدير المدرسة",
      coverages: [
        {
          id: 3,
          attendance_date: "2026-08-17",
          period_sequence: 1,
          status: "VOIDED",
          status_label: "ملغاة",
          voided_at: "2026-08-19T10:00:00Z",
          void_reason: "ATTENDANCE_CHANGED",
        },
      ],
    };
    const { calls } = mockApi({
      "/auth/me/": { body: meWithRoles(["SCHOOL_MANAGER"]) },
      "/excuses/kpis/": { body: KPIS },
      "/excuses/7/cancel/": { body: { ...approved, status: "CANCELLED" } },
      "/excuses/7/": { body: approved },
      "/excuses/": { body: LIST },
    });
    renderApp("/excuses");
    const user = userEvent.setup();

    await user.click(await screen.findByTestId("open-excuse-7"));
    expect(await screen.findByTestId("coverage-3")).toHaveTextContent("تغير الحضور");

    await user.type(await screen.findByTestId("decision-reason"), "خطأ إداري");
    await user.click(screen.getByTestId("cancel-excuse"));
    const cancelCall = calls.find((call) => call.url.includes("/excuses/7/cancel/"));
    expect(JSON.parse(String(cancelCall!.init!.body))).toEqual({ reason: "خطأ إداري" });
  });

  it("uploads an attachment as FormData", async () => {
    const { calls } = mockApi({
      "/auth/me/": { body: meWithRoles(["VICE_PRINCIPAL"]) },
      "/excuses/kpis/": { body: KPIS },
      "/excuses/7/attachments/": {
        status: 201,
        body: {
          id: 4,
          original_filename: "report.pdf",
          mime_type: "application/pdf",
          size_bytes: 2048,
          created_at: "2026-08-19T09:30:00Z",
          uploaded_by_name: "وكيل المدرسة",
        },
      },
      "/excuses/7/": { body: DETAIL },
      "/excuses/": { body: LIST },
    });
    renderApp("/excuses");
    const user = userEvent.setup();

    await user.click(await screen.findByTestId("open-excuse-7"));
    const input = await screen.findByTestId("attachment-input");
    await user.upload(
      input,
      new File(["%PDF-1.4"], "report.pdf", { type: "application/pdf" }),
    );

    const upload = calls.find(
      (call) => call.url.includes("/excuses/7/attachments/") && call.init?.method === "POST",
    );
    expect(upload).toBeDefined();
    expect(upload!.init!.body).toBeInstanceOf(FormData);
  });

  it("creates a full-day multi-day excuse from the page", async () => {
    const { calls } = mockApi({
      "/auth/me/": { body: meWithRoles(["VICE_PRINCIPAL"]) },
      "/excuses/kpis/": { body: KPIS },
      "/students/search/": {
        body: {
          results: [{ id: 5, full_name: "محمد أحمد", national_id_masked: "******5678" }],
        },
      },
      "/excuses/7/": { body: DETAIL },
      "/excuses/": { body: LIST },
    });
    renderApp("/excuses");
    const user = userEvent.setup();

    await user.click(await screen.findByTestId("new-excuse"));
    await user.type(screen.getByLabelText("بحث عن طالب"), "محمد");
    await user.click(await screen.findByTestId("pick-student-5"));
    expect(screen.getByTestId("selected-student")).toHaveTextContent("محمد أحمد");

    await user.clear(screen.getByTestId("excuse-from"));
    await user.type(screen.getByTestId("excuse-from"), "2026-08-17");
    await user.clear(screen.getByTestId("excuse-to"));
    await user.type(screen.getByTestId("excuse-to"), "2026-08-19");
    await user.click(screen.getByTestId("save-excuse"));

    const create = calls.find(
      (call) => call.url.endsWith("/excuses/") && call.init?.method === "POST",
    );
    const body = JSON.parse(String(create!.init!.body));
    expect(body.student_id).toBe(5);
    expect(body.reason_type).toBe("MEDICAL_REPORT");
    expect(body.targets).toEqual([
      { attendance_date: "2026-08-17" },
      { attendance_date: "2026-08-18" },
      { attendance_date: "2026-08-19" },
    ]);
  });

  it("creates a period-specific excuse", async () => {
    const { calls } = mockApi({
      "/auth/me/": { body: meWithRoles(["VICE_PRINCIPAL"]) },
      "/excuses/kpis/": { body: KPIS },
      "/students/search/": {
        body: {
          results: [{ id: 5, full_name: "محمد أحمد", national_id_masked: "******5678" }],
        },
      },
      "/excuses/7/": { body: DETAIL },
      "/excuses/": { body: LIST },
    });
    renderApp("/excuses");
    const user = userEvent.setup();

    await user.click(await screen.findByTestId("new-excuse"));
    await user.type(screen.getByLabelText("بحث عن طالب"), "محمد");
    await user.click(await screen.findByTestId("pick-student-5"));
    await user.selectOptions(screen.getByTestId("excuse-scope"), "PERIODS");
    await user.clear(screen.getByTestId("excuse-from"));
    await user.type(screen.getByTestId("excuse-from"), "2026-08-19");
    await user.type(screen.getByTestId("excuse-periods"), "2، 3");
    await user.click(screen.getByTestId("save-excuse"));

    const create = calls.find(
      (call) => call.url.endsWith("/excuses/") && call.init?.method === "POST",
    );
    expect(JSON.parse(String(create!.init!.body)).targets).toEqual([
      { attendance_date: "2026-08-19", period_sequence: 2 },
      { attendance_date: "2026-08-19", period_sequence: 3 },
    ]);
  });

  it("hides management actions from a counselor (read-only)", async () => {
    mockApi({
      "/auth/me/": { body: meWithRoles(["COUNSELOR"]) },
      "/excuses/kpis/": { body: KPIS },
      "/excuses/7/": { body: DETAIL },
      "/excuses/": { body: LIST },
    });
    renderApp("/excuses");
    const user = userEvent.setup();

    await screen.findByTestId("excuse-row-7");
    expect(screen.queryByTestId("new-excuse")).not.toBeInTheDocument();
    await user.click(screen.getByTestId("open-excuse-7"));
    await screen.findByTestId("excuse-detail");
    expect(screen.queryByTestId("preview-excuse")).not.toBeInTheDocument();
    expect(screen.queryByTestId("reject-excuse")).not.toBeInTheDocument();
    expect(screen.queryByTestId("attachment-input")).not.toBeInTheDocument();
  });

  it("denies a teacher with an Arabic message", async () => {
    mockApi({
      "/auth/me/": { body: meWithRoles(["TEACHER"]) },
      "/excuses/kpis/": {
        status: 403,
        body: { code: "PERMISSION_DENIED", message: "ليست لديك صلاحية.", details: {} },
      },
      "/excuses/": {
        status: 403,
        body: { code: "PERMISSION_DENIED", message: "ليست لديك صلاحية.", details: {} },
      },
    });
    renderApp("/excuses");
    expect(
      await screen.findByRole("heading", { name: "لا تملك صلاحية عرض الأعذار" }),
    ).toBeInTheDocument();
  });
});
