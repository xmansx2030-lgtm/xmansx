import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import { queryClient } from "@/app/queryClient";
import { buildMe, membership, mockApi } from "@/test/mockApi";
import { renderApp } from "@/test/renderApp";

function managerMe() {
  return buildMe({
    active_school: { id: 10, name: "ثانوية الأندلس", slug: "andalus" },
    roles: ["SCHOOL_MANAGER"],
    memberships: [membership(1, 10, "ثانوية الأندلس", ["SCHOOL_MANAGER"])],
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
    full_absence_days: 1,
    partial_absence_days: 2,
    undetermined_days: 1,
    absent_periods: 10,
    period_late_occurrences: 1,
    period_late_minutes: 8,
  },
  morning_attendance: {
    status: "AVAILABLE",
    morning_late_occurrences: 1,
    morning_late_minutes: 13,
  },
};

describe("student attendance profile (Phase 9)", () => {
  beforeEach(() => {
    queryClient.clear();
    document.cookie = "csrftoken=test-token";
  });

  it("renders header, metrics, and keeps morning late separate from period late", async () => {
    mockApi({
      "/auth/me/": { body: managerMe() },
      "/attendance-profile/": { body: PROFILE },
    });

    renderApp("/students/5/attendance");
    expect(await screen.findByRole("heading", { name: "محمد أحمد" })).toBeInTheDocument();
    expect(screen.getByText("******5678")).toBeInTheDocument();

    // تأخر الحصص: 1 مرة و8 دقائق — عداد مستقل
    expect(screen.getByText("تأخر عن الحصص").nextSibling).toHaveTextContent("1 مرة");
    expect(screen.getByText("إجمالي التأخر").nextSibling).toHaveTextContent("8 دقيقة");
    // التأخر الصباحي: 1 مرة و13 دقيقة — صندوق منفصل، لا 2/21 موحدة
    const morningBox = screen.getByText("التأخر عن الدوام الصباحي").parentElement;
    expect(morningBox).toHaveTextContent("1 مرات");
    expect(morningBox).toHaveTextContent("13 دقيقة");
    expect(document.body.textContent).not.toContain("21 دقيقة");
    // تحذير الأيام غير المكتملة
    expect(screen.getByRole("status")).toHaveTextContent("لم تكتمل فيها بيانات التحضير");
  });

  it("shows NOT_AVAILABLE morning state without breaking the profile", async () => {
    mockApi({
      "/auth/me/": { body: managerMe() },
      "/attendance-profile/": {
        body: {
          ...PROFILE,
          morning_attendance: { status: "NOT_AVAILABLE" },
        },
      },
    });

    renderApp("/students/5/attendance");
    await screen.findByRole("heading", { name: "محمد أحمد" });
    expect(
      screen.getByText("التأخر الصباحي: بيانات الحضور الصباحي غير متاحة."),
    ).toBeInTheDocument();
  });

  it("morning tab lists arrivals from SchoolArrival history", async () => {
    mockApi({
      "/auth/me/": { body: managerMe() },
      "/morning-attendance/": {
        body: [
          {
            date: "2026-08-19",
            arrival_time: "2026-08-19T07:18:00+03:00",
            status: "LATE",
            raw_late_minutes: 18,
            counted_late_minutes: 13,
            source: "BIOMETRIC",
          },
        ],
      },
      "/attendance-profile/": { body: PROFILE },
    });

    renderApp("/students/5/attendance");
    const user = userEvent.setup();
    await screen.findByRole("heading", { name: "محمد أحمد" });
    await user.click(screen.getByRole("button", { name: "الحضور الصباحي" }));
    expect(await screen.findByText("جهاز")).toBeInTheDocument();
    const table = screen.getByRole("table");
    expect(table).toHaveTextContent("13 دقيقة");
    expect(table).toHaveTextContent("متأخر");
  });
});
