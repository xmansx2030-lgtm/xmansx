import { screen, waitFor, within } from "@testing-library/react";
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
    morning_late_occurrences: 8,
    morning_late_minutes: 137,
  },
};

const WARNINGS = {
  count: 1,
  next: null,
  previous: null,
  results: [
    {
      id: 21,
      student_id: 5,
      student_name: "محمد أحمد",
      grade_name: "الأول الثانوي",
      section_name: "2",
      warning_type: "UNEXCUSED_FULL_DAY_ABSENCE",
      warning_type_label: "غياب يوم كامل بدون عذر",
      level: "LEVEL_2",
      level_label: "الإنذار الثاني",
      status: "ISSUED",
      threshold_at_issue: 5,
      metric_value_at_issue: 5,
      issued_at: "2026-08-18T09:00:00Z",
      issued_by: "سعد الوكيل",
      notes: "",
      voided_at: null,
      voided_by: null,
      void_reason: "",
    },
  ],
};

const ACTION_ROW = {
  id: 31,
  student_id: 5,
  action_type: "PARENT_CONTACT",
  action_type_label: "التواصل مع ولي الأمر",
  status: "COMPLETED",
  status_label: "منفذ",
  warning_id: 21,
  warning_label: "الإنذار الثاني — غياب يوم كامل بدون عذر",
  performed_at: "2026-08-19T08:00:00Z",
  performed_by_name: "سعد الوكيل",
  notes: "تم التواصل مع ولي الأمر",
  cancelled_at: null,
  cancelled_by_name: null,
  cancellation_reason: "",
};

const DOCUMENT_ROW = {
  id: 41,
  student_id: 5,
  document_type: "WARNING_LEVEL_2",
  document_type_label: "الإنذار الثاني",
  status: "READY",
  status_label: "جاهز",
  template: "warning_level_2:v1",
  warning_id: 21,
  action_id: null,
  generated_at: "2026-08-19T10:00:00Z",
  generated_by_name: "سعد الوكيل",
  size_bytes: 24000,
  checksum: "abc123",
  error_code: "",
  can_download: true,
};

const PREVIEW = {
  document_type: "WARNING_LEVEL_2",
  document_type_label: "الإنذار الثاني",
  template: "warning_level_2:v1",
  already_exists: false,
  snapshot: {
    warning: {
      level_label: "الإنذار الثاني",
      metric_value_at_issue: 5,
      unit: "يوم",
    },
  },
};

function parseBody(init?: RequestInit): Record<string, unknown> {
  return JSON.parse(String(init?.body ?? "{}")) as Record<string, unknown>;
}

async function openTab(name: string) {
  const user = userEvent.setup();
  renderApp("/students/5/attendance");
  await screen.findByRole("heading", { name: "محمد أحمد" });
  await user.click(screen.getByRole("button", { name }));
  return user;
}

