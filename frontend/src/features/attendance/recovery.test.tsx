import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { queryClient } from "@/app/queryClient";
import type { AttendanceSessionData } from "./api";
import { clearAttendanceDrafts, readDraft, writeDraft } from "./drafts";
import { buildMe, membership, mockApi } from "@/test/mockApi";
import { renderApp } from "@/test/renderApp";
import { mockBrowserStorage } from "@/test/browserStorage";

const section = { id: 3, name: "4", grade_name: "الثاني الثانوي", department: "المسار العام", students_count: 2 };
const period = { sequence: 1, name: "الحصة الأولى", start_time: "07:00", end_time: "07:45", timezone: "Asia/Riyadh" };
const session: AttendanceSessionData = {
  id: 5, updated_at: "2026-10-07T07:01:00+03:00", status: "IN_PROGRESS", attendance_date: "2026-10-07",
  section, period, submitted_by: null, submitted_at: null, can_edit: true,
  roster: [{ student_id: 11, full_name: "طالب اختبار", national_id_masked: "******0011" },
    { student_id: 12, full_name: "طالب آخر", national_id_masked: "******0012" }], marks: [],
};
const me = buildMe({ active_school: { id: 10, name: "مدرسة الاختبار", slug: "qa" }, roles: ["TEACHER"], memberships: [membership(1, 10, "مدرسة الاختبار", ["TEACHER"])] });
const scope = { userId: me.id, schoolId: 10 };
const preview = { attendance_date: session.attendance_date, section, period, session: null };
const approved = { ...session, status: "SUBMITTED", submitted_by: "معلم الاختبار", submitted_at: "2026-10-07T07:50:00+03:00" };
const absentButton = () => within(screen.getByTestId("roster-student-11")).getByRole("button", { name: "غائب" });

beforeEach(() => {
  queryClient.clear(); vi.restoreAllMocks(); mockBrowserStorage(); document.cookie = "csrftoken=test-token";
});

