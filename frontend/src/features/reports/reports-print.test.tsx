import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { queryClient } from "@/app/queryClient";
import type { ReferralRow } from "@/features/referrals/api";
import type { AbsenceRow, LatenessRow, ReportResponse } from "@/features/reports/api";
import { buildMe, membership, mockApi } from "@/test/mockApi";
import { renderApp } from "@/test/renderApp";

type ReportKind = "absence" | "lateness" | "referrals";
type ReportRow = AbsenceRow | LatenessRow | ReferralRow;

const RESULT_COUNT = 151;
const FROM_DATE = "2026-08-01";
const TO_DATE = "2026-08-30";
const PRINT_LOADING = "جارٍ إعداد جميع النتائج للطباعة...";
const PRINT_BUTTONS = ["طباعة واضحة", "طباعة التقرير النشط"] as const;
const TAB_LABELS: Record<ReportKind, string> = {
  absence: "الغياب", lateness: "التأخر", referrals: "الإحالات للمرشد",
};

const me = buildMe({
  name: "سعد الوكيل",
  active_school: { id: 10, name: "ثانوية الأندلس", slug: "andalus", school_type: "BOYS" },
  roles: ["VICE_PRINCIPAL"],
  memberships: [membership(1, 10, "ثانوية الأندلس", ["VICE_PRINCIPAL"])],
});

function studentName(kind: ReportKind, index: number) {
  return `طالب ${kind} ${String(index + 1).padStart(3, "0")}`;
}

function reportRows(kind: ReportKind): ReportRow[] {
  return Array.from({ length: RESULT_COUNT }, (_, index) => {
    const student = {
      student_id: index + 1, full_name: studentName(kind, index),
      grade_name: "الأول", section_name: "أ",
    };
    if (kind === "absence") {
      return {
        ...student, guardian_mobile: "0550000001", full_absence_days: 2,
        partial_absence_days: 1, absent_periods: 8, excused_absent_periods: 3,
        unexcused_absent_periods: 5, incomplete_days: 0,
      };
    }
    if (kind === "lateness") {
      return { ...student, morning_occurrences: 3, morning_minutes: 22 };
    }
    return {
      id: index + 1000,
      student: { id: student.student_id, full_name: student.full_name, grade_name: "الأول", section_name: "أ" },
      source_type: "TEACHER", source_type_label: "معلم", category: "ATTENDANCE",
      category_label: "المواظبة", reason_code: "REPEATED_ABSENCE", reason_label: "غياب متكرر",
      status: "REFERRED", status_label: "محوّلة للمرشد", priority: "HIGH", priority_label: "عاجلة",
      created_at: "2026-08-25T08:00:00Z", created_by_name: "معلم الطالب",
      assigned_vice_principal_id: 1, assigned_vice_principal_name: "سعد الوكيل",
      assigned_counselor_id: 4, assigned_counselor_name: "أحمد المرشد", counseling_case_id: null,
    } satisfies ReferralRow;
  });
}

function reportPayload(kind: ReportKind, params = new URLSearchParams()): ReportResponse<unknown, ReportRow> {
  const rows = reportRows(kind).filter((row) => !params.has("student") || (
    "student" in row ? row.student.id : row.student_id
  ) === Number(params.get("student")));
  const count = rows.length;
  const all = params.get("_export_all") === "1";
  const page = all ? 1 : Number(params.get("page") ?? 1);
  const summary = kind === "absence"
    ? { students: count, student_days: count * 3, full_absence_days: count * 2, partial_absence_days: count, excused_absent_periods: count * 3, unexcused_absent_periods: count * 5, incomplete_days: 0 }
    : kind === "lateness"
      ? { students: count, morning_occurrences: count * 3, morning_minutes: count * 22 }
      : { total: count, new: 0, under_vice_review: 0, referred: count, acknowledged: 0, closed: 0, unassigned: 0, high_priority: count };
  return {
    context: {
      range: { from_date: FROM_DATE, to_date: TO_DATE, days: 30, preset: all ? "CUSTOM" : "LAST_30_DAYS" },
      scope: { grade_id: params.has("grade") ? Number(params.get("grade")) : null, section_id: params.has("section") ? Number(params.get("section")) : null },
    },
    summary, results: all ? rows : rows.slice((page - 1) * 25, page * 25),
    count, page, page_size: all ? count : 25,
  };
}