describe("student actions tab (Phase 12)", () => {
  beforeEach(() => {
    queryClient.clear();
    document.cookie = "csrftoken=test-token";
  });

  it("lists actions with type, actor, and linked warning", async () => {
    mockApi({
      "/auth/me/": { body: roleMe(["VICE_PRINCIPAL"]) },
      "/attendance-profile/": { body: PROFILE },
      "/warnings/?student=5": { body: WARNINGS },
      "/student-actions/": { body: { count: 1, next: null, previous: null, results: [ACTION_ROW] } },
    });

    await openTab("الإجراءات");
    const row = await screen.findByTestId("action-31");
    expect(row).toHaveTextContent("التواصل مع ولي الأمر");
    expect(row).toHaveTextContent("سعد الوكيل");
    expect(row).toHaveTextContent("الإنذار الثاني");
    expect(screen.getByTestId("action-status-31")).toHaveTextContent("منفذ");
  });

  it("creates an action linked to a warning without trusted fields", async () => {
    const { calls } = mockApi({
      "/auth/me/": { body: roleMe(["VICE_PRINCIPAL"]) },
      "/attendance-profile/": { body: PROFILE },
      "/warnings/?student=5": { body: WARNINGS },
      "/student-actions/": (init) =>
        init?.method === "POST"
          ? { status: 201, body: ACTION_ROW }
          : { body: { count: 0, next: null, previous: null, results: [] } },
    });

    const user = await openTab("الإجراءات");
    await user.click(await screen.findByTestId("new-action"));
    await user.selectOptions(screen.getByTestId("action-type"), "PARENT_CONTACT");
    await user.selectOptions(screen.getByTestId("action-warning"), "21");
    await user.type(screen.getByTestId("action-notes"), "تم التواصل");
    await user.click(screen.getByTestId("save-action"));

    await waitFor(() => {
      const post = calls.find(
        (call) => call.init?.method === "POST" && call.url.includes("/student-actions/"),
      );
      expect(post).toBeDefined();
      const body = parseBody(post?.init);
      expect(body).toEqual({
        student_id: 5,
        action_type: "PARENT_CONTACT",
        warning_id: 21,
        notes: "تم التواصل",
      });
    });
  });

  it("cancels an action with a reason instead of deleting it", async () => {
    const { calls } = mockApi({
      "/auth/me/": { body: roleMe(["SCHOOL_MANAGER"]) },
      "/attendance-profile/": { body: PROFILE },
      "/warnings/?student=5": { body: WARNINGS },
      "/student-actions/31/cancel/": {
        body: { ...ACTION_ROW, status: "CANCELLED", status_label: "ملغى" },
      },
      "/student-actions/": { body: { count: 1, next: null, previous: null, results: [ACTION_ROW] } },
    });

    const user = await openTab("الإجراءات");
    await user.click(await screen.findByTestId("cancel-action-31"));
    await user.type(screen.getByTestId("cancel-reason"), "سجل بالخطأ");
    await user.click(screen.getByTestId("confirm-cancel-action"));

    await waitFor(() => {
      const post = calls.find((call) => call.url.includes("/student-actions/31/cancel/"));
      expect(post).toBeDefined();
      expect(parseBody(post?.init)).toEqual({ reason: "سجل بالخطأ" });
    });
  });

  it("hides action creation from the counselor", async () => {
    mockApi({
      "/auth/me/": { body: roleMe(["COUNSELOR"]) },
      "/attendance-profile/": { body: PROFILE },
      "/student-actions/": { body: { count: 1, next: null, previous: null, results: [ACTION_ROW] } },
    });

    await openTab("الإجراءات");
    expect(await screen.findByTestId("action-31")).toBeInTheDocument();
    expect(screen.queryByTestId("new-action")).not.toBeInTheDocument();
    expect(screen.queryByTestId("cancel-action-31")).not.toBeInTheDocument();
  });
});

