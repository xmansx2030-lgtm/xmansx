import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { queryClient } from "@/app/queryClient";
import {
  generatePeriodsFromSettings,
  validatePeriods,
} from "@/features/settings/tabs/BellSchedulesTab";
import { buildMe, membership, mockApi } from "@/test/mockApi";
import { renderApp } from "@/test/renderApp";

const SETTINGS_BODY = {
  school: { id: 10, name: "ثانوية الأندلس", slug: "andalus", school_type: "BOYS" as const },
  ministry_school_number: "12345",
  education_stage: "SECONDARY",
  city: "الرياض",
  official_principal_name: "",
  timezone: "Asia/Riyadh",
  logo_url: null,
  attendance_edit_window_minutes: 15,
  unprepared_period_alert_minutes: 25,
  school_day_start_time: "07:00",
  morning_late_grace_minutes: 5,
  staff: { managers: ["خالد المدير"], vice_principals: ["سعد الوكيل"], counselors: [] },
};

function meWithRoles(roles: ("SCHOOL_MANAGER" | "TEACHER" | "VICE_PRINCIPAL" | "COUNSELOR")[]) {
  return buildMe({
    active_school: { id: 10, name: "ثانوية الأندلس", slug: "andalus" },
    roles,
    memberships: [membership(1, 10, "ثانوية الأندلس", roles)],
  });
}

