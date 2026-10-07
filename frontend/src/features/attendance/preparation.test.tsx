import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import { queryClient } from "@/app/queryClient";
import type { MonitoringSection, PreparationToday } from "@/features/attendance/api";
import { buildMe, membership, mockApi } from "@/test/mockApi";
import { renderApp } from "@/test/renderApp";
import { mockBrowserStorage } from "@/test/browserStorage";

const DATE = "2026-10-05";
const PERIOD = { sequence: 1, name: "الحصة الأولى", start_time: "08:00", end_time: "08:40", timezone: "Asia/Riyadh" };
const ROSTER = [{ student_id: 11, full_name: "طالب تجريبي", national_id_masked: "******0011" }];
const SECTION = { id: 3, name: "1", grade_name: "الأول الثانوي", department: "عام", students_count: 1 };
const SESSION = { id: 5, updated_at: `${DATE}T09:00:00.123456+03:00`, status: "IN_PROGRESS", attendance_date: DATE, section: SECTION, period: PERIOD, submitted_by: null, submitted_at: null, can_edit: true, roster: ROSTER, marks: [] };

function roleMe(role: "SCHOOL_MANAGER" | "VICE_PRINCIPAL") {
  return buildMe({ active_school: { id: 10, name: "مدرسة التجربة", slug: "qa" }, roles: [role], memberships: [membership(1, 10, "مدرسة التجربة", [role])] });
}

function row(id: number, status: MonitoringSection["attendance_status"]): MonitoringSection {
  return { section_id: id, section_name: String(id), grade_id: 1, grade_name: "الأول الثانوي", department: "عام", students_count: 1, attendance_status: status, timeliness_status: "OVERDUE", minutes_overdue: 10, started_at: status === "NOT_STARTED" ? null : "08:01", submitted_at: status === "SUBMITTED" ? "08:30" : null, teacher_name: null, session_id: status === "NOT_STARTED" ? null : id };
}

const DAY: PreparationToday = {
  date: DATE, school_time: `${DATE}T09:05:00+03:00`, is_school_day: true,
  periods: [{ ...PERIOD, state: "ENDED", summary: { total: 3, submitted: 1, in_progress: 1, not_started: 1, incomplete: 2, overdue: 2 }, sections: [row(1, "NOT_STARTED"), row(2, "IN_PROGRESS"), row(3, "SUBMITTED")] }, { ...PERIOD, sequence: 2, name: "الحصة الثانية", state: "UPCOMING", summary: null, sections: [] }],
};

