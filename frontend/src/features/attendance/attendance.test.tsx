import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { queryClient } from "@/app/queryClient";
import { currentTimeInZone } from "@/features/attendance/AttendanceSessionPage";
import { buildMe, membership, mockApi, UNAUTHENTICATED } from "@/test/mockApi";
import { renderApp } from "@/test/renderApp";

vi.mock("qrcode", () => ({
  default: { toCanvas: vi.fn().mockResolvedValue(undefined) },
}));

function teacherMe() {
  return buildMe({
    active_school: { id: 10, name: "ثانوية الأندلس", slug: "andalus" },
    roles: ["TEACHER"],
    memberships: [membership(1, 10, "ثانوية الأندلس", ["TEACHER"])],
  });
}

function managerMe() {
  return buildMe({
    active_school: { id: 10, name: "ثانوية الأندلس", slug: "andalus" },
    roles: ["SCHOOL_MANAGER"],
    memberships: [membership(1, 10, "ثانوية الأندلس", ["SCHOOL_MANAGER"])],
  });
}

const SECTIONS = [
  { id: 3, name: "1", grade_name: "الأول الثانوي", students_count: 3 },
  { id: 4, name: "2", grade_name: "الأول الثانوي", students_count: 25 },
];

const ROSTER = [
  { student_id: 11, full_name: "طالب أول", national_id_masked: "******0011" },
  { student_id: 12, full_name: "طالب ثانٍ", national_id_masked: "******0012" },
  { student_id: 13, full_name: "طالب ثالث", national_id_masked: "******0013" },
];

function sessionBody(overrides: Record<string, unknown> = {}) {
  return {
    id: 5,
    status: "IN_PROGRESS",
    attendance_date: "2026-08-19",
    section: { id: 3, name: "1", grade_name: "الأول الثانوي", students_count: 3 },
    period: {
      sequence: 2,
      name: "الثانية",
      start_time: "08:05",
      end_time: "08:50",
      timezone: "Asia/Riyadh",
    },
    submitted_by: null,
    submitted_at: null,
    can_edit: true,
    roster: ROSTER,
    marks: [],
    ...overrides,
  };
}

function parseBody(init?: RequestInit): Record<string, unknown> {
  return JSON.parse(String(init?.body ?? "{}")) as Record<string, unknown>;
}