describe("SettingsPage", () => {
  beforeEach(() => {
    queryClient.clear();
    document.cookie = "csrftoken=test-token";
  });

  it("manager sees editable settings with save button and staff list", async () => {
    mockApi({
      "/auth/me/": { body: meWithRoles(["SCHOOL_MANAGER"]) },
      "/school/settings/": { body: SETTINGS_BODY },
    });
    renderApp("/settings");
    expect(await screen.findByLabelText("اسم المدرسة")).toHaveValue("ثانوية الأندلس");
    expect(screen.getByRole("button", { name: "حفظ البيانات" })).toBeInTheDocument();
    expect(screen.getByText("خالد المدير")).toBeInTheDocument();
    expect(screen.getByText("سعد الوكيل")).toBeInTheDocument();
  });

  it("changes a girls school role labels from the school settings", async () => {
    const { calls } = mockApi({
      "/auth/me/": { body: meWithRoles(["SCHOOL_MANAGER"]) },
      "/school/settings/": { body: SETTINGS_BODY },
    });
    renderApp("/settings");
    const user = userEvent.setup();

    await user.selectOptions(await screen.findByLabelText("نوع المدرسة"), "GIRLS");
    expect(screen.getByText("مديرة المدرسة")).toBeInTheDocument();
    expect(screen.getByText("الوكيلات")).toBeInTheDocument();
    expect(screen.getByText("المرشدات الطلابيات")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "حفظ البيانات" }));

    await waitFor(() => {
      const patch = calls.find((call) => call.url.includes("/school/settings/") && call.init?.method === "PATCH");
      expect(JSON.parse(String(patch?.init?.body))).toMatchObject({ school_type: "GIRLS" });
    });
  });

  it("vice principal cannot see or open school settings", async () => {
    mockApi({
      "/auth/me/": { body: meWithRoles(["VICE_PRINCIPAL"]) },
    });
    renderApp("/settings");
    await screen.findByTestId("dashboard-page");
    expect(screen.queryByRole("link", { name: "الإعدادات" })).not.toBeInTheDocument();
    expect(screen.queryByTestId("settings-page")).not.toBeInTheDocument();
  });

  it("يعيد المعلم من رابط الإعدادات إلى مساحة عمله", async () => {
    mockApi({ "/auth/me/": { body: meWithRoles(["TEACHER"]) } });
    renderApp("/settings");
    await screen.findByTestId("active-school-name");
    expect(screen.queryByRole("link", { name: "الإعدادات" })).not.toBeInTheDocument();
    expect(screen.queryByTestId("settings-page")).not.toBeInTheDocument();
  });

  it("counselor cannot see or open school settings", async () => {
    mockApi({ "/auth/me/": { body: meWithRoles(["COUNSELOR"]) } });
    renderApp("/settings");
    await screen.findByTestId("active-school-name");
    expect(screen.queryByRole("link", { name: "الإعدادات" })).not.toBeInTheDocument();
    expect(screen.queryByTestId("settings-page")).not.toBeInTheDocument();
  });

  it("attendance tab validates minutes range client-side", async () => {
    mockApi({
      "/auth/me/": { body: meWithRoles(["SCHOOL_MANAGER"]) },
      "/school/settings/": { body: SETTINGS_BODY },
    });
    renderApp("/settings");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("tab", { name: "سياسات الحضور" }));
    const alertInput = await screen.findByLabelText(/إظهار تنبيه/);
    await user.clear(alertInput);
    await user.type(alertInput, "121");
    await user.click(screen.getByRole("button", { name: "حفظ الإعدادات" }));
    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent("بين 1 و120"),
    );
  });

  it("manager can control morning start and grace time from attendance policies", async () => {
    const { calls } = mockApi({
      "/auth/me/": { body: meWithRoles(["SCHOOL_MANAGER"]) },
      "/school/settings/": { body: SETTINGS_BODY },
    });
    renderApp("/settings?section=attendance");
    const user = userEvent.setup();

    const startTime = await screen.findByLabelText("وقت بداية الدوام");
    const grace = screen.getByLabelText("فترة السماح بعد بداية الدوام");
    expect(screen.getByTestId("morning-policy-preview")).toHaveTextContent("07:05");

    await user.clear(startTime);
    await user.type(startTime, "07:15");
    await user.clear(grace);
    await user.type(grace, "10");
    expect(screen.getByTestId("morning-policy-preview")).toHaveTextContent("07:25");
    await user.click(screen.getByRole("button", { name: "حفظ الإعدادات" }));

    await waitFor(() => {
      const patch = calls.find((call) => call.url.includes("/school/settings/") && call.init?.method === "PATCH");
      expect(JSON.parse(String(patch?.init?.body))).toMatchObject({
        school_day_start_time: "07:15",
        morning_late_grace_minutes: 10,
      });
    });
    expect(await screen.findByRole("status")).toHaveTextContent("تم حفظ سياسات الحضور");
  });

  it("manager can create grades and sections from school settings", async () => {
    const { calls } = mockApi({
      "/auth/me/": { body: meWithRoles(["SCHOOL_MANAGER"]) },
      "/grades/": { body: [] },
      "/sections/": { body: [] },
    });
    renderApp("/settings?section=structure");
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("اسم الصف"), "الثالث المتوسط");
    await user.type(screen.getByLabelText("رمز الصف"), "MID-3");
    await user.click(screen.getByRole("button", { name: "حفظ الصف" }));
    await waitFor(() => expect(calls.some((call) => call.url.endsWith("/grades/") && call.init?.method === "POST")).toBe(true));
  });

  it("يدير الصفوف والفصول بالتعديل والإيقاف والحذف الآمن", async () => {
    const grades = [
      { id: 1, name: "الأول الثانوي", code: "SEC-1", sequence: 1, is_active: true },
      { id: 2, name: "صف فارغ", code: "EMPTY", sequence: 9, is_active: false },
    ];
    const sections = [
      { id: 10, name: "1", code: "A", is_active: true, grade: { id: 1, name: "الأول الثانوي", is_active: true } },
    ];
    const { calls } = mockApi({
      "/auth/me/": { body: meWithRoles(["SCHOOL_MANAGER"]) },
      "/grades/1/": (init) => ({ body: { ...grades[0], ...JSON.parse(String(init?.body ?? "{}")) } }),
      "/grades/2/": (init) => ({ body: { ...grades[1], ...JSON.parse(String(init?.body ?? "{}")) } }),
      "/sections/10/": (init) => ({ body: init?.method === "DELETE" ? {} : { ...sections[0], ...JSON.parse(String(init?.body ?? "{}")) } }),
      "/grades/": { body: grades },
      "/sections/": { body: sections },
    });
    renderApp("/settings?section=structure");
    const user = userEvent.setup();

    expect(await screen.findByText("إدارة الصفوف والفصول من مكان واحد")).toBeInTheDocument();
    expect(screen.getByText("صف نشط").parentElement?.parentElement).toHaveTextContent("1");
    expect(screen.getAllByText("متوقف").length).toBeGreaterThan(0);

    await user.click(screen.getByRole("button", { name: "تعديل الصف الأول الثانوي" }));
    const name = screen.getByLabelText("تعديل اسم الصف");
    await user.clear(name);
    await user.type(name, "الأول الثانوي المطور");
    await user.click(screen.getByRole("button", { name: "حفظ التعديلات" }));
    await waitFor(() => {
      const call = calls.find((item) => item.url.includes("/grades/1/") && item.init?.method === "PATCH");
      expect(JSON.parse(String(call?.init?.body))).toMatchObject({ name: "الأول الثانوي المطور" });
    });

    await user.click(screen.getByRole("button", { name: "إيقاف الصف الأول الثانوي" }));
    expect(await screen.findByText(/سيتم أيضًا إيقاف 1 فصل تابع/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "تأكيد الإيقاف" }));
    await waitFor(() => {
      const call = calls.filter((item) => item.url.includes("/grades/1/") && item.init?.method === "PATCH").at(-1);
      expect(JSON.parse(String(call?.init?.body))).toEqual({ is_active: false });
    });

    await user.click(screen.getByRole("button", { name: "حذف الفصل 1" }));
    expect(await screen.findByText("الحذف النهائي متاح للعناصر غير المستخدمة فقط.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "تأكيد الحذف" }));
    await waitFor(() => expect(calls.some((item) => item.url.includes("/sections/10/") && item.init?.method === "DELETE")).toBe(true));
  });

  it("تحديث توقيت الحصص يبطل قراءات الحصة والمراقبة واللوحة فورًا", async () => {
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");
    const schedule = {
      id: 11,
      name: "الجدول العادي",
      status: "ACTIVE",
      valid_from: null,
      valid_to: null,
      periods: [
        {
          id: 21,
          sequence: 1,
          name: "الحصة الأولى",
          start_time: "07:00",
          end_time: "07:45",
          is_attendance_period: true,
        },
      ],
    };
    mockApi({
      "/auth/me/": { body: meWithRoles(["SCHOOL_MANAGER"]) },
      "/school/bell-schedules/11/periods/": { body: schedule },
      "/school/bell-schedules/": { body: [schedule] },
      "/school/week-days/": { body: { days: [] } },
    });

    renderApp("/settings?section=bell-schedules");
    await screen.findByDisplayValue("الحصة الأولى");
    await userEvent.click(screen.getByRole("button", { name: "حفظ الحصص" }));
    expect(await screen.findByText("تم حفظ الحصص.")).toBeInTheDocument();

    for (const queryKey of [
      ["school", 10, "attendance", "current-period"],
      ["school", 10, "attendance", "monitoring"],
      ["school", 10, "dashboard"],
    ]) {
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey });
    }
  });

  it("يولد الحصص ديناميكيًا مع الفسحة والصلاة كفواصل غير داخلة في التحضير", async () => {
    const schedule = {
      id: 11,
      name: "الجدول العادي",
      status: "ACTIVE",
      valid_from: null,
      valid_to: null,
      periods: [],
    };
    const { calls } = mockApi({
      "/auth/me/": { body: meWithRoles(["SCHOOL_MANAGER"]) },
      "/school/bell-schedules/11/periods/": { body: schedule },
      "/school/bell-schedules/": { body: [schedule] },
      "/school/week-days/": { body: { days: [] } },
    });

    renderApp("/settings?section=bell-schedules");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "توليد الجدول" }));
    expect(await screen.findByLabelText("اسم الفترة 4")).toHaveValue("الفسحة");
    expect(screen.getByLabelText("اسم الفترة 7")).toHaveValue("الصلاة");

    await user.click(screen.getByRole("button", { name: "حفظ الحصص" }));
    await waitFor(() => {
      const call = calls.find(
        (item) => item.url.includes("/school/bell-schedules/11/periods/") && item.init?.method === "PUT",
      );
      const payload = JSON.parse(String(call?.init?.body)) as {
        periods: { name: string; is_attendance_period: boolean }[];
      };
      expect(payload.periods).toHaveLength(9);
      expect(payload.periods.filter((period) => period.is_attendance_period)).toHaveLength(7);
      expect(payload.periods).toContainEqual(
        expect.objectContaining({ name: "الفسحة", is_attendance_period: false }),
      );
      expect(payload.periods).toContainEqual(
        expect.objectContaining({ name: "الصلاة", is_attendance_period: false }),
      );
    });
  });
});