describe("administrative preparation", () => {
  beforeEach(() => { queryClient.clear(); mockBrowserStorage(); document.cookie = "csrftoken=test-token"; });

  it("opens only unfinished sections for the chosen period and links explicit targets", async () => {
    mockApi({ "/auth/me/": { body: roleMe("VICE_PRINCIPAL") }, "/attendance/preparation/today/": { body: DAY } });
    renderApp(`/attendance/monitoring?date=${DATE}&period=1&status=INCOMPLETE`);
    const list = await screen.findByTestId("monitoring-list");
    expect(within(list).queryByTestId("monitoring-section-3")).toBeNull();
    expect(within(list).getByRole("link", { name: /تحضير الفصل/ })).toHaveAttribute("href", `/attendance/section/1?date=${DATE}&period=1`);
    expect(within(list).getByRole("link", { name: /استكمال التحضير/ })).toHaveAttribute("href", `/attendance/section/2?date=${DATE}&period=1`);
    const card = screen.getByTestId("preparation-period-1");
    expect(within(card).getByRole("link")).toHaveAttribute("href", `/attendance/monitoring?date=${DATE}&period=1&status=INCOMPLETE`);
    expect(screen.getByTestId("preparation-period-2")).toHaveTextContent("لم تبدأ");
    expect(within(screen.getByTestId("preparation-period-2")).queryByRole("link")).toBeNull();
  });

  for (const role of ["SCHOOL_MANAGER", "VICE_PRINCIPAL"] as const) {
    it(`${role} explicitly starts and approves an ended period with a reason`, async () => {
      const user = userEvent.setup();
      const { calls } = mockApi({
        "/auth/me/": { body: roleMe(role) },
        "/attendance/admin/sections/3/preview/": { body: { attendance_date: DATE, section: SECTION, period: PERIOD, session: null } },
        "/attendance/admin/sessions/start/": { body: SESSION },
        "/attendance/admin/sessions/5/submit/": { body: { ...SESSION, status: "SUBMITTED", submitted_by: "الإدارة", submitted_at: `${DATE}T09:06:00+03:00` } },
      });
      renderApp(`/attendance/section/3?date=${DATE}&period=1`);
      await screen.findByTestId("attendance-start-confirmation");
      expect(calls.some((call) => call.init?.method === "POST")).toBe(false);
      await user.click(screen.getByTestId("start-attendance"));
      await screen.findByTestId("roster-list");
      const started = calls.find((call) => call.url.includes("admin/sessions/start"));
      expect(JSON.parse(String(started?.init?.body))).toEqual({ section_id: 3, date: DATE, period_sequence: 1 });
      expect(screen.getByTestId("submit-attendance")).toBeDisabled();
      await user.type(screen.getByTestId("administrative-reason"), "تغطية إدارية");
      await user.click(within(screen.getByTestId("roster-student-11")).getByRole("button", { name: "غائب" }));
      await user.click(screen.getByTestId("submit-attendance"));
      expect(await screen.findByTestId("submitted-banner")).toHaveTextContent("الإدارة");
      const submitted = calls.find((call) => call.url.includes("admin/sessions/5/submit"));
      expect(JSON.parse(String(submitted?.init?.body))).toEqual({ marks: [{ student_id: 11, status: "ABSENT" }], reason: "تغطية إدارية" });
    });
  }

  it("resumes a teacher session and displays the winning submission when another actor approves first", async () => {
    const user = userEvent.setup();
    const winner = { ...SESSION, status: "SUBMITTED", submitted_by: "المعلم السابق", submitted_at: `${DATE}T09:06:00+03:00`, marks: [{ student_id: 11, status: "ABSENT" }] };
    const { calls } = mockApi({
      "/auth/me/": { body: roleMe("VICE_PRINCIPAL") },
      "/attendance/admin/sections/3/preview/": { body: { attendance_date: DATE, section: SECTION, period: PERIOD, session: SESSION } },
      "/attendance/admin/sessions/5/submit/": { status: 409, body: { code: "ATTENDANCE_SESSION_ALREADY_SUBMITTED", message: "سبق اعتماد التحضير بواسطة المعلم", details: {} } },
      "/attendance/sessions/5/": { body: winner },
    });
    renderApp(`/attendance/section/3?date=${DATE}&period=1`);
    await screen.findByTestId("roster-list");
    expect(calls.some((call) => call.url.includes("sessions/start"))).toBe(false);
    await user.type(screen.getByTestId("administrative-reason"), "تغطية إدارية");
    await user.click(screen.getByTestId("submit-attendance"));
    await waitFor(() => expect(screen.getByTestId("submitted-banner")).toHaveTextContent("المعلم السابق"));
    expect(screen.getByTestId("roster-student-11")).toHaveTextContent("غائب");
    expect(screen.queryByTestId("submit-attendance")).toBeNull();
    expect(screen.getByText("سبق اعتماد التحضير بواسطة المعلم")).toBeInTheDocument();
  });

  it("does not interpret an old date as today's period", async () => {
    mockApi({ "/auth/me/": { body: roleMe("VICE_PRINCIPAL") }, "/attendance/preparation/today/": { body: DAY } });
    renderApp("/attendance/monitoring?date=2026-10-04&period=1&status=INCOMPLETE");
    expect(await screen.findByText(/هذا الرابط يخص يومًا سابقًا/)).toBeInTheDocument();
    expect(screen.queryByTestId("monitoring-list")).toBeNull();
  });

  for (const role of ["SCHOOL_MANAGER", "VICE_PRINCIPAL"] as const) {
    it(`${role} opens submitted classes and corrects them with a required reason and version`, async () => {
      const user = userEvent.setup();
      const submitted = { ...SESSION, status: "SUBMITTED", submitted_by: "المعلم", submitted_at: `${DATE}T08:30:00+03:00`, marks: [{ student_id: 11, status: "ABSENT" }] };
      const { calls } = mockApi({
        "/auth/me/": { body: roleMe(role) },
        "/attendance/preparation/today/": { body: DAY },
        "/attendance/admin/sections/3/preview/": { body: { attendance_date: DATE, section: SECTION, period: PERIOD, session: submitted } },
        "/attendance/sessions/5/": { body: { ...submitted, updated_at: `${DATE}T09:10:00.654321+03:00`, marks: [] } },
      });
      renderApp(`/attendance/monitoring?date=${DATE}&period=1&status=ALL`);
      await user.click(await screen.findByTestId("correct-section-3"));
      await user.click(await screen.findByTestId("edit-button"));
      expect(screen.getByLabelText("سبب التصحيح الإداري (مطلوب)")).toBeRequired();
      expect(screen.getByTestId("submit-attendance")).toBeDisabled();
      await user.type(screen.getByTestId("edit-reason"), "   ");
      expect(screen.getByTestId("submit-attendance")).toBeDisabled();
      await user.clear(screen.getByTestId("edit-reason"));
      await user.type(screen.getByTestId("edit-reason"), "  تحقق إداري  ");
      await user.click(within(screen.getByTestId("roster-student-11")).getByRole("button", { name: "حاضر" }));
      await user.click(screen.getByTestId("submit-attendance"));
      await waitFor(() => expect(screen.queryByTestId("submit-attendance")).toBeNull());
      const patch = calls.find((call) => call.init?.method === "PATCH");
      expect(JSON.parse(String(patch?.init?.body))).toEqual({ marks: [], reason: "تحقق إداري", expected_updated_at: submitted.updated_at });
      expect(screen.getByRole("link", { name: "العودة للمتابعة" })).toHaveAttribute("href", `/attendance/monitoring?date=${DATE}&period=1&status=ALL`);
    });
  }

  it("rejects a stale edit, displays current marks and requires a fresh review before retry", async () => {
    const user = userEvent.setup();
    const submitted = { ...SESSION, status: "SUBMITTED", submitted_by: "المعلم", submitted_at: `${DATE}T08:30:00+03:00` };
    const latest = { ...submitted, updated_at: `${DATE}T09:10:00.654321+03:00`, marks: [{ student_id: 11, status: "ABSENT" }] };
    let edits = 0;
    const { calls } = mockApi({
      "/auth/me/": { body: roleMe("VICE_PRINCIPAL") },
      "/attendance/admin/sections/3/preview/": { body: { attendance_date: DATE, section: SECTION, period: PERIOD, session: submitted } },
      "/attendance/sessions/5/": (init) => {
        if (init?.method !== "PATCH") return { body: latest };
        edits += 1;
        return edits === 1
          ? { status: 409, body: { code: "ATTENDANCE_SESSION_CHANGED", message: "تغير التحضير؛ لم يُحفظ تصحيحك. راجع أحدث البيانات.", details: {} } }
          : { body: { ...latest, marks: [], updated_at: `${DATE}T09:11:00.123456+03:00` } };
      },
    });
    renderApp(`/attendance/section/3?date=${DATE}&period=1`);
    await user.click(await screen.findByTestId("edit-button"));
    await user.type(screen.getByTestId("edit-reason"), "تحقق إداري");
    await user.click(screen.getByTestId("submit-attendance"));
    expect(await screen.findByText(/تغير التحضير؛ لم يُحفظ تصحيحك/)).toBeInTheDocument();
    expect(screen.getByTestId("roster-student-11")).toHaveTextContent("غائب");
    expect(screen.queryByTestId("submit-attendance")).toBeNull();
    expect(edits).toBe(1);
    await user.click(screen.getByTestId("edit-button"));
    await user.click(within(screen.getByTestId("roster-student-11")).getByRole("button", { name: "حاضر" }));
    await user.click(screen.getByTestId("submit-attendance"));
    await waitFor(() => expect(edits).toBe(2));
    const patches = calls.filter((call) => call.init?.method === "PATCH");
    expect(JSON.parse(String(patches[0]?.init?.body)).expected_updated_at).toBe(submitted.updated_at);
    expect(JSON.parse(String(patches[1]?.init?.body)).expected_updated_at).toBe(latest.updated_at);
  });

  it("does not send a teacher's explicit administrative link to the current-period API", async () => {
    const me = buildMe({ active_school: { id: 10, name: "مدرسة التجربة", slug: "qa" }, roles: ["TEACHER"], memberships: [membership(1, 10, "مدرسة التجربة", ["TEACHER"])] });
    const { calls } = mockApi({ "/auth/me/": { body: me } });
    renderApp(`/attendance/section/3?date=${DATE}&period=1`);
    expect(await screen.findByText(/التحضير لحصة محددة متاح للمدير والوكيل/)).toBeInTheDocument();
    expect(calls.some((call) => call.url.includes("/attendance/"))).toBe(false);
  });

  it("requires a complete administrative target even for a manager who is also a teacher", async () => {
    const me = roleMe("SCHOOL_MANAGER");
    me.roles.push("TEACHER");
    me.memberships = [membership(1, 10, "مدرسة التجربة", ["SCHOOL_MANAGER", "TEACHER"])];
    const { calls } = mockApi({ "/auth/me/": { body: me } });
    renderApp(`/attendance/section/3?date=${DATE}`);
    expect(await screen.findByText("اختر الحصة والفصل من متابعة تحضير اليوم.")).toBeInTheDocument();
    expect(calls.some((call) => call.url.includes("/attendance/"))).toBe(false);
  });
});