describe("student documents tab (Phase 12)", () => {
  beforeEach(() => {
    queryClient.clear();
    document.cookie = "csrftoken=test-token";
  });

  it("previews before generating and shows the frozen issue value", async () => {
    mockApi({
      "/auth/me/": { body: roleMe(["VICE_PRINCIPAL"]) },
      "/attendance-profile/": { body: PROFILE },
      "/warnings/?student=5": { body: WARNINGS },
      "/documents/preview/": { body: PREVIEW },
      "/documents/?student=5": { body: { count: 0, next: null, previous: null, results: [] } },
    });

    const user = await openTab("المستندات");
    await user.selectOptions(await screen.findByTestId("document-type"), "WARNING_LEVEL_2");
    await user.selectOptions(screen.getByTestId("document-warning"), "21");
    await user.click(screen.getByTestId("preview-document"));

    const preview = await screen.findByTestId("document-preview");
    expect(preview).toHaveTextContent("الإنذار الثاني");
    expect(preview).toHaveTextContent("صدر عند 5 يوم");
    expect(preview).toHaveTextContent("warning_level_2:v1");
  });

  it("generates a warning document with intent-only payload", async () => {
    const { calls } = mockApi({
      "/auth/me/": { body: roleMe(["VICE_PRINCIPAL"]) },
      "/attendance-profile/": { body: PROFILE },
      "/warnings/?student=5": { body: WARNINGS },
      "/documents/preview/": { body: PREVIEW },
      "/documents/generate/": { status: 201, body: DOCUMENT_ROW },
      "/documents/?student=5": { body: { count: 0, next: null, previous: null, results: [] } },
    });

    const user = await openTab("المستندات");
    await user.selectOptions(await screen.findByTestId("document-type"), "WARNING_LEVEL_2");
    await user.selectOptions(screen.getByTestId("document-warning"), "21");
    await user.click(screen.getByTestId("preview-document"));
    await user.click(await screen.findByTestId("create-document"));

    await waitFor(() => {
      const post = calls.find((call) => call.url.includes("/documents/generate/"));
      expect(post).toBeDefined();
      const body = parseBody(post?.init);
      expect(body).toEqual({
        student_id: 5,
        document_type: "WARNING_LEVEL_2",
        warning_id: 21,
        create_action: false,
      });
      expect(body).not.toHaveProperty("snapshot_data");
      expect(body).not.toHaveProperty("metric_value_at_issue");
    });
  });

  it("generates a report with the selected date range", async () => {
    const { calls } = mockApi({
      "/auth/me/": { body: roleMe(["VICE_PRINCIPAL"]) },
      "/attendance-profile/": { body: PROFILE },
      "/warnings/?student=5": { body: WARNINGS },
      "/documents/preview/": {
        body: {
          document_type: "MORNING_LATE_DETAIL_REPORT",
          document_type_label: "كشف تفصيلي للتأخر الصباحي",
          template: "morning_late_report:v1",
          already_exists: false,
          snapshot: { totals: { occurrences: 8 } },
        },
      },
      "/documents/generate/": {
        status: 201,
        body: { ...DOCUMENT_ROW, document_type: "MORNING_LATE_DETAIL_REPORT" },
      },
      "/documents/?student=5": { body: { count: 0, next: null, previous: null, results: [] } },
    });

    const user = await openTab("المستندات");
    await user.selectOptions(
      await screen.findByTestId("document-type"),
      "MORNING_LATE_DETAIL_REPORT",
    );
    const from = screen.getByTestId("document-from");
    await user.clear(from);
    await user.type(from, "2026-08-01");
    await user.click(screen.getByTestId("preview-document"));
    expect(await screen.findByTestId("document-preview")).toHaveTextContent("عدد السجلات: 8");

    await user.click(screen.getByTestId("create-document"));
    await waitFor(() => {
      const post = calls.find((call) => call.url.includes("/documents/generate/"));
      const body = parseBody(post?.init) as { from_date: string; document_type: string };
      expect(body.document_type).toBe("MORNING_LATE_DETAIL_REPORT");
      expect(body.from_date).toBe("2026-08-01");
    });
  });

  it("shows ready documents with a download link and version", async () => {
    mockApi({
      "/auth/me/": { body: roleMe(["VICE_PRINCIPAL"]) },
      "/attendance-profile/": { body: PROFILE },
      "/warnings/?student=5": { body: WARNINGS },
      "/documents/?student=5": {
        body: { count: 1, next: null, previous: null, results: [DOCUMENT_ROW] },
      },
    });

    await openTab("المستندات");
    const row = await screen.findByTestId("doc-row-41");
    expect(row).toHaveTextContent("الإنذار الثاني");
    expect(row).toHaveTextContent("warning_level_2:v1");
    expect(screen.getByTestId("doc-status-41")).toHaveTextContent("جاهز");
    expect(screen.getByTestId("doc-download-41")).toHaveAttribute(
      "href",
      "/api/v1/documents/41/download/",
    );
  });

  it("offers retry for a failed document and hides download", async () => {
    const failed = {
      ...DOCUMENT_ROW,
      id: 42,
      status: "FAILED",
      status_label: "فشل الإنشاء",
      error_code: "DOCUMENT_RENDER_FAILED",
      can_download: false,
    };
    const { calls } = mockApi({
      "/auth/me/": { body: roleMe(["VICE_PRINCIPAL"]) },
      "/attendance-profile/": { body: PROFILE },
      "/warnings/?student=5": { body: WARNINGS },
      "/documents/42/retry/": { body: { ...failed, status: "READY", status_label: "جاهز" } },
      "/documents/?student=5": {
        body: { count: 1, next: null, previous: null, results: [failed] },
      },
    });

    const user = await openTab("المستندات");
    const row = await screen.findByTestId("doc-row-42");
    expect(row).toHaveTextContent("DOCUMENT_RENDER_FAILED");
    expect(screen.queryByTestId("doc-download-42")).not.toBeInTheDocument();

    await user.click(screen.getByTestId("doc-retry-42"));
    await waitFor(() => {
      expect(calls.some((call) => call.url.includes("/documents/42/retry/"))).toBe(true);
    });
  });

  it("counselor sees documents read-only without download", async () => {
    mockApi({
      "/auth/me/": { body: roleMe(["COUNSELOR"]) },
      "/attendance-profile/": { body: PROFILE },
      "/documents/?student=5": {
        body: {
          count: 1,
          next: null,
          previous: null,
          results: [{ ...DOCUMENT_ROW, can_download: false }],
        },
      },
    });

    await openTab("المستندات");
    expect(await screen.findByTestId("doc-row-41")).toBeInTheDocument();
    expect(screen.queryByTestId("document-form")).not.toBeInTheDocument();
    expect(screen.queryByTestId("doc-download-41")).not.toBeInTheDocument();
    expect(screen.queryByTestId("doc-void-41")).not.toBeInTheDocument();
  });

  it("only the manager can void a document, with a reason", async () => {
    const { calls } = mockApi({
      "/auth/me/": { body: roleMe(["SCHOOL_MANAGER"]) },
      "/attendance-profile/": { body: PROFILE },
      "/warnings/?student=5": { body: WARNINGS },
      "/documents/41/void/": {
        body: { ...DOCUMENT_ROW, status: "VOIDED", status_label: "ملغى", can_download: false },
      },
      "/documents/?student=5": {
        body: { count: 1, next: null, previous: null, results: [DOCUMENT_ROW] },
      },
    });

    const user = await openTab("المستندات");
    await user.click(await screen.findByTestId("doc-void-41"));
    await user.type(screen.getByTestId("void-document-reason"), "أُصدر بالخطأ");
    await user.click(screen.getByTestId("confirm-void-document"));

    await waitFor(() => {
      const post = calls.find((call) => call.url.includes("/documents/41/void/"));
      expect(post).toBeDefined();
      expect(parseBody(post?.init)).toEqual({ reason: "أُصدر بالخطأ" });
    });
  });

  it("vice principal cannot void", async () => {
    mockApi({
      "/auth/me/": { body: roleMe(["VICE_PRINCIPAL"]) },
      "/attendance-profile/": { body: PROFILE },
      "/warnings/?student=5": { body: WARNINGS },
      "/documents/?student=5": {
        body: { count: 1, next: null, previous: null, results: [DOCUMENT_ROW] },
      },
    });

    await openTab("المستندات");
    await screen.findByTestId("doc-row-41");
    expect(screen.queryByTestId("doc-void-41")).not.toBeInTheDocument();
  });

  it("commitment generation also records the commitment action", async () => {
    const { calls } = mockApi({
      "/auth/me/": { body: roleMe(["VICE_PRINCIPAL"]) },
      "/attendance-profile/": { body: PROFILE },
      "/warnings/?student=5": { body: WARNINGS },
      "/documents/preview/": {
        body: {
          document_type: "ATTENDANCE_COMMITMENT",
          document_type_label: "تعهد الالتزام بالحضور",
          template: "attendance_commitment:v1",
          already_exists: false,
          snapshot: { metrics: { unexcused_full_absence_days: 5 } },
        },
      },
      "/documents/generate/": {
        status: 201,
        body: { ...DOCUMENT_ROW, document_type: "ATTENDANCE_COMMITMENT", action_id: 31 },
      },
      "/documents/?student=5": { body: { count: 0, next: null, previous: null, results: [] } },
    });

    const user = await openTab("المستندات");
    await user.click(await screen.findByTestId("preview-document"));
    expect(await screen.findByTestId("document-preview")).toHaveTextContent(
      "غياب بدون عذر: 5 يوم",
    );
    await user.click(screen.getByTestId("create-document"));

    await waitFor(() => {
      const post = calls.find((call) => call.url.includes("/documents/generate/"));
      const body = parseBody(post?.init) as { create_action: boolean };
      expect(body.create_action).toBe(true);
    });
  });

  it("shows both new tabs in the student profile", async () => {
    mockApi({
      "/auth/me/": { body: roleMe(["VICE_PRINCIPAL"]) },
      "/attendance-profile/": { body: PROFILE },
    });

    renderApp("/students/5/attendance");
    await screen.findByRole("heading", { name: "محمد أحمد" });
    const tabs = screen.getAllByRole("button");
    const labels = tabs.map((tab) => tab.textContent);
    expect(labels).toContain("الإجراءات");
    expect(labels).toContain("المستندات");
  });

  it("keeps document rows free of the full national id", async () => {
    mockApi({
      "/auth/me/": { body: roleMe(["VICE_PRINCIPAL"]) },
      "/attendance-profile/": { body: PROFILE },
      "/warnings/?student=5": { body: WARNINGS },
      "/documents/?student=5": {
        body: { count: 1, next: null, previous: null, results: [DOCUMENT_ROW] },
      },
    });

    await openTab("المستندات");
    const tab = await screen.findByTestId("student-documents-tab");
    expect(within(tab).queryByText(/\d{10}/)).not.toBeInTheDocument();
  });
});