function setupReports() {
  let requestUrl = "";
  const routes = {
    "/auth/me/": { body: me },
    "/attendance/sections/": { body: [{ id: 20, name: "أ", grade_id: 2, grade_name: "الأول", students_count: 151 }] },
    "/students/": { body: { count: 1, results: [{ id: 77, full_name: "الطالب المحدد", grade: { id: 2, name: "الأول" }, section: { id: 20, name: "أ" }, status: "ACTIVE" }] } },
    "/referrals/options/": { body: { categories: [{ value: "ATTENDANCE", label: "المواظبة", reasons: [{ value: "REPEATED_ABSENCE", label: "غياب متكرر" }] }] } },
    "/referrals/counselors/": { body: { counselors: [{ id: 4, name: "أحمد المرشد" }] } },
    ...Object.fromEntries((["absence", "lateness", "referrals"] as const).map((kind) => [
      `/reports/${kind}/`, () => ({ body: reportPayload(kind, new URL(requestUrl, "http://localhost").searchParams) }),
    ])),
  };
  const api = mockApi(routes);
  const respond = api.fetchMock.getMockImplementation()!;
  api.fetchMock.mockImplementation(async (input, init) => {
    requestUrl = String(input);
    return respond(input, init);
  });
  return api;
}

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function holdPrintRequest(api: ReturnType<typeof setupReports>) {
  const respond = api.fetchMock.getMockImplementation()!;
  let resolveResponse: ((response: Response) => void) | undefined;
  let request: { url: string; init?: RequestInit } | undefined;
  api.fetchMock.mockImplementation(async (input, init) => {
    if (String(input).includes("_export_all=1")) {
      request = { url: String(input), init };
      api.calls.push(request);
      return new Promise<Response>((resolve) => { resolveResponse = resolve; });
    }
    return respond(input, init);
  });
  return {
    getRequest: () => request,
    resolve: async (body: unknown, status = 200) => {
      await act(async () => { resolveResponse!(jsonResponse(body, status)); });
    },
  };
}

async function openReport(kind: ReportKind) {
  await screen.findByText(studentName("absence", 0));
  if (kind !== "absence") await userEvent.click(screen.getByRole("tab", { name: TAB_LABELS[kind] }));
  await screen.findByText(studentName(kind, 0));
}

async function setReportFilters(kind: ReportKind) {
  const user = userEvent.setup();
  await user.selectOptions(screen.getByLabelText("الصف"), "2");
  await user.selectOptions(screen.getByLabelText("الفصل"), "20");
  if (kind === "absence") {
    await user.selectOptions(screen.getByLabelText("نوع الغياب"), "PARTIAL");
    await user.selectOptions(screen.getByLabelText("حالة العذر"), "MIXED");
    return { absence_type: "PARTIAL", excuse_type: "MIXED" };
  }
  if (kind === "lateness") {
    fireEvent.change(screen.getByLabelText("الحد الأدنى للمرات"), { target: { value: "2" } });
    fireEvent.change(screen.getByLabelText("الحد الأدنى للدقائق"), { target: { value: "10" } });
    return { min_occurrences: "2", min_minutes: "10" };
  }
  await user.selectOptions(screen.getByLabelText("الحالة"), "OPEN");
  await user.selectOptions(screen.getByLabelText("الأولوية"), "HIGH");
  await user.selectOptions(screen.getByLabelText("الفئة"), "ATTENDANCE");
  await user.selectOptions(screen.getByLabelText("السبب"), "REPEATED_ABSENCE");
  await user.selectOptions(screen.getByLabelText("المُحيل"), "TEACHER");
  await user.selectOptions(screen.getByLabelText("المرشد"), "4");
  return { status: "OPEN", priority: "HIGH", category: "ATTENDANCE", reason_code: "REPEATED_ABSENCE", source_type: "TEACHER", counselor: "4" };
}