describe("validatePeriods (تحقق مطابق للخادم)", () => {
  const period = (seq: number, name: string, start: string, end: string) => ({
    sequence: seq,
    name,
    start_time: start,
    end_time: end,
    is_attendance_period: true,
  });

  it("accepts a valid non-overlapping schedule", () => {
    expect(
      validatePeriods([
        period(1, "الأولى", "07:00", "07:45"),
        period(2, "الثانية", "07:45", "08:30"),
      ]),
    ).toBeNull();
  });

  it("rejects duplicate sequence", () => {
    expect(
      validatePeriods([
        period(1, "الأولى", "07:00", "07:45"),
        period(1, "مكررة", "07:45", "08:30"),
      ]),
    ).toMatch("تكرار");
  });

  it("rejects end before start", () => {
    expect(validatePeriods([period(1, "مقلوبة", "08:00", "07:00")])).toMatch("بعد بدايتها");
  });

  it("rejects overlapping periods", () => {
    expect(
      validatePeriods([
        period(1, "الأولى", "07:00", "07:45"),
        period(2, "متداخلة", "07:30", "08:15"),
      ]),
    ).toMatch("تداخل");
  });

  it("rejects an unreasonable multi-hour class duration", () => {
    expect(validatePeriods([period(1, "الأولى", "00:00", "23:59")])).toMatch("غير معتادة");
  });

  it("builds a generated school day with recess and prayer breaks", () => {
    const generated = generatePeriodsFromSettings({
      startTime: "07:00",
      periodCount: 6,
      periodMinutes: 40,
      gapMinutes: 5,
      recess: { enabled: true, label: "الفسحة", afterPeriod: 2, duration: 20 },
      prayer: { enabled: true, label: "الصلاة", afterPeriod: 4, duration: 15 },
    });

    expect(generated.map((period) => period.name)).toEqual([
      "الحصة الأولى",
      "الحصة الثانية",
      "الفسحة",
      "الحصة الثالثة",
      "الحصة الرابعة",
      "الصلاة",
      "الحصة الخامسة",
      "الحصة السادسة",
    ]);
    expect(generated.find((period) => period.name === "الفسحة")).toMatchObject({
      start_time: "08:25",
      end_time: "08:45",
      is_attendance_period: false,
    });
    expect(validatePeriods(generated)).toBeNull();
  });
});
