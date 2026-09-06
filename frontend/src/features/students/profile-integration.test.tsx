/** تكامل م12+م13 في الواجهة — ملف الطالب الموحد والتنقل حسب الدور.
 *
 * يمنع أن يبتلع دمج لاحق تبويبًا من مرحلة سابقة (البنود 28-29 و43-46).
 */

import { screen } from "@testing-library/react";
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
    period_late_occurrences: 0,
    period_late_minutes: 0,
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

const PROFILE_TABS = [
  "الملخص",
  "سجل الأيام",
  "غياب الحصص",
  "تأخر الحصص",
  "الحضور الصباحي",
  "الاستئذانات",
  "الأعذار",
  "الإنذارات",
  "الإجراءات",
  "المستندات",
  "الإحالات",
];

describe("unified student profile (phase 12 + 13)", () => {
  beforeEach(() => {
    queryClient.clear();
    document.cookie = "csrftoken=test-token";
  });

  it("keeps every module tab after the merge", async () => {
    mockApi({
      "/auth/me/": { body: roleMe(["VICE_PRINCIPAL"]) },
      "/attendance-profile/": { body: PROFILE },
    });

    renderApp("/students/5/attendance");
    await screen.findByRole("heading", { name: "محمد أحمد" });
    const header = screen.getByTestId("student-profile-header");
    expect(header).toHaveTextContent("محمد أحمد");
    expect(header).toHaveTextContent("رقم الطالب: 1001");
    expect(header).toHaveTextContent("الهوية: ******5678");
    const labels = screen.getAllByRole("button").map((button) => button.textContent);
    for (const tab of PROFILE_TABS) {
      expect(labels).toContain(tab);
    }
  });

  it("shows the student's leave history inside the unified record", async () => {
    mockApi({
      "/auth/me/": { body: roleMe(["VICE_PRINCIPAL"]) },
      "/attendance-profile/": { body: PROFILE },
      "/student-leaves/": {
        body: {
          count: 1,
          next: null,
          previous: null,
          summary: { total: 1, active: 1, cancelled: 0 },
          results: [{
            id: 81,
            student: { id: 5, full_name: "محمد أحمد", student_number: "1001", national_id_masked: "******5678" },
            leave_date: "2026-09-06",
            leave_time: "10:35",
            weekday_label: "الأحد",
            reason: "موعد طبي لدى المستشفى",
            grade_name: "الأول الثانوي",
            section_name: "2",
            status: "ACTIVE",
            status_label: "ساري",
            recorded_by_name: "سعد الوكيل",
            created_at: "2026-09-06T10:30:00+03:00",
            cancelled_by_name: null,
            cancelled_at: null,
            cancellation_reason: "",
          }],
        },
      },
    });
    renderApp("/students/5/attendance");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "الاستئذانات" }));
    const tab = await screen.findByTestId("student-leaves-tab");
    expect(tab).toHaveTextContent("موعد طبي لدى المستشفى");
    expect(tab).toHaveTextContent("وقت الخروج 10:35");
    expect(tab).toHaveTextContent("سعد الوكيل");
  });

  it("shows the counselor the read-only tabs without an admin link set", async () => {
    mockApi({
      "/auth/me/": { body: roleMe(["COUNSELOR"]) },
      "/attendance-profile/": { body: PROFILE },
    });

    renderApp("/students/5/attendance");
    await screen.findByRole("heading", { name: "محمد أحمد" });
    const labels = screen.getAllByRole("button").map((button) => button.textContent);
    expect(labels).toContain("الإجراءات");
    expect(labels).toContain("المستندات");
    expect(labels).toContain("الإحالات");
    // سجل التعديلات للمدير/الوكيل فقط — لم يتغير بالدمج
    expect(labels).not.toContain("سجل التعديلات");
  });
});

describe("navigation after the merge", () => {
  beforeEach(() => {
    queryClient.clear();
    document.cookie = "csrftoken=test-token";
  });

  it("vice principal sees warnings and referrals, not the teacher inbox", async () => {
    mockApi({ "/auth/me/": { body: roleMe(["VICE_PRINCIPAL"]) } });
    renderApp("/");
    expect(await screen.findByRole("link", { name: "الإحالات" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "الإنذارات" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "الاستئذانات" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "إحالاتي" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "مزامنة أجهزة الطلاب" })).not.toBeInTheDocument();
  });

  it("teacher sees only his own referrals, no official documents or admin pages", async () => {
    mockApi({ "/auth/me/": { body: roleMe(["TEACHER"]) } });
    renderApp("/");
    expect(await screen.findByRole("link", { name: "إحالاتي" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "الإحالات" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "الإنذارات" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "الأعذار" })).not.toBeInTheDocument();
  });

  it("counselor sees the referrals inbox", async () => {
    mockApi({ "/auth/me/": { body: roleMe(["COUNSELOR"]) } });
    renderApp("/");
    expect(await screen.findByRole("link", { name: "الإحالات" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "إحالاتي" })).not.toBeInTheDocument();
  });
});
