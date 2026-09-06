import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

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

const SUMMARY = {
  date: "2026-08-19",
  arrived_total: 420,
  on_time: 395,
  late: 25,
  late_minutes_total: 312,
  unmatched_events: 3,
  devices_total: 2,
  devices_offline: 1,
};

const LATE_LIST = {
  date: "2026-08-19",
  total_late: 1,
  students: [
    {
      arrival_id: 77,
      student_id: 5,
      full_name: "محمد أحمد",
      grade_name: "الأول الثانوي",
      section_name: "2",
      arrival_time: "07:16",
      raw_late_minutes: 16,
      counted_late_minutes: 11,
      source: "BIOMETRIC",
    },
  ],
  page: 1,
  page_size: 25,
};

const SEARCH = {
  count: 1,
  next: null,
  previous: null,
  results: [{ id: 5, full_name: "محمد أحمد", national_id_masked: "******5678" }],
};

function parseBody(init?: RequestInit): Record<string, unknown> {
  return JSON.parse(String(init?.body ?? "{}")) as Record<string, unknown>;
}

describe("morning attendance UI (Phase 8.5)", () => {
  beforeEach(() => {
    queryClient.clear();
    document.cookie = "csrftoken=test-token";
  });

  it("shows today KPIs and never an absent counter from biometrics", async () => {
    mockApi({
      "/auth/me/": { body: roleMe(["VICE_PRINCIPAL"]) },
      "/morning/summary/": { body: SUMMARY },
    });

    renderApp("/morning");
    const kpis = await screen.findByTestId("morning-kpis");
    expect(within(kpis).getByTestId("kpi-arrived")).toHaveTextContent("420");
    expect(within(kpis).getByTestId("kpi-late")).toHaveTextContent("25");
    expect(within(kpis).getByTestId("kpi-unmatched")).toHaveTextContent("3");
    expect(within(kpis).getByTestId("kpi-devices-offline")).toHaveTextContent("1");
    // قاعدة صلبة: لا بطاقة «غائبون» من البصمة
    expect(within(kpis).queryByText(/غائب/)).not.toBeInTheDocument();
    expect(screen.getByText(/لا يعني غياب الطالب/)).toBeInTheDocument();
  });

  it("records a manual arrival with server-computed lateness", async () => {
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");
    const { calls } = mockApi({
      "/auth/me/": { body: roleMe(["VICE_PRINCIPAL"]) },
      "/morning/summary/": { body: SUMMARY },
      "/students/search/": { body: SEARCH },
      "/morning/arrivals/": {
        status: 201,
        body: {
          id: 91, student_id: 5, attendance_date: "2026-08-19",
          arrival_time: "07:20", status: "LATE",
          raw_late_minutes: 20, counted_late_minutes: 15, source: "MANUAL",
        },
      },
    });

    renderApp("/morning");
    const user = userEvent.setup();
    await screen.findByTestId("morning-kpis");
    await user.type(screen.getByLabelText("بحث عن طالب"), "محمد");
    await user.click(await screen.findByTestId("pick-student-5"));
    await user.type(screen.getByLabelText("سبب التسجيل اليدوي"), "دخل من البوابة الخلفية");
    await user.click(screen.getByTestId("save-manual-arrival"));

    expect(await screen.findByTestId("manual-arrival-result")).toHaveTextContent(
      "متأخر 15 دقيقة",
    );
    const post = calls.find(
      (c) => c.url.includes("/morning/arrivals/") && c.init?.method === "POST",
    );
    const body = parseBody(post?.init);
    expect(body.student_id).toBe(5);
    expect(body).not.toHaveProperty("late_minutes"); // الحساب خادمي حصرًا
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: ["school", 10, "dashboard"],
    });
  });

  it("lists late students by date and corrects an arrival with reason", async () => {
    const { calls } = mockApi({
      "/auth/me/": { body: roleMe(["VICE_PRINCIPAL"]) },
      "/morning/summary/": { body: SUMMARY },
      "/morning/late/": { body: LATE_LIST },
      "/morning/arrivals/77/correct/": {
        body: {
          id: 77, student_id: 5, attendance_date: "2026-08-19",
          arrival_time: "07:05", status: "ON_TIME",
          raw_late_minutes: 5, counted_late_minutes: 0, source: "MANUAL",
        },
      },
    });

    renderApp("/morning");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("tab", { name: "المتأخرون" }));
    const row = await screen.findByTestId("late-row-5");
    expect(row).toHaveTextContent("متأخر 11 دقيقة");
    expect(row).toHaveTextContent("البصمة");

    await user.click(screen.getByTestId("correct-5"));
    await user.clear(screen.getByTestId("correct-time"));
    await user.type(screen.getByTestId("correct-time"), "07:05");
    await user.type(screen.getByTestId("correct-reason"), "البصمة سجلت متأخرة");
    await user.click(screen.getByTestId("save-correction"));

    await waitFor(() => {
      const post = calls.find((c) => c.url.includes("/correct/"));
      expect(parseBody(post?.init)).toEqual({
        arrival_time: "07:05",
        reason: "البصمة سجلت متأخرة",
      });
    });
  });

  it("shows student morning late history with minutes-to-hours display", async () => {
    mockApi({
      "/auth/me/": { body: roleMe(["VICE_PRINCIPAL"]) },
      "/morning/summary/": { body: SUMMARY },
      "/students/search/": { body: SEARCH },
      "/morning/students/5/history/": {
        body: {
          student_id: 5, full_name: "محمد أحمد",
          late_count: 8, total_late_minutes: 137,
          entries: [
            { date: "2026-08-18", arrival_time: "07:20",
              raw_late_minutes: 20, counted_late_minutes: 15, source: "BIOMETRIC" },
          ],
        },
      },
    });

    renderApp("/morning");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("tab", { name: "سجل طالب" }));
    await user.type(screen.getByLabelText("بحث عن طالب"), "محمد");
    await user.click(await screen.findByTestId("pick-student-5"));

    const summary = await screen.findByTestId("history-summary");
    expect(summary).toHaveTextContent("مرات التأخر عن الدوام: 8");
    expect(summary).toHaveTextContent("137");
    expect(summary).toHaveTextContent("2 ساعة و17 دقيقة"); // الدقائق تخزن والعرض يحول
    expect(screen.getByTestId("history-entries")).toHaveTextContent("خام 20 د · محتسب 15 د");
  });

  it("teacher cannot see morning or devices navigation", async () => {
    mockApi({
      "/auth/me/": { body: roleMe(["TEACHER"]) },
      "/attendance/current-period/": { body: { period: null, date: "2026-08-19" } },
      "/attendance/sections/": { body: [] },
    });

    renderApp("/");
    await screen.findByTestId("active-school-name");
    expect(screen.queryByRole("link", { name: "الحضور الصباحي" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "أجهزة الحضور" })).not.toBeInTheDocument();
  });
});