describe("printing all filtered report results", () => {
  beforeEach(() => queryClient.clear());
  afterEach(() => vi.restoreAllMocks());

  it.each((["absence", "lateness", "referrals"] as const).flatMap((kind) => PRINT_BUTTONS.map((button) => ({ kind, button }))))(
    "prints all 151 $kind results from page 2 using $button and retains every active filter",
    async ({ kind, button }) => {
      const api = setupReports();
      renderApp("/reports");
      await openReport(kind);
      const extra = await setReportFilters(kind);
      await userEvent.click(await screen.findByRole("button", { name: "التالي" }));
      await screen.findByText(studentName(kind, 25));
      expect(screen.getByText("صفحة 2 من 7")).toBeInTheDocument();
      expect(screen.queryByText(studentName(kind, 0))).not.toBeInTheDocument();
      expect(screen.queryByText(studentName(kind, RESULT_COUNT - 1))).not.toBeInTheDocument();

      let printedCount = 0;
      let printedText = "";
      let printedFilters = "";
      const print = vi.spyOn(window, "print").mockImplementation(() => {
        const snapshot = document.querySelector('[data-testid="report-print-table"]');
        printedCount = snapshot?.querySelectorAll("tbody tr").length ?? 0;
        printedText = snapshot?.textContent ?? "";
        printedFilters = screen.getByTestId("report-filter-summary").textContent ?? "";
      });
      await userEvent.click(screen.getByRole("button", { name: button }));
      await waitFor(() => expect(print).toHaveBeenCalledOnce());

      expect(printedCount).toBe(RESULT_COUNT);
      expect(printedText).toContain(studentName(kind, 0));
      expect(printedText).toContain(studentName(kind, RESULT_COUNT - 1));
      expect(printedText).toContain(`عدد النتائج المطبوعة: ${RESULT_COUNT}`);
      expect(printedFilters).toContain("الصف: الأول");
      expect(printedFilters).toContain("الفصل: الأول / أ");
      if (kind === "absence") expect(printedFilters).toContain("نوع الغياب: جزئي · حالة العذر: مختلط");
      if (kind === "lateness") expect(printedFilters).toContain("الحد الأدنى للمرات: 2 · الحد الأدنى للدقائق: 10");
      if (kind === "referrals") {
        expect(printedFilters).toContain("الحالة: المفتوحة · الأولوية: عاجلة");
        expect(printedFilters).toContain("المرشد: أحمد المرشد");
      }
      const printCalls = api.calls.filter((call) => call.url.includes("_export_all=1"));
      expect(printCalls).toHaveLength(1);
      const request = printCalls[0]!;
      const url = new URL(request.url, "http://localhost");
      expect(url.pathname).toBe(`/api/v1/reports/${kind}/`);
      for (const [key, value] of Object.entries({ from_date: FROM_DATE, to_date: TO_DATE, page: "1", _export_all: "1", grade: "2", section: "20", ...extra })) {
        expect(url.searchParams.get(key), key).toBe(value);
      }
      expect(url.searchParams.has("preset")).toBe(false);
      expect(request.init?.credentials).toBe("include");
      expect(screen.queryByTestId("report-print-table")).not.toBeInTheDocument();
      expect(screen.getByText("صفحة 2 من 7")).toBeInTheDocument();
      expect(screen.getByTestId("report-results").querySelectorAll("tbody tr")).toHaveLength(25);
      expect(screen.getByText(studentName(kind, 25))).toBeInTheDocument();
      expect(screen.queryByText(studentName(kind, 0))).not.toBeInTheDocument();
    },
  );

  it.each(["absence", "lateness", "referrals"] as const)("prepares all %s results for Ctrl+P", async (kind) => {
    setupReports();
    renderApp("/reports");
    await openReport(kind);
    let printedRows = 0;
    const print = vi.spyOn(window, "print").mockImplementation(() => {
      printedRows = document.querySelector('[data-testid="report-print-table"]')?.querySelectorAll("tbody tr").length ?? 0;
    });
    expect(fireEvent.keyDown(document, { key: "p", ctrlKey: true })).toBe(false);
    await waitFor(() => expect(print).toHaveBeenCalledOnce());
    expect(printedRows).toBe(RESULT_COUNT);
  });

  it("retains the selected student when preparing the printable result", async () => {
    const api = setupReports();
    renderApp("/reports");
    await openReport("absence");
    await userEvent.type(screen.getByLabelText("البحث عن الطالب"), "المحدد");
    await userEvent.click(await screen.findByRole("button", { name: /الطالب المحدد/ }));
    await screen.findByText(studentName("absence", 76));
    let printedCount = 0;
    let printedText = "";
    const print = vi.spyOn(window, "print").mockImplementation(() => {
      const snapshot = document.querySelector('[data-testid="report-print-table"]');
      printedCount = snapshot?.querySelectorAll("tbody tr").length ?? 0;
      printedText = snapshot?.textContent ?? "";
      expect(document.querySelector(".report-print-heading")?.textContent).toContain("سجل الطالب المحدد بالفلتر");
      expect(document.querySelector(".report-print-heading")?.textContent).not.toContain("كل المدرسة");
    });
    await userEvent.click(screen.getByRole("button", { name: "طباعة واضحة" }));
    await waitFor(() => expect(print).toHaveBeenCalledOnce());
    expect(printedCount).toBe(1);
    expect(printedText).toContain(studentName("absence", 76));
    const request = api.calls.find((call) => call.url.includes("_export_all=1"))!;
    expect(new URL(request.url, "http://localhost").searchParams.get("student")).toBe("77");
  });

  it("preserves separate absence rows for one student across multiple sections", async () => {
    const api = setupReports();
    const respond = api.fetchMock.getMockImplementation()!;
    const student = reportRows("absence")[0] as AbsenceRow;
    api.fetchMock.mockImplementation(async (input, init) => {
      if (String(input).includes("_export_all=1")) {
        api.calls.push({ url: String(input), init });
        return jsonResponse({
          ...reportPayload("absence", new URLSearchParams("_export_all=1")),
          results: [student, { ...student, section_name: "ب" }], count: 2, page_size: 2,
        });
      }
      return respond(input, init);
    });
    let sections: string[] = [];
    const print = vi.spyOn(window, "print").mockImplementation(() => {
      const snapshot = document.querySelector('[data-testid="report-print-table"]');
      sections = Array.from(snapshot?.querySelectorAll("tbody tr") ?? [], (row) => row.querySelectorAll("td")[2]?.textContent ?? "");
    });
    renderApp("/reports");
    await openReport("absence");
    await userEvent.click(screen.getByRole("button", { name: "طباعة واضحة" }));
    await waitFor(() => expect(print).toHaveBeenCalledOnce());
    expect(sections).toEqual(["الأول / أ", "الأول / ب"]);
  });

  it("waits for the complete snapshot and disables both print controls while preparing", async () => {
    const api = setupReports();
    const pending = holdPrintRequest(api);
    const print = vi.spyOn(window, "print").mockImplementation(() => undefined);
    renderApp("/reports");
    await openReport("absence");
    await userEvent.click(screen.getByRole("button", { name: "طباعة التقرير النشط" }));

    await waitFor(() => expect(pending.getRequest()).toBeDefined());
    const loadingButtons = screen.getAllByRole("button", { name: PRINT_LOADING });
    expect(loadingButtons).toHaveLength(2);
    for (const button of loadingButtons) expect(button).toBeDisabled();
    await userEvent.click(loadingButtons[0]!);
    expect(api.calls.filter((call) => call.url.includes("_export_all=1"))).toHaveLength(1);
    expect(print).not.toHaveBeenCalled();
    expect(screen.queryByTestId("report-print-table")).not.toBeInTheDocument();

    await pending.resolve(reportPayload("absence", new URLSearchParams("_export_all=1")));
    await waitFor(() => expect(print).toHaveBeenCalledOnce());
    for (const name of PRINT_BUTTONS) expect(screen.getByRole("button", { name })).toBeEnabled();
  });

  it("reports a failed full-results request inline, keeps the current page, and can retry", async () => {
    const api = setupReports();
    const respond = api.fetchMock.getMockImplementation()!;
    let attempts = 0;
    api.fetchMock.mockImplementation(async (input, init) => {
      if (String(input).includes("_export_all=1") && attempts++ === 0) {
        api.calls.push({ url: String(input), init });
        return jsonResponse({ code: "SERVER_ERROR", message: "الخادم غير متاح مؤقتًا", details: {} }, 503);
      }
      return respond(input, init);
    });
    const print = vi.spyOn(window, "print").mockImplementation(() => undefined);
    renderApp("/reports");
    await openReport("absence");
    await userEvent.click(screen.getByRole("button", { name: "التالي" }));
    await screen.findByText(studentName("absence", 25));
    await userEvent.click(screen.getByRole("button", { name: "طباعة واضحة" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("تعذر إعداد جميع النتائج للطباعة.");
    expect(screen.getByRole("alert")).toHaveTextContent("الخادم غير متاح مؤقتًا");
    expect(print).not.toHaveBeenCalled();
    expect(screen.queryByTestId("report-print-table")).not.toBeInTheDocument();
    expect(screen.getByText("صفحة 2 من 7")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "طباعة التقرير النشط" }));
    await waitFor(() => expect(print).toHaveBeenCalledOnce());
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("refuses to print a successful response that omits some matching rows", async () => {
    const api = setupReports();
    const respond = api.fetchMock.getMockImplementation()!;
    api.fetchMock.mockImplementation(async (input, init) => {
      if (String(input).includes("_export_all=1")) {
        api.calls.push({ url: String(input), init });
        return jsonResponse({ ...reportPayload("absence", new URLSearchParams("_export_all=1")), results: reportRows("absence").slice(0, 100) });
      }
      return respond(input, init);
    });
    const print = vi.spyOn(window, "print").mockImplementation(() => undefined);
    renderApp("/reports");
    await openReport("absence");
    await userEvent.click(screen.getByRole("button", { name: "طباعة واضحة" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("تعذر إعداد جميع النتائج للطباعة.");
    expect(print).not.toHaveBeenCalled();
    expect(screen.queryByTestId("report-print-table")).not.toBeInTheDocument();
    expect(screen.getByTestId("report-results").querySelectorAll("tbody tr")).toHaveLength(25);
  });

  it.each(["tab", "common filter", "report filter"] as const)(
    "cancels pending printing after changing the %s and ignores a late successful response",
    async (change) => {
      const api = setupReports();
      const pending = holdPrintRequest(api);
      const print = vi.spyOn(window, "print").mockImplementation(() => undefined);
      renderApp("/reports");
      await openReport("absence");
      await userEvent.click(screen.getByRole("button", { name: "طباعة واضحة" }));
      await waitFor(() => expect(pending.getRequest()).toBeDefined());
      if (change === "tab") {
        await userEvent.click(screen.getByRole("tab", { name: "التأخر" }));
        await screen.findByText(studentName("lateness", 0));
      } else if (change === "common filter") {
        await userEvent.selectOptions(screen.getByLabelText("الصف"), "2");
      } else {
        await userEvent.selectOptions(screen.getByLabelText("نوع الغياب"), "PARTIAL");
      }
      expect(pending.getRequest()?.init?.signal?.aborted).toBe(true);
      await pending.resolve(reportPayload("absence", new URLSearchParams("_export_all=1")));

      expect(print).not.toHaveBeenCalled();
      expect(screen.queryByTestId("report-print-table")).not.toBeInTheDocument();
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
      expect(screen.getByRole("button", { name: "طباعة التقرير النشط" })).toBeEnabled();
    },
  );
});
