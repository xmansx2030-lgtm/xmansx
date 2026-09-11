import { screen, within } from "@testing-library/react";
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
    excused_absent_periods: 4,
    unexcused_absent_periods: 6,
    excused_full_absence_days: 1,
    unexcused_full_absence_days: 0,
    mixed_full_absence_days: 0,
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

  it("renders header, metrics, and morning lateness", async () => {
    mockApi({
      "/auth/me/": { body: managerMe() },
      "/attendance-profile/": { body: PROFILE },
    });

    renderApp("/students/5/attendance");
    expect(await screen.findByRole("heading", { name: "محمد أحمد" })).toBeInTheDocument();
    expect(screen.getByText("******5678")).toBeInTheDocument();

    // التأخر الصباحي: 1 مرة و13 دقيقة.
    const morningBox = screen.getByText("التأخر عن الدوام الصباحي").parentElement;
    expect(morningBox).toHaveTextContent("1 مرات");
    expect(morningBox).toHaveTextContent("13 دقيقة");
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

  // ---- المرحلة 10: التصنيف الإداري داخل ملف الطالب ----

  it("shows excused/unexcused cards without replacing the totals", async () => {
    mockApi({
      "/auth/me/": { body: managerMe() },
      "/attendance-profile/": { body: PROFILE },
    });

    renderApp("/students/5/attendance");
    await screen.findByRole("heading", { name: "محمد أحمد" });
    // الإجمالي يبقى ظاهرًا (بند 69)
    expect(screen.getByText("غياب كامل").nextSibling).toHaveTextContent("1 يوم");
    expect(screen.getByText("حصص غياب").nextSibling).toHaveTextContent("10 حصة");
    // التصنيف إضافة فوقه
    const metrics = await screen.findByTestId("excuse-metrics");
    expect(within(metrics).getByText("غياب كامل بعذر").nextSibling).toHaveTextContent(
      "1 يوم",
    );
    expect(
      within(metrics).getByText("غياب كامل بدون عذر").nextSibling,
    ).toHaveTextContent("0 يوم");
    expect(within(metrics).getByText("حصص غياب بعذر").nextSibling).toHaveTextContent(
      "4 حصة",
    );
    expect(
      within(metrics).getByText("حصص غياب بدون عذر").nextSibling,
    ).toHaveTextContent("6 حصة");
  });

  it("lists the student's excuses in the excuses tab", async () => {
    mockApi({
      "/auth/me/": { body: managerMe() },
      "/attendance-profile/": { body: PROFILE },
      "/excuses/": {
        body: {
          count: 1,
          next: null,
          previous: null,
          results: [
            {
              id: 7,
              student: {
                id: 5,
                full_name: "محمد أحمد",
                grade_name: "الأول الثانوي",
                section_name: "2",
              },
              status: "APPROVED",
              status_label: "معتمد",
              reason_type: "MEDICAL_REPORT",
              reason_type_label: "تقرير طبي",
              date_from: "2026-08-17",
              date_to: "2026-08-19",
              targets_count: 3,
              active_coverage_count: 17,
              attachments_count: 1,
              recorded_at: "2026-08-19T09:00:00Z",
              recorded_by_name: "وكيل المدرسة",
              approved_by_name: "مدير المدرسة",
            },
          ],
        },
      },
    });

    renderApp("/students/5/attendance");
    const user = userEvent.setup();
    await screen.findByRole("heading", { name: "محمد أحمد" });
    await user.click(screen.getByRole("button", { name: "الأعذار" }));

    const row = await screen.findByTestId("profile-excuse-7");
    expect(row).toHaveTextContent("تقرير طبي");
    expect(row).toHaveTextContent("معتمد");
    expect(row).toHaveTextContent("17 حصة");
    expect(row).toHaveTextContent("مدير المدرسة");
  });

  it("marks day periods as excused/unexcused and offers a quick excuse", async () => {
    mockApi({
      "/auth/me/": { body: managerMe() },
      "/attendance-profile/": { body: PROFILE },
      "/attendance-days/2026-08-19/": {
        body: {
          date: "2026-08-19",
          absence_status: "PARTIAL",
          absence_status_label: "غياب جزئي",
          section: { id: 2, name: "2", grade_name: "الأول الثانوي" },
          absent_periods: 2,
          excused_absent_periods: 1,
          unexcused_absent_periods: 1,
          periods: [
            {
              sequence: 2,
              name: "الحصة 2",
              status: "ABSENT",
              status_label: "غائب",
              excused: true,
            },
            {
              sequence: 4,
              name: "الحصة 4",
              status: "ABSENT",
              status_label: "غائب",
              excused: false,
            },
          ],
        },
      },
      "/attendance-days/": {
        body: {
          count: 1,
          next: null,
          previous: null,
          results: [
            {
              date: "2026-08-19",
              absence_status: "PARTIAL",
              absence_status_label: "غياب جزئي",
              section: { id: 2, name: "2", grade_name: "الأول الثانوي" },
              absent_periods: 2,
              excused_absent_periods: 1,
              unexcused_absent_periods: 1,
            },
          ],
        },
      },
    });

    renderApp("/students/5/attendance");
    const user = userEvent.setup();
    await screen.findByRole("heading", { name: "محمد أحمد" });
    await user.click(screen.getByRole("button", { name: "سجل الأيام" }));
    // التاريخ يعرض بتقويم ar-SA — ننقر عبر testid لا عبر النص المنسق
    await user.click(await screen.findByTestId("day-row-2026-08-19"));

    expect(await screen.findByText(/غائب — بعذر/)).toBeInTheDocument();
    expect(screen.getByText(/غائب — بدون عذر/)).toBeInTheDocument();
    // زر إضافة عذر للحصة غير المعذورة فقط
    expect(screen.getByTestId("period-add-excuse-4")).toBeInTheDocument();
    expect(screen.queryByTestId("period-add-excuse-2")).not.toBeInTheDocument();
    expect(screen.getByTestId("day-add-excuse")).toBeInTheDocument();
  });
});