describe("attendance draft recovery", () => {
  it("restores choices after remount and submits the original session after its period ends", async () => {
    const { calls } = mockApi({
      "/auth/me/": { body: me }, "/attendance/sessions/5/submit/": { body: approved },
      "/attendance/sessions/5/": { body: session },
    });
    const user = userEvent.setup();
    const first = renderApp("/attendance/section/3?session=5");
    await screen.findByTestId("roster-list"); await user.click(absentButton());
    expect(screen.getByTestId("draft-status")).toHaveTextContent("لا يُعتمد");
    first.unmount(); queryClient.clear();
    renderApp("/attendance/section/3?session=5");
    await screen.findByTestId("roster-list");
    expect(absentButton()).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByTestId("draft-status")).toHaveTextContent("استُعيدت");
    expect(screen.queryByTestId("submitted-banner")).toBeNull();
    await user.click(screen.getByTestId("submit-attendance"));
    await screen.findByTestId("submitted-banner");
    const submit = calls.find((call) => call.url.includes("/5/submit/"));
    expect(JSON.parse(String(submit?.init?.body)).marks).toEqual([{ student_id: 11, status: "ABSENT" }]);
    expect(readDraft(scope, session)).toBeNull();
    expect(calls.some((call) => call.url.includes("/preview/") || call.url.includes("/start/"))).toBe(false);
  });

  it("preserves an explicit all-present draft when an absence is cleared", () => {
    expect(writeDraft(scope, session, [11])).toBe(true);
    expect(writeDraft(scope, session, [])).toBe(true);
    expect(readDraft(scope, session)).toEqual([]);
  });

  it("isolates drafts by user, school and session and filters transferred students", () => {
    writeDraft(scope, session, [11, 12]);
    expect(readDraft({ ...scope, userId: 2 }, session)).toBeNull();
    expect(readDraft({ ...scope, schoolId: 20 }, session)).toBeNull();
    expect(readDraft(scope, { ...session, id: 6 })).toBeNull();
    expect(readDraft(scope, { ...session, roster: session.roster.slice(0, 1) })).toEqual([11]);
    expect(window.localStorage.getItem(window.localStorage.key(0)!)).not.toContain("طالب");
  });

  it.each([
    { updated_at: "2026-10-07T07:02:00+03:00" }, { attendance_date: "2026-10-08" },
    { period: { ...period, sequence: 2 } }, { status: "SUBMITTED" as const },
  ])("rejects a draft that no longer matches server state: %j", (change) => {
    writeDraft(scope, session, [11]);
    expect(readDraft(scope, { ...session, ...change })).toBeNull();
    expect(window.localStorage.length).toBe(0);
  });

  it("expires a draft after 24 hours and clears only attendance data on logout/school change", () => {
    const now = Date.now(); vi.spyOn(Date, "now").mockReturnValue(now);
    writeDraft(scope, session, [11]);
    vi.spyOn(Date, "now").mockReturnValue(now + 24 * 60 * 60 * 1000 + 1);
    expect(readDraft(scope, session)).toBeNull();
    writeDraft(scope, session, [11]); window.localStorage.setItem("unrelated", "keep");
    clearAttendanceDrafts(); expect(window.localStorage.getItem("unrelated")).toBe("keep");
    expect(readDraft(scope, session)).toBeNull();
  });

  it("warns and blocks navigation when browser storage is unavailable", async () => {
    mockApi({ "/auth/me/": { body: me }, "/attendance/sessions/5/": { body: session } });
    renderApp("/attendance/section/3?session=5");
    const user = userEvent.setup(); await screen.findByTestId("roster-list");
    vi.spyOn(window.localStorage, "setItem").mockImplementation(() => { throw new DOMException("quota", "QuotaExceededError"); });
    await user.click(absentButton());
    expect(screen.getByTestId("draft-status")).toHaveTextContent("تعذر حفظ");
    await user.click(screen.getByRole("link", { name: "العودة للمتابعة" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("المغادرة ستفقد");
    await user.click(screen.getByRole("button", { name: "البقاء في التحضير" }));
    expect(absentButton()).toHaveAttribute("aria-pressed", "true");
  });

  it("clears a draft when another teacher has already approved the session", async () => {
    writeDraft(scope, session, [11]);
    mockApi({ "/auth/me/": { body: me }, "/attendance/sessions/5/": { body: { ...approved, submitted_by: "معلم التغطية", marks: [] } } });
    renderApp("/attendance/section/3?session=5");
    expect(await screen.findByTestId("submitted-banner")).toHaveTextContent("معلم التغطية");
    expect(screen.getByTestId("live-summary")).toHaveTextContent("غائب 0");
    expect(readDraft(scope, session)).toBeNull();
  });

  it("preserves choices and retry if fetching the winning approval fails", async () => {
    let conflict = false;
    mockApi({
      "/auth/me/": { body: me },
      "/attendance/sessions/5/submit/": () => { conflict = true; return { status: 409, body: { code: "ATTENDANCE_SESSION_ALREADY_SUBMITTED", message: "سبق الاعتماد", details: {} } }; },
      "/attendance/sessions/5/": () => conflict ? { status: 500, body: { code: "TEST_ERROR", message: "تعذر تحديث الجلسة", details: {} } } : { body: session },
    });
    renderApp("/attendance/section/3?session=5");
    const user = userEvent.setup(); await screen.findByTestId("roster-list"); await user.click(absentButton());
    await user.click(screen.getByTestId("submit-attendance"));
    expect(await screen.findByRole("alert")).toHaveTextContent("تعذر تحديث الجلسة");
    expect(absentButton()).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByTestId("submit-attendance")).toBeEnabled();
    expect(readDraft(scope, session)).toEqual([11]);
  });

  it("updates the draft revision after a roster conflict and restores only enrolled students", async () => {
    let changed = false;
    const refreshed = { ...session, updated_at: "2026-10-07T07:30:00+03:00", roster: session.roster.slice(1) };
    mockApi({
      "/auth/me/": { body: me },
      "/attendance/sessions/5/submit/": () => { changed = true; return { status: 409, body: { code: "ATTENDANCE_ROSTER_CHANGED", message: "تغيرت القائمة", details: {} } }; },
      "/attendance/sessions/5/": () => ({ body: changed ? refreshed : session }),
    });
    const user = userEvent.setup(); const first = renderApp("/attendance/section/3?session=5");
    await screen.findByTestId("roster-list"); await user.click(absentButton());
    await user.click(within(screen.getByTestId("roster-student-12")).getByRole("button", { name: "غائب" }));
    await user.click(screen.getByTestId("submit-attendance"));
    await waitFor(() => expect(screen.queryByTestId("roster-student-11")).toBeNull());
    expect(readDraft(scope, refreshed)).toEqual([12]);
    first.unmount(); queryClient.clear(); renderApp("/attendance/section/3?session=5");
    await screen.findByTestId("roster-list");
    expect(screen.getByTestId("live-summary")).toHaveTextContent("غائب 1");
    expect(screen.getByTestId("draft-status")).toHaveTextContent("استُعيدت");
  });

  for (const failure of [
    { name: "HTTP 500", status: 500 }, { name: "HTTP 400", status: 400 },
    { name: "network interruption", exception: () => new TypeError("Failed to fetch") },
    { name: "timeout", exception: () => new DOMException("timeout", "TimeoutError") },
  ]) {
    it(`${failure.name} keeps selections and the saved draft for retry`, async () => {
      mockApi({
        "/auth/me/": { body: me },
        "/attendance/sessions/5/submit/": () => {
          if ("exception" in failure && failure.exception) throw failure.exception();
          return { status: failure.status, body: { code: "TEST_ERROR", message: "تعذر الاعتماد التجريبي", details: {} } };
        },
        "/attendance/sessions/5/": { body: session },
      });
      renderApp("/attendance/section/3?session=5");
      const user = userEvent.setup(); await screen.findByTestId("roster-list"); await user.click(absentButton());
      await user.click(screen.getByTestId("submit-attendance"));
      await screen.findByRole("alert");
      expect(absentButton()).toHaveAttribute("aria-pressed", "true");
      expect(screen.queryByTestId("submitted-banner")).toBeNull();
      expect(screen.getByTestId("submit-attendance")).toBeEnabled();
      expect(readDraft(scope, session)).toEqual([11]);
    });
  }

  it.each([session, { ...approved, id: 6 }, { ...approved, submitted_at: null }])("requires a confirmed approval receipt for this session", async (receipt) => {
    mockApi({ "/auth/me/": { body: me }, "/attendance/sessions/5/submit/": { body: receipt }, "/attendance/sessions/5/": { body: session } });
    renderApp("/attendance/section/3?session=5");
    const user = userEvent.setup(); await screen.findByTestId("roster-list"); await user.click(absentButton());
    await user.click(screen.getByTestId("submit-attendance"));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("لم يؤكد الخادم"));
    expect(screen.queryByTestId("submitted-banner")).toBeNull(); expect(readDraft(scope, session)).toEqual([11]);
  });
});

