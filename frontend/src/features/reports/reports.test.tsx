import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import { queryClient } from "@/app/queryClient";
import { buildMe, membership, mockApi } from "@/test/mockApi";
import { renderApp } from "@/test/renderApp";

const me = buildMe({
  name: "سعد الوكيل",
  active_school: {
    id: 10,
    name: "ثانوية الأندلس",
    slug: "andalus",
    school_type: "BOYS",
  },
  roles: ["VICE_PRINCIPAL"],
  memberships: [membership(1, 10, "ثانوية الأندلس", ["VICE_PRINCIPAL"])],
});

const range = {
  range: { from_date: "2026-08-01", to_date: "2026-08-30", days: 30, preset: "LAST_30_DAYS" },
  scope: { grade_id: null, section_id: null },
};

describe("school reports", () => {
  beforeEach(() => queryClient.clear());

  it("يعرض للوكيل تقارير الغياب والتأخر والإحالات دون المخالفات", async () => {
    mockApi({
      "/auth/me/": { body: me },
      "/attendance/sections/": {
        body: [{ id: 20, name: "أ", grade_id: 2, grade_name: "الأول", students_count: 30 }],
      },
      "/reports/absence/": {
        body: {
          context: range,
          summary: {
            students: 1,
            student_days: 2,
            full_absence_days: 2,
            partial_absence_days: 0,
            excused_absent_periods: 1,
            unexcused_absent_periods: 13,
            incomplete_days: 0,
          },
          results: [{
            student_id: 7,
            full_name: "محمد أحمد",
            grade_name: "الأول",
            section_name: "أ",
            full_absence_days: 2,
            partial_absence_days: 0,
            absent_periods: 14,
            excused_absent_periods: 1,
            unexcused_absent_periods: 13,
            incomplete_days: 0,
          }],
          count: 1,
          page: 1,
          page_size: 25,
        },
      },
      "/reports/lateness/": {
        body: {
          context: range,
          summary: { students: 1, morning_occurrences: 3, morning_minutes: 22 },
          results: [], count: 0, page: 1, page_size: 25,
        },
      },
    });
    renderApp("/reports");

    expect(await screen.findByRole("heading", { name: "مركز التقارير" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "التقارير" })).toBeInTheDocument();
    expect(await screen.findByText("محمد أحمد")).toBeInTheDocument();
    expect(screen.queryByText("المخالفات")).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("tab", { name: "التأخر" }));
    expect(await screen.findByText("مرات التأخر الصباحي")).toBeInTheDocument();
    expect(screen.getByText("22")).toBeInTheDocument();
  });
});
