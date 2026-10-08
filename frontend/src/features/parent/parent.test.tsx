import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { queryClient } from "@/app/queryClient";
import { buildMe, membership, mockApi, UNAUTHENTICATED } from "@/test/mockApi";
import { renderApp } from "@/test/renderApp";
import { parentKey, type ChildDetail } from "@/features/parent/api";
import { todayDate } from "@/features/parent/shared";

vi.mock("qrcode", () => ({
  default: { toCanvas: vi.fn().mockResolvedValue(undefined) },
}));
const DATE = todayDate();
const PARENT = buildMe({
  id: 201,
  name: "محمد ولي الأمر",
  has_parent_portal: true,
});
const STAFF_PARENT = buildMe({
  ...PARENT,
  active_school: { id: 10, name: "مدرسة النور", slug: "noor" },
  roles: ["TEACHER"],
  memberships: [membership(1, 10, "مدرسة النور", ["TEACHER"])],
});
const DAY = {
  date: DATE,
  absence_status: "FULL" as const,
  completeness_status: "INCOMPLETE",
  expected_periods: 5,
  submitted_periods: 1,
  present_periods: 0,
  absent_periods: 1,
  excused_absent_periods: 0,
  unexcused_absent_periods: 1,
  updated_at: `${DATE}T05:00:00Z`,
};
const CHILD = {
  relation_id: 11,
  school: { id: 10, name: "مدرسة النور" },
  student: {
    id: 5,
    full_name: "أحمد محمد",
    grade_name: "الأول الثانوي",
    section_name: "2",
    department: "علمي",
  },
  status: "ACTIVE" as const,
  today: DAY,
};
const DETAIL: ChildDetail = {
  child: CHILD,
  today: DAY,
  morning: {
    status: "NOT_RECORDED",
    arrival_time: null,
    counted_late_minutes: 0,
    updated_at: null,
  },
  periods: [
    {
      sequence: 1,
      period_sequence: 1,
      name: "الحصة الأولى",
      attendance_date: DATE,
      session_id: 55,
      start_time: "07:00",
      end_time: "07:45",
      status: "ABSENT",
      status_label: "غائب",
      updated_at: `${DATE}T05:00:00Z`,
    },
    {
      sequence: 2,
      period_sequence: 2,
      name: "الحصة الثانية",
      attendance_date: DATE,
      session_id: 56,
      start_time: "07:45",
      end_time: "08:30",
      status: "IN_PROGRESS",
      status_label: "بانتظار اعتماد التحضير",
      updated_at: null,
    },
    {
      sequence: 3,
      period_sequence: 3,
      name: "الحصة الثالثة",
      attendance_date: DATE,
      session_id: null,
      start_time: "09:00",
      end_time: "09:45",
      status: "NOT_STARTED",
      status_label: "لم تبدأ",
      updated_at: null,
    },
  ],
};
const EXCUSE = {
  id: 71,
  type: "EXCUSE",
  relation_id: 11,
  student_id: 5,
  status: "PENDING",
  reason_type: "MEDICAL_REPORT",
  notes: "تقرير طبي معتمد",
  targets: [{ attendance_date: DATE, period_sequence: null }],
  decision_note: "",
  administrative_excuse_id: null,
  created_at: `${DATE}T05:00:00Z`,
  updated_at: `${DATE}T05:00:00Z`,
  attachments: [],
};
const metadataPath =
  "/parent/registration/11111111-1111-4111-8111-111111111111/";
