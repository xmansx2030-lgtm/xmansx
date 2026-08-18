import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import { queryClient } from "@/app/queryClient";
import { validatePeriods } from "@/features/settings/tabs/BellSchedulesTab";
import { buildMe, membership, mockApi } from "@/test/mockApi";
import { renderApp } from "@/test/renderApp";

const SETTINGS_BODY = {
  school: { id: 10, name: "ثانوية الأندلس", slug: "andalus" },
  ministry_school_number: "12345",
  education_stage: "SECONDARY",
  city: "الرياض",
  official_principal_name: "",
  timezone: "Asia/Riyadh",
  logo_url: null,
  attendance_edit_window_minutes: 15,
  unprepared_period_alert_minutes: 25,
  staff: { managers: ["خالد المدير"], vice_principals: ["سعد الوكيل"], counselors: [] },
};

function meWithRoles(roles: ("SCHOOL_MANAGER" | "TEACHER" | "VICE_PRINCIPAL")[]) {
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

  it("vice principal sees read-only settings (no save button, fields disabled)", async () => {
    mockApi({
      "/auth/me/": { body: meWithRoles(["VICE_PRINCIPAL"]) },
      "/school/settings/": { body: SETTINGS_BODY },
    });
    renderApp("/settings");
    const nameField = await screen.findByLabelText("اسم المدرسة");
    expect(nameField).toBeDisabled();
    expect(screen.queryByRole("button", { name: "حفظ البيانات" })).not.toBeInTheDocument();
  });

  it("teacher is denied the settings screen entirely", async () => {
    mockApi({ "/auth/me/": { body: meWithRoles(["TEACHER"]) } });
    renderApp("/settings");
    expect(
      await screen.findByText("لا تملك صلاحية عرض الإعدادات"),
    ).toBeInTheDocument();
    // ولا يظهر رابط الإعدادات في الترويسة
    expect(screen.queryByRole("link", { name: "الإعدادات" })).not.toBeInTheDocument();
  });

  it("attendance tab validates minutes range client-side", async () => {
    mockApi({
      "/auth/me/": { body: meWithRoles(["SCHOOL_MANAGER"]) },
      "/school/settings/": { body: SETTINGS_BODY },
    });
    renderApp("/settings");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("tab", { name: "إعدادات التحضير" }));
    const alertInput = await screen.findByLabelText(/إظهار تنبيه/);
    await user.clear(alertInput);
    await user.type(alertInput, "121");
    await user.click(screen.getByRole("button", { name: "حفظ الإعدادات" }));
    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent("بين 1 و120"),
    );
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
});