describe("attendance", () => {
  beforeEach(() => {
    queryClient.clear();
    document.cookie = "csrftoken=test-token";
  });

  it("uses the school timezone for the default late-arrival time", () => {
    const utcNow = new Date("2026-09-05T16:51:00Z");
    expect(currentTimeInZone("Asia/Riyadh", utcNow)).toBe("19:51");
    expect(currentTimeInZone("Asia/Dubai", utcNow)).toBe("20:51");
  });

  it("teacher home shows current period and sections", async () => {
    mockApi({
      "/auth/me/": { body: teacherMe() },
      "/attendance/current-period/": {
        body: {
          period: { sequence: 2, name: "الثانية", start_time: "08:05", end_time: "08:50" },
          date: "2026-08-19",
        },
      },
      "/attendance/sections/": { body: SECTIONS },
    });

    renderApp("/");
    expect(await screen.findByTestId("current-period-name")).toHaveTextContent("الثانية");
    const list = await screen.findByTestId("sections-list");
    expect(within(list).getByTestId("section-3")).toHaveTextContent("3 طالبًا");
    expect(within(list).getByTestId("section-4")).toHaveTextContent("الأول الثانوي");
  });

  it("filters a long section list and offers a clear empty search state", async () => {
    const manySections = [
      ...SECTIONS,
      { id: 5, name: "1", grade_name: "الثاني الثانوي", students_count: 20 },
      { id: 6, name: "2", grade_name: "الثاني الثانوي", students_count: 22 },
      { id: 7, name: "1", grade_name: "الثالث الثانوي", students_count: 18 },
      { id: 8, name: "2", grade_name: "الثالث الثانوي", students_count: 21 },
      { id: 9, name: "الموهوبين", grade_name: "الأول الثانوي", students_count: 12 },
    ];
    mockApi({
      "/auth/me/": { body: teacherMe() },
      "/attendance/current-period/": { body: { period: null, date: "2026-08-19" } },
      "/attendance/sections/": { body: manySections },
    });

    renderApp("/");
    const user = userEvent.setup();
    const search = await screen.findByTestId("section-search");

    await user.type(search, "الموهوبين");
    const list = screen.getByTestId("sections-list");
    expect(within(list).getByTestId("section-9")).toBeInTheDocument();
    expect(within(list).queryByTestId("section-3")).toBeNull();

    await user.clear(search);
    await user.type(search, "غير موجود");
    expect(screen.getByText("لا يوجد فصل مطابق")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "مسح البحث" }));
    expect(await screen.findByTestId("section-3")).toBeInTheDocument();
  });

  it("teacher home shows a clear message when no period is active", async () => {
    mockApi({
      "/auth/me/": { body: teacherMe() },
      "/attendance/current-period/": { body: { period: null, date: "2026-08-19" } },
      "/attendance/sections/": { body: [] },
    });

    renderApp("/");
    expect(await screen.findByTestId("no-current-period")).toBeInTheDocument();
    expect(await screen.findByTestId("no-sections")).toBeInTheDocument();
  });

  it("searches the roster and can focus on attendance exceptions", async () => {
    mockApi({
      "/auth/me/": { body: teacherMe() },
      "/attendance/sessions/start/": { status: 201, body: sessionBody() },
    });

    renderApp("/attendance/section/3");
    const user = userEvent.setup();
    const search = await screen.findByRole("searchbox", { name: "البحث في قائمة الطلاب" });

    await user.type(search, "ثانٍ");
    expect(screen.getByTestId("roster-student-12")).toBeInTheDocument();
    expect(screen.queryByTestId("roster-student-11")).toBeNull();

    await user.clear(search);
    await user.click(
      within(screen.getByTestId("roster-student-11")).getByRole("button", { name: "غائب" }),
    );
    await user.click(screen.getByTestId("exceptions-only"));

    expect(screen.getByTestId("roster-student-11")).toBeInTheDocument();
    expect(screen.queryByTestId("roster-student-12")).toBeNull();
    expect(screen.getByText("سيُرسل 1 استثناء، والبقية حاضرون تلقائيًا.")).toBeInTheDocument();

    await user.click(screen.getByTestId("exceptions-only"));
    expect(screen.getByTestId("roster-student-12")).toBeInTheDocument();
  });

  it("submits exceptions only: absent + late with arrival time, never late_minutes", async () => {
    const { calls } = mockApi({
      "/auth/me/": { body: teacherMe() },
      "/attendance/sessions/start/": { status: 201, body: sessionBody() },
      "/attendance/sessions/5/submit/": {
        body: sessionBody({
          status: "SUBMITTED",
          submitted_by: "أحمد المعلم",
          submitted_at: "2026-08-19T08:20:00Z",
          marks: [
            { student_id: 11, status: "ABSENT", arrival_time: null, late_minutes: null },
            { student_id: 12, status: "LATE", arrival_time: "08:15", late_minutes: 10 },
          ],
        }),
      },
    });

    renderApp("/attendance/section/3");
    const user = userEvent.setup();

    const rowOne = await screen.findByTestId("roster-student-11");
    await user.click(within(rowOne).getByRole("button", { name: "غائب" }));
    const rowTwo = screen.getByTestId("roster-student-12");
    await user.click(within(rowTwo).getByRole("button", { name: "متأخر" }));

    // الملخص الحي يتحدث فورًا
    expect(screen.getByTestId("live-summary")).toHaveTextContent("حاضر 1");
    expect(screen.getByTestId("live-summary")).toHaveTextContent("غائب 1");
    expect(screen.getByTestId("live-summary")).toHaveTextContent("متأخر 1");

    await user.click(screen.getByTestId("submit-attendance"));
    expect(await screen.findByTestId("submitted-banner")).toHaveTextContent("أحمد المعلم");

    const submitCall = calls.find((c) => c.url.includes("/submit/"));
    const body = parseBody(submitCall?.init);
    const marks = body.marks as Record<string, unknown>[];
    expect(marks).toHaveLength(2); // استثناءات فقط — لا «حاضر»
    expect(marks[0]).toMatchObject({ student_id: 11, status: "ABSENT", arrival_time: null });
    expect(marks[1]?.student_id).toBe(12);
    expect(marks[1]?.arrival_time).toMatch(/^\d{2}:\d{2}$/);
    expect(JSON.stringify(body)).not.toContain("late_minutes"); // يحسبه الخادم حصرًا
  });

  it("shows submitted view with late minutes and no edit button when can_edit=false", async () => {
    mockApi({
      "/auth/me/": { body: teacherMe() },
      "/attendance/sessions/start/": {
        body: sessionBody({
          status: "SUBMITTED",
          submitted_by: "خالد المدير",
          submitted_at: "2026-08-19T08:20:00Z",
          can_edit: false,
          marks: [{ student_id: 12, status: "LATE", arrival_time: "08:15", late_minutes: 10 }],
        }),
      },
    });

    renderApp("/attendance/section/3");
    expect(await screen.findByTestId("submitted-banner")).toHaveTextContent("خالد المدير");
    expect(screen.getByTestId("roster-student-12")).toHaveTextContent("متأخر (10 د)");
    expect(screen.queryByTestId("edit-button")).not.toBeInTheDocument();
    expect(screen.queryByTestId("submit-attendance")).not.toBeInTheDocument();
  });

  it("edits a submitted session with a reason via PATCH", async () => {
    const { calls } = mockApi({
      "/auth/me/": { body: teacherMe() },
      "/attendance/sessions/start/": {
        body: sessionBody({
          status: "SUBMITTED",
          submitted_by: "أحمد المعلم",
          submitted_at: "2026-08-19T08:20:00Z",
          marks: [{ student_id: 11, status: "ABSENT", arrival_time: null, late_minutes: null }],
        }),
      },
      "/attendance/sessions/5/": (init) =>
        init?.method === "PATCH"
          ? {
              body: sessionBody({
                status: "SUBMITTED",
                submitted_by: "أحمد المعلم",
                submitted_at: "2026-08-19T08:20:00Z",
                marks: [],
              }),
            }
          : { body: sessionBody() },
    });

    renderApp("/attendance/section/3");
    const user = userEvent.setup();

    await user.click(await screen.findByTestId("edit-button"));
    const rowOne = screen.getByTestId("roster-student-11");
    await user.click(within(rowOne).getByRole("button", { name: "حاضر" }));
    await user.type(screen.getByTestId("edit-reason"), "عاد الطالب");
    await user.click(screen.getByTestId("submit-attendance"));

    await waitFor(() => {
      const patchCall = calls.find((c) => c.init?.method === "PATCH");
      expect(patchCall).toBeDefined();
      const body = parseBody(patchCall?.init);
      expect(body.marks).toEqual([]);
      expect(body.reason).toBe("عاد الطالب");
    });
  });

  it("refreshes the roster and keeps marks when the server reports ROSTER_CHANGED", async () => {
    let startCalls = 0;
    mockApi({
      "/auth/me/": { body: teacherMe() },
      "/attendance/sessions/start/": () => {
        startCalls += 1;
        return startCalls === 1
          ? { status: 201, body: sessionBody() }
          : {
              body: sessionBody({
                roster: [
                  ...ROSTER,
                  { student_id: 14, full_name: "طالب جديد", national_id_masked: "******0014" },
                ],
              }),
            };
      },
      "/attendance/sessions/5/submit/": {
        status: 409,
        body: {
          code: "ATTENDANCE_ROSTER_CHANGED",
          message: "تغيرت قائمة الفصل.",
          details: {},
        },
      },
    });

    renderApp("/attendance/section/3");
    const user = userEvent.setup();

    const rowOne = await screen.findByTestId("roster-student-11");
    await user.click(within(rowOne).getByRole("button", { name: "غائب" }));
    await user.click(screen.getByTestId("submit-attendance"));

    expect(await screen.findByTestId("roster-changed-notice")).toBeInTheDocument();
    expect(await screen.findByTestId("roster-student-14")).toBeInTheDocument();
    // العلامة السابقة باقية بعد التحديث
    expect(
      within(screen.getByTestId("roster-student-11")).getByRole("button", { name: "غائب" }),
    ).toHaveAttribute("aria-pressed", "true");
  });

  it("resolves a QR token and opens the section roster", async () => {
    mockApi({
      "/auth/me/": { body: teacherMe() },
      "/attendance/qr/resolve/": { body: SECTIONS[0] },
      "/attendance/sessions/start/": { status: 201, body: sessionBody() },
    });

    renderApp("/qr/tok-abc123");
    expect(await screen.findByTestId("session-section-name")).toHaveTextContent("1");
    expect(await screen.findByTestId("roster-student-11")).toBeInTheDocument();
  });

  it("shows an isolated public gate without resolving or leaking QR data", async () => {
    const { calls } = mockApi({ "/auth/me/": UNAUTHENTICATED });

    renderApp("/qr/private-token-123");

    expect(
      await screen.findByRole("heading", { name: "هذا الرمز مخصص للمعلمين المصرح لهم" }),
    ).toBeInTheDocument();
    expect(screen.getByTestId("qr-access-gate")).toHaveTextContent("لم يتم عرض أي بيانات مدرسية");
    expect(screen.getByRole("link", { name: "دخول الموظفين المصرح لهم" })).toHaveAttribute(
      "href",
      "/login?returnTo=%2Fqr%2Fprivate-token-123",
    );
    expect(screen.queryByText("private-token-123")).not.toBeInTheDocument();
    expect(screen.queryByText("ثانوية الأندلس")).not.toBeInTheDocument();
    expect(calls.some((call) => call.url.includes("/attendance/qr/resolve/"))).toBe(false);
  });

  it("does not send the QR token for an authenticated non-teacher", async () => {
    const { calls } = mockApi({ "/auth/me/": { body: managerMe() } });

    renderApp("/qr/private-token-123");

    expect(
      await screen.findByRole("heading", { name: "هذا الحساب غير مخول بفتح التحضير" }),
    ).toBeInTheDocument();
    expect(screen.getByTestId("qr-access-gate")).toHaveTextContent(
      "لم يتم إرسال الرمز للتحقق",
    );
    expect(screen.queryByText("ثانوية الأندلس")).not.toBeInTheDocument();
    expect(calls.some((call) => call.url.includes("/attendance/qr/resolve/"))).toBe(false);
  });

  it("shows the API error for an invalid or rotated QR token", async () => {
    mockApi({
      "/auth/me/": { body: teacherMe() },
      "/attendance/qr/resolve/": {
        status: 404,
        body: {
          code: "SECTION_QR_INVALID",
          message: "رمز QR غير صالح أو تم تجديده. اطلب الرمز الحديث من الإدارة.",
          details: {},
        },
      },
    });

    renderApp("/qr/old-token");
    expect(await screen.findByRole("alert")).toHaveTextContent("رمز QR غير صالح");
    expect(screen.getByRole("link", { name: /العودة للرئيسية/ })).toBeInTheDocument();
  });

  it("manager generates and rotates a section QR", async () => {
    let rotated = false;
    vi.stubGlobal("confirm", vi.fn().mockReturnValue(true));
    vi.stubGlobal("print", vi.fn());
    const { calls } = mockApi({
      "/auth/me/": { body: managerMe() },
      "/school/settings/": {
        body: {
          school: { id: 10, name: "ثانوية الأندلس", slug: "andalus" },
          ministry_school_number: "12345",
          education_stage: "SECONDARY",
          city: "الرياض",
          official_principal_name: "خالد المدير",
          timezone: "Asia/Riyadh",
          logo_url: null,
          attendance_edit_window_minutes: 15,
          unprepared_period_alert_minutes: 25,
          staff: { managers: ["خالد المدير"], vice_principals: [], counselors: [] },
        },
      },
      "/attendance/sections/": { body: SECTIONS },
      "/sections/3/qr/": (init) => {
        if (init?.method === "POST") rotated = true;
        return {
          body: {
            section_id: 3,
            section_name: "1",
            grade_name: "الأول الثانوي",
            token: rotated ? "new-token" : "old-token",
            url_path: rotated ? "/qr/new-token" : "/qr/old-token",
          },
        };
      },
    });

    renderApp("/attendance/qr");
    const user = userEvent.setup();

    const search = await screen.findByLabelText("البحث في الفصول");
    await user.type(search, "2");
    expect(screen.queryByTestId("qr-section-3")).toBeNull();
    expect(screen.getByTestId("qr-section-4")).toBeInTheDocument();
    await user.clear(search);

    await user.click(await screen.findByTestId("qr-section-3"));
    expect(await screen.findByTestId("qr-section-title")).toHaveTextContent("الفصل 1");
    expect(screen.getByTestId("qr-canvas")).toBeInTheDocument();
    const printSheet = screen.getByTestId("qr-print-sheet");
    expect(printSheet).toHaveTextContent("ثانوية الأندلس");
    expect(printSheet).toHaveTextContent("الفصل 1");
    expect(printSheet).toHaveTextContent("الأول الثانوي");

    await user.click(screen.getByTestId("print-qr"));
    expect(window.print).toHaveBeenCalledOnce();

    await user.click(screen.getByTestId("rotate-qr"));
    await waitFor(() => {
      expect(calls.some((c) => c.url.includes("/sections/3/qr/") && c.init?.method === "POST")).toBe(
        true,
      );
    });
  });
});