describe("devices settings UI (Phase 8.5)", () => {
  beforeEach(() => {
    queryClient.clear();
    document.cookie = "csrftoken=test-token";
  });

  it("creates a bridge and shows the credential exactly once", async () => {
    mockApi({
      "/auth/me/": { body: roleMe(["SCHOOL_MANAGER"]) },
      "/device-bridges/": (init) =>
        init?.method === "POST"
          ? {
              status: 201,
              body: {
                bridge: {
                  id: 1, installation_name: "جسر الاستقبال",
                  status: "ACTIVE", last_seen_at: null, is_online: false,
                },
                credential: "brg_abc123_secret-value-once",
              },
            }
          : { body: [] },
      "/devices/": { body: [] },
      "/device-identities/": { body: [] },
    });

    renderApp("/devices");
    const user = userEvent.setup();
    await screen.findByTestId("bridges-list");
    await user.type(screen.getByLabelText("اسم الجسر"), "جسر الاستقبال");
    await user.click(screen.getByTestId("add-bridge"));

    const box = await screen.findByTestId("bridge-credential-box");
    expect(box).toHaveTextContent("brg_abc123_secret-value-once");
    expect(box).toHaveTextContent("يظهر مرة واحدة");
  });

  it("lists devices with status and requests a connection test", async () => {
    const device = {
      id: 4, name: "بوابة رئيسية", vendor: "SIMULATOR", model: "", serial_number: "",
      connection_type: "TCP", local_ip: "192.168.1.50", local_port: null,
      status: "ONLINE", last_seen_at: "2026-08-19T07:00:00Z",
      last_successful_sync_at: null, is_active: true, unmatched_events: 2,
      test_result: { ok: true, detail: "simulator ready" },
    };
    const { calls } = mockApi({
      "/auth/me/": { body: roleMe(["SCHOOL_MANAGER"]) },
      "/device-bridges/": { body: [] },
      "/devices/4/test-connection/": { body: device },
      "/devices/": { body: [device] },
      "/device-identities/": { body: [] },
    });

    renderApp("/devices");
    const user = userEvent.setup();
    const row = await screen.findByTestId("device-4");
    expect(within(row).getByTestId("device-status-4")).toHaveTextContent("متصل");
    expect(row).toHaveTextContent("2 حدثًا غير مطابق");
    await user.click(within(row).getByTestId("test-device-4"));
    await waitFor(() => {
      expect(
        calls.some((c) => c.url.includes("/test-connection/") && c.init?.method === "POST"),
      ).toBe(true);
    });
  });

  it("maps an unmatched device user to a student", async () => {
    const identity = {
      id: 9, device_id: 4, device_name: "بوابة رئيسية",
      external_user_id: "1042", display_name: "",
      status: "UNMATCHED" as const, student_id: null, student_name: null,
    };
    const { calls } = mockApi({
      "/auth/me/": { body: roleMe(["SCHOOL_MANAGER"]) },
      "/device-bridges/": { body: [] },
      "/devices/": { body: [] },
      "/device-identities/9/map/": {
        body: { ...identity, status: "MATCHED", student_id: 5, student_name: "محمد أحمد" },
      },
      "/device-identities/": { body: [identity] },
      "/students/search/": { body: SEARCH },
    });

    renderApp("/devices");
    const user = userEvent.setup();
    await user.click(await screen.findByTestId("map-identity-9"));
    await user.type(screen.getByLabelText("بحث عن طالب"), "محمد");
    await user.click(await screen.findByTestId("pick-student-5"));

    await waitFor(() => {
      const post = calls.find((c) => c.url.includes("/device-identities/9/map/"));
      expect(parseBody(post?.init)).toEqual({ student_id: 5 });
    });
  });

  it("roster sync page renders devices and analyzes on demand", async () => {
    vi.stubGlobal("confirm", vi.fn().mockReturnValue(true));
    const { calls } = mockApi({
      "/auth/me/": { body: roleMe(["SCHOOL_MANAGER"]) },
      "/devices/1/roster-sync/analyze/": {
        status: 202,
        body: {
          id: 3, device_id: 1, device_name: "بوابة", status: "ANALYZING",
          roster_version: "", device_roster_version: "",
          matched_count: 0, create_count: 0, update_count: 0,
          delete_count: 0, conflict_count: 0, student_count: 0,
          device_user_count: 0, ready_at: null, approved_at: null,
        },
      },
      "/device-roster-syncs/3/items/": { body: [] },
      "/device-roster-syncs/3/": {
        body: {
          id: 3, device_id: 1, device_name: "بوابة", status: "READY_FOR_REVIEW",
          roster_version: "v1", device_roster_version: "d1",
          matched_count: 5, create_count: 2, update_count: 1,
          delete_count: 0, conflict_count: 1, student_count: 8,
          device_user_count: 7, ready_at: "2026-08-19T07:00:00Z", approved_at: null,
        },
      },
      "/devices/": {
        body: [{ id: 1, name: "بوابة", vendor: "SIMULATOR", model: "", status: "ONLINE", is_active: true }],
      },
    });

    renderApp("/devices/roster-sync");
    const user = userEvent.setup();
    await screen.findByRole("heading", { name: "مزامنة طلاب أجهزة الحضور" });
    const select = screen.getByRole("combobox");
    await user.selectOptions(select, "1");
    await user.click(screen.getByRole("button", { name: /فحص/ }));
    await waitFor(() => {
      expect(calls.some((c) => c.url.includes("/roster-sync/analyze/"))).toBe(true);
    });
  });
});