function detailApi(extra: Parameters<typeof mockApi>[0] = {}) {
  return mockApi({
    "/auth/me/": { body: PARENT },
    "/parent/children/11/": { body: DETAIL },
    ...extra,
  });
}
describe("parent portal isolation and family workflows", () => {
  beforeEach(() => {
    queryClient.clear();
    document.cookie = "csrftoken=test-token";
    window.history.replaceState({}, "", "/");
  });

  it("routes a global parent without employee membership to the parent portal", async () => {
    mockApi({
      "/auth/me/": { body: PARENT },
      "/parent/children/": { body: { results: [CHILD] } },
    });
    renderApp("/");
    expect(await screen.findByTestId("parent-shell")).toBeInTheDocument();
    expect(
      await screen.findByRole("heading", { name: "أحمد محمد" }),
    ).toBeInTheDocument();
    expect(screen.queryByText("اختر المدرسة")).not.toBeInTheDocument();
  });
  it("shows children at independent schools in one account", async () => {
    mockApi({
      "/auth/me/": { body: PARENT },
      "/parent/children/": {
        body: {
          results: [
            CHILD,
            {
              ...CHILD,
              relation_id: 22,
              school: { id: 20, name: "مدرسة الأفق" },
              student: { ...CHILD.student, id: 6, full_name: "خالد محمد" },
            },
          ],
        },
      },
    });
    renderApp("/parent");
    expect(await screen.findByText("مدرسة الأفق")).toBeInTheDocument();
    expect(screen.getByText("مدرسة النور")).toBeInTheDocument();
    expect(
      screen.getAllByRole("link", { name: "متابعة المواظبة" }),
    ).toHaveLength(2);
  });
  it("shows per-child new notifications and required actions with a scoped notification link", async () => {
    mockApi({
      "/auth/me/": { body: PARENT },
      "/parent/children/": {
        body: {
          results: [{ ...CHILD, new_notifications: 3, required_actions: 2 }],
        },
      },
    });
    renderApp("/parent");
    const link = await screen.findByRole("link", {
      name: "تنبيهات وإجراءات أحمد محمد",
    });
    expect(link).toHaveAttribute(
      "href",
      "/parent/notifications?relation_id=11",
    );
    expect(link).toHaveTextContent("تنبيهات جديدة 3");
    expect(link).toHaveTextContent("إجراءات مطلوبة 2");
  });
  it("filters notifications server-side and identifies the permitted child and school", async () => {
    const { calls } = mockApi({
      "/auth/me/": { body: PARENT },
      "/parent/notifications/": {
        body: {
          items: [
            {
              id: 8,
              relation_id: 11,
              student_name: "أحمد محمد",
              school_name: "مدرسة النور",
              kind: "ABSENCE",
              title: "غياب حصة",
              body: "الحصة الأولى",
              state: "NEW",
              requires_action: false,
              created_at: `${DATE}T05:00:00Z`,
              read_at: null,
              action_completed_at: null,
            },
          ],
        },
      },
    });
    renderApp("/parent/notifications?relation_id=11");
    expect(
      await screen.findByText("أحمد محمد · مدرسة النور"),
    ).toBeInTheDocument();
    expect(
      calls.some(
        (call) => call.url === "/api/v1/parent/notifications/?relation_id=11",
      ),
    ).toBe(true);
    expect(
      screen.getByRole("link", { name: "عرض جميع الأبناء" }),
    ).toHaveAttribute("href", "/parent/notifications");
  });
  it("offers all five parent sections and opens attendance through the child's history", async () => {
    mockApi({
      "/auth/me/": { body: PARENT },
      "/parent/children/11/history/": { body: { results: [], summary: {} } },
      "/parent/children/11/": { body: DETAIL },
      "/parent/children/": { body: { results: [CHILD] } },
    });
    renderApp("/parent/attendance");
    const user = userEvent.setup();
    const navigation = await screen.findByRole("navigation", {
      name: "تنقل بوابة ولي الأمر",
    });
    expect(within(navigation).getAllByRole("link")).toHaveLength(5);
    const link = await screen.findByRole("link", { name: "عرض سجل المواظبة" });
    expect(link).toHaveAttribute("href", "/parent/children/11?tab=history");
    await user.click(link);
    expect(
      await screen.findByRole("tab", { name: "سجل المواظبة" }),
    ).toHaveAttribute("aria-selected", "true");
    expect(
      await screen.findByRole("heading", { name: "ملخص الفترة" }),
    ).toBeInTheDocument();
  });
  it("keeps suspended relationship content hidden and other children accessible", async () => {
    mockApi({
      "/auth/me/": { body: PARENT },
      "/parent/children/": {
        body: {
          results: [
            CHILD,
            {
              relation_id: 22,
              school: { id: 20, name: "مدرسة الأفق" },
              status: "SUSPENDED_CONTACT_REVIEW",
              student: null,
              today: null,
            },
          ],
        },
      },
    });
    renderApp("/parent");
    const suspended = await screen.findByTestId("parent-child-22");
    expect(suspended).toHaveTextContent("معلقة لمراجعة التواصل");
    expect(within(suspended).queryByRole("link")).toBeNull();
    expect(
      screen.getByRole("link", { name: "متابعة المواظبة" }),
    ).toHaveAttribute("href", "/parent/children/11");
  });
  it("never exposes staff leave or gate actions to a parent-only account", async () => {
    const { calls } = mockApi({
      "/auth/me/": { body: PARENT },
      "/parent/children/": { body: { results: [CHILD] } },
    });
    renderApp("/gate");
    await screen.findByTestId("parent-shell");
    expect(screen.queryByText("الاستئذانات")).toBeNull();
    expect(screen.queryByText("طلب استئذان")).toBeNull();
    expect(calls.some((call) => /student-leaves|gate\//.test(call.url))).toBe(
      false,
    );
  });
  it("staff retain their work destination and switching space removes old cached data", async () => {
    queryClient.setQueryData(["school", 10, "private-sentinel"], {
      name: "private old pupil",
    });
    mockApi({
      "/auth/me/": { body: STAFF_PARENT },
      "/parent/children/": { body: { results: [CHILD] } },
    });
    renderApp("/");
    const user = userEvent.setup();
    await user.click(
      await screen.findByRole("button", { name: "بوابة ولي الأمر" }),
    );
    await screen.findByTestId("parent-shell");
    expect(
      queryClient.getQueryData(["school", 10, "private-sentinel"]),
    ).toBeUndefined();
    expect(
      screen.getByRole("button", { name: "مساحة العمل" }),
    ).toBeInTheDocument();
  });
  it("labels draft and future periods accurately and never confirms incomplete FULL days", async () => {
    detailApi();
    renderApp("/parent/children/11");
    expect(
      await screen.findByText("بانتظار اعتماد التحضير"),
    ).toBeInTheDocument();
    expect(screen.getByText("لم تبدأ")).toBeInTheDocument();
    expect(screen.getByText("بيانات اليوم غير مكتملة")).toBeInTheDocument();
    expect(screen.queryByText("غياب يوم كامل")).toBeNull();
    const second = screen
      .getByRole("heading", { name: "الحصة الثانية" })
      .closest("li");
    expect(second).toHaveTextContent("بانتظار اعتماد التحضير");
    expect(second).not.toHaveTextContent("غائب");
  });
  it("treats missing morning arrival as no record and not proof of absence", async () => {
    detailApi();
    renderApp("/parent/children/11");
    expect(await screen.findByText("لم تسجل بصمة وصول")).toBeInTheDocument();
    expect(
      screen.getByText("غياب بصمة الوصول لا يعني غياب الطالب عن المدرسة."),
    ).toBeInTheDocument();
  });
  it("supports RTL keyboard navigation with a linked active tab panel", async () => {
    detailApi();
    renderApp("/parent/children/11");
    const today = await screen.findByRole("tab", { name: "اليوم" });
    today.focus();
    fireEvent.keyDown(today, { key: "ArrowLeft" });
    const history = screen.getByRole("tab", { name: "سجل المواظبة" });
    expect(history).toHaveFocus();
    expect(history).toHaveAttribute("aria-selected", "true");
    expect(today).toHaveAttribute("tabindex", "-1");
    expect(screen.getByRole("tabpanel")).toHaveAttribute(
      "aria-labelledby",
      history.id,
    );
    fireEvent.keyDown(history, { key: "Home" });
    expect(today).toHaveFocus();
    expect(today).toHaveAttribute("aria-selected", "true");
  });
  it("uses counted morning minutes from the backend", async () => {
    mockApi({
      "/auth/me/": { body: PARENT },
      "/parent/children/11/": {
        body: {
          ...DETAIL,
          morning: {
            status: "LATE",
            arrival_time: `${DATE}T04:18:00Z`,
            counted_late_minutes: 7,
            updated_at: null,
          },
        },
      },
    });
    renderApp("/parent/children/11");
    expect(
      await screen.findByText("تأخر صباحي محتسب: 7 دقيقة"),
    ).toBeInTheDocument();
  });
  it("submits a pending excuse intention without school/user or approval fields", async () => {
    const { calls } = mockApi({
      "/auth/me/": { body: PARENT },
      "/parent/children/11/excuses/": { body: EXCUSE },
      "/parent/children/11/": { body: DETAIL },
    });
    renderApp("/parent/children/11");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("tab", { name: "تقديم طلب" }));
    await user.type(screen.getByLabelText("سبب العذر"), "تقرير طبي معتمد");
    await user.click(screen.getByRole("button", { name: "إرسال طلب العذر" }));
    expect(
      await screen.findByText("تم إرسال طلب العذر #71"),
    ).toBeInTheDocument();
    const body = JSON.parse(
      String(
        calls.find(
          (call) =>
            call.url.includes("/excuses/") && call.init?.method === "POST",
        )?.init?.body,
      ),
    ) as Record<string, unknown>;
    expect(body).toEqual({
      reason_type: "MEDICAL_REPORT",
      notes: "تقرير طبي معتمد",
      targets: [{ attendance_date: DATE, period_sequence: null }],
    });
  });
  it("correction sends an existing absent session and reason through the parent request API", async () => {
    const { calls } = mockApi({
      "/auth/me/": { body: PARENT },
      "/parent/children/11/corrections/": { body: { id: 81 } },
      "/parent/children/11/": { body: DETAIL },
    });
    renderApp("/parent/children/11");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("tab", { name: "تقديم طلب" }));
    await user.selectOptions(
      screen.getByLabelText("حصة الغياب المطلوب مراجعتها"),
      "55",
    );
    await user.type(screen.getByLabelText("سبب الاعتراض"), "كان ابني حاضراً");
    await user.click(screen.getByRole("button", { name: "طلب مراجعة الحضور" }));
    expect(
      await screen.findByText("تم إرسال طلب المراجعة #81"),
    ).toBeInTheDocument();
    expect(
      JSON.parse(
        String(
          calls.find((call) => call.url.includes("/corrections/"))?.init?.body,
        ),
      ),
    ).toEqual({ session_id: 55, reason: "كان ابني حاضراً" });
    expect(
      screen.queryByRole("button", { name: /طلب استئذان|طلب خروج/ }),
    ).toBeNull();
  });
  it("adds a requested private attachment to the existing excuse without creating a duplicate", async () => {
    const { calls } = mockApi({
      "/auth/me/": { body: PARENT },
      "/parent/children/11/excuses/71/attachments/": {
        body: {
          id: 2,
          filename: "تقرير طبي.pdf",
          mime_type: "application/pdf",
          size_bytes: 12,
        },
      },
      "/parent/requests/": {
        body: {
          items: [
            {
              ...EXCUSE,
              status: "NEEDS_INFO",
              decision_note: "أرفق التقرير الطبي",
            },
          ],
        },
      },
    });
    renderApp("/parent/requests");
    const user = userEvent.setup();
    await user.upload(
      await screen.findByLabelText("استكمال مرفق العذر #71"),
      new File(["private-file"], "تقرير طبي.pdf", { type: "application/pdf" }),
    );
    await user.click(
      screen.getByRole("button", { name: "إضافة المرفق إلى الطلب" }),
    );
    expect(
      await screen.findByText("تم استكمال مرفق العذر"),
    ).toBeInTheDocument();
    const post = calls.find((call) => call.init?.method === "POST");
    expect(post?.url).toBe(
      "/api/v1/parent/children/11/excuses/71/attachments/",
    );
    expect(post?.init?.body).toBeInstanceOf(FormData);
    expect((post?.init?.body as FormData).get("file")).toBeInstanceOf(File);
    expect(calls.filter((call) => call.init?.method === "POST")).toHaveLength(
      1,
    );
  });
  it("supports historical day lookup without deriving attendance from the current timetable", async () => {
    const { calls } = detailApi();
    renderApp("/parent/children/11");
    const input = await screen.findByLabelText("يوم المتابعة");
    fireEvent.change(input, { target: { value: "2026-09-01" } });
    await waitFor(() =>
      expect(calls.some((call) => call.url.includes("?date=2026-09-01"))).toBe(
        true,
      ),
    );
  });
  it("removes displayed and cached child details immediately after relationship denial", async () => {
    let denied = false;
    mockApi({
      "/auth/me/": { body: PARENT },
      "/parent/children/11/": () =>
        denied
          ? {
              status: 404,
              body: { code: "NOT_FOUND", message: "غير متاح", details: {} },
            }
          : { body: DETAIL },
    });
    renderApp("/parent/children/11");
    await screen.findByRole("heading", { name: "أحمد محمد" });
    denied = true;
    await queryClient.invalidateQueries({
      queryKey: parentKey(PARENT.id, "child", 11),
    });
    expect(
      await screen.findByText("تعذر عرض بيانات الابن"),
    ).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "أحمد محمد" })).toBeNull();
    await waitFor(() =>
      expect(
        queryClient
          .getQueryCache()
          .findAll({ queryKey: parentKey(PARENT.id, "child", 11) })
          .every((query) => query.state.data === undefined),
      ).toBe(true),
    );
  });
  it("opening an issued warning does not acknowledge it until explicit confirmation", async () => {
    const { calls } = mockApi({
      "/auth/me/": { body: PARENT },
      "/parent/children/11/warnings/": {
        body: {
          items: [
            {
              id: 91,
              warning_type: "UNEXCUSED_FULL_DAY_ABSENCE",
              level: "LEVEL_1",
              status: "ISSUED",
              issued_at: `${DATE}T05:00:00Z`,
              acknowledged_at: null,
              documents: [],
            },
          ],
        },
      },
      "/parent/children/11/": { body: DETAIL },
    });
    renderApp("/parent/children/11");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("tab", { name: "الإنذارات" }));
    const button = await screen.findByRole("button", {
      name: "تأكيد الاطلاع على الإنذار",
    });
    expect(calls.some((call) => call.url.includes("/acknowledge/"))).toBe(
      false,
    );
    await user.click(button);
    await waitFor(() =>
      expect(
        calls.some((call) => call.url.includes("/warnings/91/acknowledge/")),
      ).toBe(true),
    );
  });
  it("rechecks the relationship and purges private cache after a denied publication action", async () => {
    let revoked = false;
    const privateRequest = new Request("https://app.example.test/api/v1/parent/children/11/publications/19/download/");
    const deleteCached = vi.fn().mockResolvedValue(true);
    vi.stubGlobal("caches", {
      keys: vi.fn().mockResolvedValue(["legacy-private-cache"]),
      open: vi.fn().mockResolvedValue({ keys: vi.fn().mockResolvedValue([privateRequest]), delete: deleteCached }),
    });
    const { calls } = mockApi({
      "/auth/me/": { body: PARENT },
      "/parent/children/11/publications/19/acknowledge/": {
        status: 404,
        body: { code: "NOT_FOUND", message: "غير متاح", details: {} },
      },
      "/parent/children/11/publications/": { body: { items: [{ id: 19, title: "محتوى خاص للأسرة", body: "نص خاص", required_action: "", published_at: `${DATE}T05:00:00Z`, acknowledged_at: null, document: { id: 2 } }] } },
      "/parent/children/11/": () => revoked ? { status: 404, body: { code: "NOT_FOUND", message: "غير متاح", details: {} } } : { body: DETAIL },
    });
    renderApp("/parent/children/11?tab=family");
    await screen.findByRole("heading", { name: "محتوى خاص للأسرة" });
    revoked = true;
    await userEvent.setup().click(screen.getByRole("button", { name: "تأكيد الاطلاع على الرسالة" }));
    expect(await screen.findByText("تعذر عرض بيانات الابن")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "أحمد محمد" })).toBeNull();
    expect(screen.queryByText("نص خاص")).toBeNull();
    await waitFor(() => expect(deleteCached).toHaveBeenCalledWith(privateRequest));
    expect(calls.filter((call) => /children\/11\/\?date=/.test(call.url))).toHaveLength(2);
    vi.unstubAllGlobals();
  });
  it("refreshes a revoked publication without hiding a still-active child", async () => {
    let removed = false;
    mockApi({
      "/auth/me/": { body: PARENT },
      "/parent/children/11/publications/19/acknowledge/": () => {
        removed = true;
        return { status: 404, body: { code: "NOT_FOUND", message: "غير متاح", details: {} } };
      },
      "/parent/children/11/publications/": () => ({ body: { items: removed ? [] : [{ id: 19, title: "رسالة مسحوبة", body: "نص مسحوب", required_action: "", published_at: `${DATE}T05:00:00Z`, acknowledged_at: null, document: null }] } }),
      "/parent/children/11/": { body: DETAIL },
    });
    renderApp("/parent/children/11?tab=family");
    await userEvent.setup().click(await screen.findByRole("button", { name: "تأكيد الاطلاع على الرسالة" }));
    expect(await screen.findByText("لا توجد رسائل منشورة للأسرة")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "أحمد محمد" })).toBeInTheDocument();
    expect(screen.queryByText("نص مسحوب")).toBeNull();
  });
  it("keeps active child data when a read-only subscription rejects an excuse", async () => {
    mockApi({
      "/parent/children/11/excuses/": { status: 403, body: { code: "SUBSCRIPTION_WRITE_BLOCKED", message: "الاشتراك لا يسمح بطلبات جديدة", details: {} } },
      "/auth/me/": { body: PARENT },
      "/parent/children/11/": { body: DETAIL },
    });
    renderApp("/parent/children/11?tab=requests");
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("سبب العذر"), "عذر موثق للغياب");
    await user.click(screen.getByRole("button", { name: "إرسال طلب العذر" }));
    expect(await screen.findByText("الاشتراك لا يسمح بطلبات جديدة")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "أحمد محمد" })).toBeInTheDocument();
    expect(screen.queryByText(/تم إرسال طلب العذر/)).toBeNull();
  });
  it("expires cached authentication after an excuse POST loses the session without false success", async () => {
    let expired = false;
    mockApi({
      "/auth/me/": () => expired ? UNAUTHENTICATED : { body: PARENT },
      "/parent/children/11/excuses/": () => { expired = true; return UNAUTHENTICATED; },
      "/parent/children/11/": { body: DETAIL },
    });
    renderApp("/parent/children/11?tab=requests");
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("سبب العذر"), "عذر موثق للغياب");
    await user.click(screen.getByRole("button", { name: "إرسال طلب العذر" }));
    expect(await screen.findByRole("heading", { name: "تسجيل الدخول" })).toBeInTheDocument();
    expect(screen.queryByText(/تم إرسال طلب العذر/)).toBeNull();
    expect(queryClient.getQueryData(["me"])).toBeUndefined();
    expect(queryClient.getQueryCache().findAll({ queryKey: parentKey(PARENT.id) })).toHaveLength(0);
  });
  it("notification read is separate from completing an action", async () => {
    const { calls } = mockApi({
      "/auth/me/": { body: PARENT },
      "/parent/notifications/": {
        body: {
          items: [
            {
              id: 9,
              relation_id: 11,
              kind: "FAMILY_PUBLICATION",
              title: "موعد متابعة",
              body: "تواصل مع المدرسة",
              state: "NEEDS_ACTION",
              requires_action: true,
              created_at: `${DATE}T05:00:00Z`,
              read_at: null,
              action_completed_at: null,
            },
          ],
        },
      },
    });
    renderApp("/parent/notifications");
    const user = userEvent.setup();
    await user.click(
      await screen.findByRole("button", { name: "تعليم كمقروء" }),
    );
    expect(
      screen.getByRole("link", { name: "مراجعة رسالة المدرسة وتأكيد الاطلاع" }),
    ).toHaveAttribute("href", "/parent/children/11?tab=family");
    expect(calls.some((call) => call.url.includes("/9/read/"))).toBe(true);
    expect(calls.some((call) => call.url.includes("/complete-action/"))).toBe(
      false,
    );
  });
  it("public registration accepts Arabic digits and responds without student matches", async () => {
    const { calls } = mockApi({
      "/auth/me/": UNAUTHENTICATED,
      [metadataPath]: (init) =>
        init?.method === "POST"
          ? { body: { message: "تم الاستلام", receipt_token: "r".repeat(48) } }
          : {
              body: {
                school_name: "مدرسة النور",
                school_id: 10,
                enabled: true,
              },
            },
    });
    renderApp("/parent/register/11111111-1111-4111-8111-111111111111");
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("اسم ولي الأمر"), "محمد الأب");
    await user.type(screen.getByLabelText("رقم الجوال"), "٠٥٥١٢٣٤٥٦٧");
    await user.type(
      screen.getByLabelText("معرف الطالب المسجل لدى المدرسة"),
      "١٠١٢٣٤٥٦٧٨",
    );
    await user.click(screen.getByRole("button", { name: "تقديم طلب تسجيل" }));
    expect(
      await screen.findByText("تم استلام طلبك، وستقوم المدرسة بمراجعته."),
    ).toBeInTheDocument();
    const body = JSON.parse(
      String(
        calls.find(
          (call) =>
            call.url.includes(metadataPath) && call.init?.method === "POST",
        )?.init?.body,
      ),
    );
    expect(body.mobile).toBe("+966551234567");
    expect(body.student_identifier).toBe("1012345678");
    expect(screen.queryByText("أحمد محمد")).toBeNull();
  });
  it("checks fragment activation without consuming it or exposing token in URL or storage", async () => {
    const token = "t".repeat(48);
    window.history.replaceState({}, "", `/parent/activate#token=${token}`);
    const setItem = vi.spyOn(Storage.prototype, "setItem");
    const { calls } = mockApi({
      "/auth/me/": UNAUTHENTICATED,
      "/parent/activation/check/": {
        body: {
          status: "VALID",
          school_name: "مدرسة النور",
          requires_login: false,
          account_exists: false,
        },
      },
    });
    renderApp("/parent/activate");
    expect(
      await screen.findByLabelText("كلمة المرور الجديدة"),
    ).toBeInTheDocument();
    expect(window.location.hash).toBe("");
    expect(calls.some((call) => call.url.includes(token))).toBe(false);
    expect(calls.some((call) => call.url.endsWith("/parent/activation/"))).toBe(
      false,
    );
    expect(
      JSON.parse(
        String(
          calls.find((call) => call.url.includes("/activation/check/"))?.init
            ?.body,
        ),
      ),
    ).toEqual({ token });
    expect(setItem).not.toHaveBeenCalled();
    setItem.mockRestore();
  });
  it("existing account activation requests current login and never asks to reset password", async () => {
    window.history.replaceState(
      {},
      "",
      `/parent/activate#token=${"t".repeat(48)}`,
    );
    mockApi({
      "/auth/me/": UNAUTHENTICATED,
      "/parent/activation/check/": {
        body: {
          status: "VALID",
          school_name: "مدرسة النور",
          requires_login: true,
          account_exists: true,
        },
      },
    });
    renderApp("/parent/activate");
    expect(
      await screen.findByLabelText("كلمة المرور الحالية"),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText("كلمة المرور الجديدة")).toBeNull();
    expect(screen.queryByLabelText("تأكيد كلمة المرور")).toBeNull();
  });
  it("asks for the owning account login even while another user is signed in", async () => {
    window.history.replaceState({}, "", `/parent/activate#token=${"t".repeat(48)}`);
    const { calls } = mockApi({
      "/auth/me/": { body: STAFF_PARENT },
      "/parent/activation/check/": { body: { status: "VALID", school_name: "مدرسة النور", requires_login: true, account_exists: true } },
    });
    renderApp("/parent/activate");
    expect(await screen.findByLabelText("كلمة المرور الحالية")).toBeInTheDocument();
    expect(screen.queryByLabelText("كلمة المرور الجديدة")).toBeNull();
    expect(screen.queryByRole("button", { name: "ربط الابن بحسابي" })).toBeNull();
    expect(calls.some((call) => call.url.endsWith("/parent/activation/"))).toBe(false);
  });
  it("counselor staff administration exposes only explicit family publication actions", async () => {
    mockApi({
      "/auth/me/": {
        body: buildMe({
          active_school: { id: 10, name: "مدرسة النور", slug: "noor" },
          roles: ["COUNSELOR"],
          memberships: [membership(1, 10, "مدرسة النور", ["COUNSELOR"])],
        }),
      },
      "/staff/parents/publications/": {
        body: {
          items: [
            {
              id: 6,
              title: "توصية الحالة المسندة",
              body: "محتوى مصرح للأسرة",
              required_action: "",
              due_at: null,
              document: null,
              published_at: `${DATE}T05:00:00Z`,
              acknowledged_at: null,
              ack_count: 1,
              acknowledgements: [
                {
                  relation_id: 11,
                  parent_name: "ولي الأمر ••••4567",
                  acknowledged_at: `${DATE}T06:00:00Z`,
                },
              ],
            },
          ],
        },
      },
    });
    renderApp("/parent-management");
    expect(
      await screen.findByLabelText("المحتوى المصرح بنشره"),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "طلبات التسجيل" })).toBeNull();
    expect(screen.queryByRole("button", { name: "مراجعة التواصل" })).toBeNull();
    expect(
      screen.getByLabelText("رقم الحالة الإرشادية المسندة"),
    ).toBeRequired();
    const user = userEvent.setup();
    await user.click(await screen.findByText("تأكيدات الاطلاع: 1"));
    expect(await screen.findByText(/ولي الأمر ••••4567/)).toBeVisible();
    expect(
      screen.queryByRole("button", { name: "تأكيدات الاطلاع" }),
    ).toBeNull();
  });
  it("lets school administrators review paginated explicit acknowledgements without changing them", async () => {
    const manager = buildMe({
      active_school: { id: 10, name: "مدرسة النور", slug: "noor" },
      roles: ["SCHOOL_MANAGER"],
      memberships: [membership(1, 10, "مدرسة النور", ["SCHOOL_MANAGER"])],
    });
    const { calls } = mockApi({
      "/auth/me/": { body: manager },
      "/staff/parents/registrations/": { body: { results: [] } },
      "/staff/parents/acknowledgements/": {
        body: {
          items: [
            {
              id: 9,
              type: "WARNING",
              student_name: "أحمد محمد",
              parent_name: "ولي الأمر ••••4567",
              acknowledged_at: `${DATE}T06:00:00Z`,
              target_id: 4,
              relation_id: 11,
              student_id: 5,
            },
          ],
          count: 26,
          next: "https://untrusted.example?page=2",
          previous: null,
        },
      },
    });
    renderApp("/parent-management");
    const user = userEvent.setup();
    await user.click(
      await screen.findByRole("button", {
        name: "تأكيدات الاطلاع",
      }),
    );
    expect(await screen.findByRole("table")).toHaveTextContent("أحمد محمد");
    expect(screen.getByRole("table")).toHaveTextContent("ولي الأمر ••••4567");
    expect(screen.getByRole("table")).toHaveTextContent("إنذار #4");
    await user.click(screen.getByRole("button", { name: "التالي" }));
    await waitFor(() =>
      expect(
        calls.some(
          (call) =>
            call.url === "/api/v1/staff/parents/acknowledgements/?page=2",
        ),
      ).toBe(true),
    );
    expect(calls.some((call) => call.init?.method === "POST")).toBe(false);
    expect(calls.some((call) => call.url.includes("untrusted.example"))).toBe(
      false,
    );
  });
  it("school settings present registration QR and the live backend statistics", async () => {
    mockApi({
      "/auth/me/": {
        body: buildMe({
          active_school: { id: 10, name: "مدرسة النور", slug: "noor" },
          roles: ["SCHOOL_MANAGER"],
          memberships: [membership(1, 10, "مدرسة النور", ["SCHOOL_MANAGER"])],
        }),
      },
      "/staff/parents/settings/": {
        body: {
          enabled: true,
          registration_url:
            "http://localhost/parent/register/11111111-1111-4111-8111-111111111111",
          stats: { registered_parents: 7, coverage_percent: 25 },
        },
      },
    });
    renderApp("/settings?section=parents");
    expect(await screen.findByLabelText("رابط التسجيل")).toHaveValue(
      "http://localhost/parent/register/11111111-1111-4111-8111-111111111111",
    );
    expect(
      screen.getByLabelText("رمز QR لتسجيل أولياء الأمور"),
    ).toBeInTheDocument();
    expect(screen.getByText("25%")).toBeInTheDocument();
  });
  it("shows failed SMS approval and safe activation history without assuming delivery", async () => {
    const registration = {
      id: 91,
      name: "محمد الأب",
      mobile: "+966551234567",
      relationship_type: "FATHER",
      status: "PENDING",
      created_at: `${DATE}T05:00:00Z`,
    };
    const manager = buildMe({
      active_school: { id: 10, name: "مدرسة النور", slug: "noor" },
      roles: ["SCHOOL_MANAGER"],
      memberships: [membership(1, 10, "مدرسة النور", ["SCHOOL_MANAGER"])],
    });
    const { calls } = mockApi({
      "/auth/me/": { body: manager },
      "/staff/parents/registrations/91/decision/": {
        body: {
          request: { ...registration, status: "APPROVED" },
          delivery_status: "FAILED",
        },
      },
      "/staff/parents/registrations/91/": {
        body: {
          request: registration,
          student_match: { id: 5, full_name: "أحمد محمد" },
          sibling_candidates: [],
          existing_relations: [],
          activations: [
            {
              id: 7,
              delivery_status: "UNKNOWN",
              failure_code: "NETWORK_TIMEOUT",
              created_at: `${DATE}T05:00:00Z`,
              expires_at: `${DATE}T06:00:00Z`,
              used_at: null,
              revoked_at: null,
            },
          ],
        },
      },
      "/staff/parents/registrations/": {
        body: { results: [registration], count: 1, next: null, previous: null },
      },
    });
    renderApp("/parent-management");
    const user = userEvent.setup();
    await user.click(
      await screen.findByRole("button", { name: "مراجعة الطلب #91" }),
    );
    expect(
      await screen.findByRole("region", { name: "سجل تسليم التفعيل" }),
    ).toHaveTextContent("نتيجة إرسال التفعيل غير مؤكدة");
    await user.selectOptions(
      screen.getByLabelText("الطالب الذي تعتمد علاقته"),
      "5",
    );
    await user.type(
      screen.getByLabelText("توثيق التحقق من الهوية والصفة"),
      "تحقق حضوري من الأب والهوية",
    );
    await user.click(screen.getByRole("button", { name: "حفظ القرار" }));
    expect(
      await screen.findByText("تعذر إرسال رسالة التفعيل"),
    ).toBeInTheDocument();
    expect(screen.getByText(/لا توجد إعادة إرسال تلقائية/)).toBeInTheDocument();
    expect(screen.queryByLabelText("رابط التفعيل")).toBeNull();
    expect(
      calls.filter((call) => call.url.includes("/91/decision/")).length,
    ).toBe(1);
  });
  it("shows unknown SMS reissue as an uncertain result and never retries automatically", async () => {
    const manager = buildMe({
      active_school: { id: 10, name: "مدرسة النور", slug: "noor" },
      roles: ["SCHOOL_MANAGER"],
      memberships: [membership(1, 10, "مدرسة النور", ["SCHOOL_MANAGER"])],
    });
    const { calls } = mockApi({
      "/auth/me/": { body: manager },
      "/staff/parents/registrations/91/activation/": {
        body: { delivery_status: "UNKNOWN" },
      },
      "/staff/parents/registrations/": { body: { results: [] } },
    });
    renderApp("/parent-management");
    const user = userEvent.setup();
    await user.click(await screen.findByText("إعادة تسليم التفعيل لطلب معتمد"));
    await user.type(screen.getByLabelText("رقم طلب التسجيل المعتمد"), "91");
    await user.type(
      screen.getByLabelText("توثيق التحقق الحديث من صاحب الصفة"),
      "تحقق حديث حضوري",
    );
    await user.click(
      screen.getByRole("button", { name: "إصدار وتسليم تفعيل جديد" }),
    );
    expect(
      await screen.findByText("نتيجة إرسال التفعيل غير مؤكدة"),
    ).toBeInTheDocument();
    expect(screen.getByText(/لا توجد إعادة إرسال تلقائية/)).toBeInTheDocument();
    expect(
      calls.filter((call) => call.url.includes("/91/activation/")).length,
    ).toBe(1);
  });
  it("changes the global account password with current credentials and clears password fields", async () => {
    const { calls } = mockApi({
      "/auth/me/": { body: PARENT },
      "/parent/account/password/": {
        body: { message: "تم تغيير كلمة المرور" },
      },
    });
    renderApp("/parent/account");
    const user = userEvent.setup();
    await user.type(
      await screen.findByLabelText("كلمة المرور الحالية للحساب"),
      "Current-Password!",
    );
    await user.type(
      screen.getByLabelText("كلمة المرور الجديدة للحساب"),
      "Next-Password-Safe!",
    );
    await user.type(
      screen.getByLabelText("تأكيد كلمة المرور الجديدة للحساب"),
      "Next-Password-Safe!",
    );
    await user.click(screen.getByRole("button", { name: "حفظ كلمة المرور" }));
    expect(await screen.findByText("تم تغيير كلمة المرور")).toBeInTheDocument();
    expect(screen.getByLabelText("كلمة المرور الحالية للحساب")).toHaveValue("");
    expect(screen.getByLabelText("كلمة المرور الجديدة للحساب")).toHaveValue("");
    expect(
      JSON.parse(
        String(
          calls.find((call) => call.url.includes("/account/password/"))?.init
            ?.body,
        ),
      ),
    ).toEqual({
      current_password: "Current-Password!",
      new_password: "Next-Password-Safe!",
      confirm_password: "Next-Password-Safe!",
    });
  });
  it("paginates children without following arbitrary server-provided absolute URLs", async () => {
    const { calls } = mockApi({
      "/auth/me/": { body: PARENT },
      "/parent/children/": (init) => ({
        body: {
          results: [CHILD],
          count: 40,
          next: "https://untrusted.example/?page=2",
          previous: null,
          method: init?.method,
        },
      }),
    });
    renderApp("/parent");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "التالي" }));
    await waitFor(() =>
      expect(
        calls.some((call) => call.url === "/api/v1/parent/children/?page=2"),
      ).toBe(true),
    );
    expect(calls.some((call) => call.url.includes("untrusted.example"))).toBe(
      false,
    );
  });
  it("published content requires explicit acknowledgement and never calls staff counseling APIs", async () => {
    const { calls } = mockApi({
      "/auth/me/": { body: PARENT },
      "/parent/children/11/publications/": {
        body: {
          items: [
            {
              id: 19,
              title: "توجيه للأسرة",
              body: "محتوى مصرح محدد",
              required_action: "",
              due_at: null,
              published_at: `${DATE}T05:00:00Z`,
              acknowledged_at: null,
              document: null,
            },
          ],
        },
      },
      "/parent/children/11/": { body: DETAIL },
    });
    renderApp("/parent/children/11");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("tab", { name: "رسائل المدرسة" }));
    await screen.findByRole("heading", { name: "توجيه للأسرة" });
    expect(calls.some((call) => call.url.includes("/acknowledge/"))).toBe(
      false,
    );
    expect(
      calls.some(
        (call) =>
          call.url.includes("/counselor/") || call.url.includes("/referrals/"),
      ),
    ).toBe(false);
    await user.click(
      screen.getByRole("button", { name: "تأكيد الاطلاع على الرسالة" }),
    );
    await waitFor(() =>
      expect(
        calls.some((call) =>
          call.url.includes("/publications/19/acknowledge/"),
        ),
      ).toBe(true),
    );
  });
});
