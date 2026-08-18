import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import { queryClient } from "@/app/queryClient";
import { buildMe, membership, mockApi } from "@/test/mockApi";
import { renderApp } from "@/test/renderApp";

function meWithRoles(roles: ("SCHOOL_MANAGER" | "VICE_PRINCIPAL")[]) {
  return buildMe({
    active_school: { id: 10, name: "ثانوية الأندلس", slug: "andalus" },
    roles,
    memberships: [membership(1, 10, "ثانوية الأندلس", roles)],
  });
}

const INACTIVE_PAGE = {
  count: 2,
  next: null,
  previous: null,
  results: [
    {
      id: 1, full_name: "خريج أول", national_id_masked: "******0001",
      status: "GRADUATED", exit_date: "2026-06-25", exit_reason: "",
      grade: { name: "الثالث الثانوي" }, section: { name: "1" },
    },
    {
      id: 2, full_name: "خريج ثانٍ", national_id_masked: "******0002",
      status: "GRADUATED", exit_date: "2026-06-25", exit_reason: "",
      grade: { name: "الثالث الثانوي" }, section: { name: "2" },
    },
  ],
};

describe("InactiveStudentsPage", () => {
  beforeEach(() => {
    queryClient.clear();
    document.cookie = "csrftoken=test-token";
  });

  it("manager runs full purge flow: select all → preview → type-confirm → progress", async () => {
    let purgeStarted = false;
    mockApi({
      "/auth/me/": { body: meWithRoles(["SCHOOL_MANAGER"]) },
      "/student-purges/preview/": {
        body: {
          confirmation_token: "tok-123",
          summary: {
            students: 2, "القيود الدراسية": 2, "الملفات المخزنة": 0,
            database_records: 4,
          },
          expires_in_seconds: 600,
        },
      },
      "/student-purges/7/": () => ({
        body: {
          id: 7, status: purgeStarted ? "COMPLETED" : "RUNNING", reason: "GRADUATED",
          total_students: 2, processed_students: 2, deleted_students: 2,
          failed_students: 0, db_records_deleted: 4,
          storage_objects_deleted: 0, storage_objects_failed: 0,
        },
      }),
      "/student-purges/": () => {
        purgeStarted = true;
        return {
          status: 202,
          body: {
            id: 7, status: "PENDING", reason: "GRADUATED", total_students: 2,
            processed_students: 0, deleted_students: 0, failed_students: 0,
            db_records_deleted: 0, storage_objects_deleted: 0, storage_objects_failed: 0,
          },
        };
      },
      "/students/inactive/": { body: INACTIVE_PAGE },
    });

    renderApp("/students/inactive");
    const user = userEvent.setup();

    // فلتر الخريجين ثم زر الحذف السريع
    await user.click(await screen.findByRole("tab", { name: "الخريجون" }));
    await screen.findByText("خريج أول");
    await user.click(
      screen.getByRole("button", { name: /حذف جميع الخريجين المعروضين/ }),
    );

    // حوار التأكيد: ملخص خادمي + كتابة إلزامية
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("سيتم حذف بيانات 2 طالبًا نهائيًا");
    expect(screen.getByTestId("purge-summary")).toHaveTextContent("القيود الدراسية: 2");
    const confirmButton = screen.getByRole("button", { name: "حذف نهائي" });
    expect(confirmButton).toBeDisabled();
    await user.type(screen.getByTestId("purge-confirm-input"), "حذف 2 طالبًا");
    expect(confirmButton).toBeEnabled();
    await user.click(confirmButton);

    // شاشة التقدم ثم الاكتمال (polling)
    await waitFor(() =>
      expect(screen.getByTestId("purge-progress")).toHaveTextContent("2 / 2"),
    );
    await waitFor(
      () =>
        expect(screen.getByTestId("purge-progress")).toHaveTextContent(
          "اكتمل الحذف النهائي",
        ),
      { timeout: 5000 },
    );
  });

  it("vice principal sees list without purge controls", async () => {
    mockApi({
      "/auth/me/": { body: meWithRoles(["VICE_PRINCIPAL"]) },
      "/students/inactive/": { body: INACTIVE_PAGE },
    });
    renderApp("/students/inactive");
    expect(await screen.findByText("خريج أول")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /حذف/ }),
    ).not.toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  });

  it("missing-from-noor filter offers classification actions", async () => {
    mockApi({
      "/auth/me/": { body: meWithRoles(["SCHOOL_MANAGER"]) },
      "/students/inactive/": { body: INACTIVE_PAGE },
    });
    renderApp("/students/inactive");
    const user = userEvent.setup();
    await user.click(
      await screen.findByRole("tab", { name: "غير الموجودين في آخر ملف نور" }),
    );
    expect(
      await screen.findByRole("button", { name: "تعيين كمنتقلين" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "تعيين كخريجين" })).toBeInTheDocument();
    // لا زر حذف مباشر في فلتر المفقودين — التصنيف أولًا
    expect(screen.queryByRole("button", { name: /حذف المحددين/ })).not.toBeInTheDocument();
  });
});

describe("StudentsPage bulk graduation", () => {
  beforeEach(() => {
    queryClient.clear();
    document.cookie = "csrftoken=test-token";
  });

  it("manager selects students and graduates them", async () => {
    let graduated: number[] = [];
    mockApi({
      "/auth/me/": { body: meWithRoles(["SCHOOL_MANAGER"]) },
      "/students/bulk-status/": (init) => {
        const parsed = JSON.parse(String(init?.body ?? "{}")) as {
          student_ids: number[];
        };
        graduated = parsed.student_ids;
        return { body: { updated: parsed.student_ids.length, status: "GRADUATED" } };
      },
      "/students/": {
        body: {
          count: 2, next: null, previous: null,
          results: [
            { id: 11, full_name: "طالب أ", national_id_masked: "******0011",
              student_number: null, status: "ACTIVE", guardian_name: "",
              grade: { id: 1, name: "الثالث الثانوي" }, section: { id: 1, name: "1" } },
            { id: 12, full_name: "طالب ب", national_id_masked: "******0012",
              student_number: null, status: "ACTIVE", guardian_name: "",
              grade: { id: 1, name: "الثالث الثانوي" }, section: { id: 1, name: "1" } },
          ],
        },
      },
      "/grades/": { body: [] },
      "/sections/": { body: [] },
    });

    renderApp("/students");
    const user = userEvent.setup();
    await screen.findByText("طالب أ");
    await user.click(screen.getByRole("checkbox", { name: "تحديد الكل" }));
    await user.click(screen.getByRole("button", { name: "تعيين المحددين كخريجين" }));
    await waitFor(() => expect(graduated).toEqual([11, 12]));
  });
});