describe("attendance period binding", () => {
  it("refreshes a stale preview and requires a second explicit start for the new period", async () => {
    const secondPeriod = { ...period, sequence: 2, name: "الحصة الثانية" };
    let transitioned = false;
    const { calls } = mockApi({
      "/auth/me/": { body: me }, "/attendance/sessions/pending/": { body: [] },
      "/attendance/sections/3/preview/": () => ({ body: { ...preview, period: transitioned ? secondPeriod : period } }),
      "/attendance/sessions/start/": () => {
        if (!transitioned) { transitioned = true; return { status: 409, body: { code: "ATTENDANCE_PERIOD_CHANGED", message: "تغيرت الحصة", details: {} } }; }
        return { status: 201, body: { ...session, period: secondPeriod } };
      },
      "/attendance/sessions/5/": { body: { ...session, period: secondPeriod } },
    });
    renderApp("/attendance/section/3");
    const user = userEvent.setup(); await user.click(await screen.findByTestId("start-attendance"));
    await screen.findByTestId("period-changed-notice");
    await waitFor(() => expect(screen.getByTestId("start-attendance")).toBeEnabled());
    expect(calls.filter((call) => call.url.includes("/sessions/start/")).length).toBe(1);
    expect(screen.queryByTestId("roster-list")).toBeNull();
    await user.click(screen.getByTestId("start-attendance")); await screen.findByTestId("roster-list");
    const starts = calls.filter((call) => call.url.includes("/sessions/start/"));
    expect(starts.map((call) => JSON.parse(String(call.init?.body)).expected_period_sequence)).toEqual([1, 2]);
    expect(starts.map((call) => JSON.parse(String(call.init?.body)).expected_date)).toEqual([session.attendance_date, session.attendance_date]);
  });

  it("shows unfinished sessions without a current period and resumes the original period", async () => {
    const { calls } = mockApi({
      "/auth/me/": { body: me }, "/attendance/current-period/": { body: { period: null, date: session.attendance_date } },
      "/attendance/sections/": { body: [section] },
      "/attendance/sessions/pending/": { body: [{ id: session.id, attendance_date: session.attendance_date, section, period, started_at: session.updated_at }] },
      "/attendance/sessions/5/": { body: session },
    });
    renderApp("/workspace");
    const user = userEvent.setup(); const pending = await screen.findByTestId("pending-attendance");
    const link = within(pending).getByRole("link");
    expect(link).toHaveAttribute("href", "/attendance/section/3?session=5");
    await user.click(link); await screen.findByTestId("roster-list");
    expect(screen.getByText("الحصة الأولى")).toBeInTheDocument();
    expect(calls.some((call) => call.url.includes("/preview/") || call.url.includes("/start/"))).toBe(false);
  });

  it("does not display a session for a different section", async () => {
    mockApi({ "/auth/me/": { body: me }, "/attendance/sessions/5/": { body: session } });
    renderApp("/attendance/section/4?session=5");
    expect(await screen.findByRole("alert")).toHaveTextContent("لا تتبع الفصل المحدد");
    expect(screen.queryByTestId("roster-list")).toBeNull();
  });
});
