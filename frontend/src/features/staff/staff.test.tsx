import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import { queryClient } from "@/app/queryClient";
import { buildMe, membership, mockApi, UNAUTHENTICATED } from "@/test/mockApi";
import { renderApp } from "@/test/renderApp";

function meWithRoles(roles: ("SCHOOL_MANAGER" | "TEACHER" | "VICE_PRINCIPAL")[]) {
  return buildMe({
    active_school: { id: 10, name: "ثانوية الأندلس", slug: "andalus" },
    roles,
    memberships: [membership(1, 10, "ثانوية الأندلس", roles)],
  });
}

const STAFF_PAGE = {
  count: 2,
  next: null,
  previous: null,
  results: [
    {
      id: 1, display_name: "أحمد الغامدي", employee_number: "T-1", job_title: "معلم",
      mobile: "+9665****0001", roles: ["TEACHER"], membership_status: "ACTIVE",
      joined_at: "2026-08-18", is_active: true,
    },
    {
      id: 2, display_name: "فهد المرشد", employee_number: null, job_title: "",
      mobile: "+9665****0004", roles: ["COUNSELOR", "TEACHER"],
      membership_status: "ACTIVE", joined_at: "2026-08-18", is_active: true,
    },
  ],
};

describe("StaffPage", () => {
  beforeEach(() => {
    queryClient.clear();
    document.cookie = "csrftoken=test-token";
  });

  it("manager sees directory with masked mobiles, roles and import button", async () => {
    mockApi({
      "/auth/me/": { body: meWithRoles(["SCHOOL_MANAGER"]) },
      "/staff/": { body: STAFF_PAGE },
    });
    renderApp("/staff");
    expect(await screen.findByText("أحمد الغامدي")).toBeInTheDocument();
    expect(screen.getByText("+9665****0001")).toBeInTheDocument();
    expect(screen.getAllByText("المرشد الطلابي").length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "استيراد" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "إدخال يدوي" })).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "إدارة" }).length).toBe(2);
  });

  it("vice principal reads directory without import or manage controls", async () => {
    mockApi({
      "/auth/me/": { body: meWithRoles(["VICE_PRINCIPAL"]) },
      "/staff/": { body: STAFF_PAGE },
    });
    renderApp("/staff");
    expect(await screen.findByText("أحمد الغامدي")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "استيراد" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "إدخال يدوي" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "إدارة" })).not.toBeInTheDocument();
  });

  it("adds staff manually and shows the one-time password", async () => {
    mockApi({
      "/auth/me/": { body: meWithRoles(["SCHOOL_MANAGER"]) },
      "/staff/": (init) => init?.method === "POST"
        ? { status: 201, body: { ...STAFF_PAGE.results[0], id: 12, display_name: "معلم يدوي", temporary_password: "Temp-pass-9", invitation_sent: false } }
        : { body: STAFF_PAGE },
    });
    renderApp("/staff");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "إدخال يدوي" }));
    await user.type(screen.getByLabelText("اسم الموظف الكامل *"), "معلم يدوي");
    await user.type(screen.getByLabelText("رقم الجوال *"), "0557771111");
    await user.click(screen.getByRole("button", { name: "إضافة الموظف" }));
    expect(await screen.findByText("Temp-pass-9")).toBeInTheDocument();
    expect(screen.getByText(/تظهر مرة واحدة فقط/)).toBeInTheDocument();
  });

  it("confirms suspending a staff member before disabling access", async () => {
    const api = mockApi({
      "/staff/1/suspend/": { body: { ...STAFF_PAGE.results[0], membership_status: "SUSPENDED" } },
      "/auth/me/": { body: meWithRoles(["SCHOOL_MANAGER"]) },
      "/staff/": { body: STAFF_PAGE },
    });
    renderApp("/staff");
    const user = userEvent.setup();
    await user.click((await screen.findAllByRole("button", { name: "إدارة" }))[0]!);
    await user.click(screen.getByRole("button", { name: "تعطيل الموظف" }));
    const dialog = screen.getByRole("dialog", { name: /تعطيل أحمد الغامدي/ });
    expect(within(dialog).getByText(/يمكن إعادة تفعيل الموظف لاحقًا/)).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "تأكيد التعطيل" }));
    await waitFor(() => expect(api.calls.some((call) => call.url.includes("/staff/1/suspend/") && call.init?.method === "POST")).toBe(true));
  });

  it("manager resets a teacher password to the mobile and sees the forced-change notice", async () => {
    const api = mockApi({
      "/staff/1/reset-password/": {
        body: { temporary_password: "0550000001", must_change_password: true },
      },
      "/auth/me/": { body: meWithRoles(["SCHOOL_MANAGER"]) },
      "/staff/": { body: STAFF_PAGE },
    });
    renderApp("/staff");
    const user = userEvent.setup();

    await user.click((await screen.findAllByRole("button", { name: "إدارة" }))[0]!);
    await user.click(screen.getByRole("button", { name: "إعادة ضبط كلمة المرور" }));
    const dialog = screen.getByRole("dialog", { name: /إعادة ضبط كلمة مرور أحمد الغامدي/ });
    expect(within(dialog).getByText(/ستصبح كلمة المرور المؤقتة هي رقم جوال المعلم/)).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "تأكيد إعادة الضبط" }));

    await waitFor(() => expect(api.calls.some((call) => call.url.includes("/staff/1/reset-password/") && call.init?.method === "POST")).toBe(true));
    expect(await screen.findByText("0550000001")).toBeInTheDocument();
    expect(screen.getByText(/سيُطلب من المعلم تغييرها فور تسجيل الدخول/)).toBeInTheDocument();
  });

  it("manager updates the teacher profile from the directory", async () => {
    let patchBody: Record<string, unknown> | null = null;
    const api = mockApi({
      "/staff/1/": (init) => {
        patchBody = JSON.parse(String(init?.body)) as Record<string, unknown>;
        return { body: { ...STAFF_PAGE.results[0], display_name: "أحمد المصحح", job_title: "معلم علوم" } };
      },
      "/auth/me/": { body: meWithRoles(["SCHOOL_MANAGER"]) },
      "/staff/": { body: STAFF_PAGE },
    });
    renderApp("/staff");
    const user = userEvent.setup();
    await user.click((await screen.findAllByRole("button", { name: "إدارة" }))[0]!);
    await user.click(screen.getByRole("button", { name: "تعديل البيانات" }));
    const name = screen.getByLabelText("الاسم الكامل *");
    await user.clear(name);
    await user.type(name, "أحمد المصحح");
    const title = screen.getByLabelText("المسمى الوظيفي");
    await user.clear(title);
    await user.type(title, "معلم علوم");
    await user.click(screen.getByRole("button", { name: "حفظ البيانات" }));

    await waitFor(() => expect(api.calls.some((call) => call.url.includes("/staff/1/") && call.init?.method === "PATCH")).toBe(true));
    expect(patchBody).toMatchObject({ display_name: "أحمد المصحح", job_title: "معلم علوم" });
  });

  it("manager assigns morning follow-up without changing the employee role", async () => {
    const api = mockApi({
      "/staff/1/morning-attendance/": {
        body: { ...STAFF_PAGE.results[0], capabilities: ["MORNING_ATTENDANCE"] },
      },
      "/auth/me/": { body: meWithRoles(["SCHOOL_MANAGER"]) },
      "/staff/": { body: STAFF_PAGE },
    });
    renderApp("/staff");
    const user = userEvent.setup();
    await user.click((await screen.findAllByRole("button", { name: "إدارة" }))[0]!);
    const assignment = screen.getByTestId("morning-assignment-1");
    expect(assignment).toHaveTextContent("متاح للمعلم أو الوكيل أو المرشد أو الحارس");
    await user.click(within(assignment).getByRole("button", { name: "تكليف بالمتابعة" }));
    await waitFor(() => expect(api.calls.some((call) =>
      call.url.includes("/staff/1/morning-attendance/") && call.init?.method === "POST",
    )).toBe(true));
    expect(STAFF_PAGE.results[0]!.roles).toEqual(["TEACHER"]);
  });

  it.each([
    ["VICE_PRINCIPAL", "وكيل المدرسة", 31],
    ["COUNSELOR", "المرشد الطلابي", 32],
    ["GATE_GUARD", "حارس البوابة", 33],
  ] as const)("manager can assign morning follow-up to %s", async (role, name, id) => {
    const member = {
      id,
      display_name: name,
      employee_number: null,
      job_title: "",
      mobile: "+9665****0031",
      roles: [role],
      capabilities: [],
      membership_status: "ACTIVE",
      joined_at: "2026-08-18",
      is_active: true,
    };
    const api = mockApi({
      [`/staff/${id}/morning-attendance/`]: {
        body: { ...member, capabilities: ["MORNING_ATTENDANCE"] },
      },
      "/auth/me/": { body: meWithRoles(["SCHOOL_MANAGER"]) },
      "/staff/": { body: { count: 1, next: null, previous: null, results: [member] } },
    });
    renderApp("/staff");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "إدارة" }));
    const assignment = screen.getByTestId(`morning-assignment-${id}`);
    await user.click(within(assignment).getByRole("button", { name: "تكليف بالمتابعة" }));
    await waitFor(() => expect(api.calls.some((call) =>
      call.url.includes(`/staff/${id}/morning-attendance/`) && call.init?.method === "POST",
    )).toBe(true));
    expect(member.roles).toEqual([role]);
  });

  it("confirms revoking morning follow-up without removing employee duties", async () => {
    const assignedStaff = {
      ...STAFF_PAGE,
      results: [
        { ...STAFF_PAGE.results[0]!, capabilities: ["MORNING_ATTENDANCE"] },
        STAFF_PAGE.results[1]!,
      ],
    };
    const api = mockApi({
      "/staff/1/morning-attendance/": {
        body: { ...STAFF_PAGE.results[0], capabilities: [] },
      },
      "/auth/me/": { body: meWithRoles(["SCHOOL_MANAGER"]) },
      "/staff/": { body: assignedStaff },
    });
    renderApp("/staff");
    const user = userEvent.setup();
    await user.click((await screen.findAllByRole("button", { name: "إدارة" }))[0]!);
    const assignment = screen.getByTestId("morning-assignment-1");
    await user.click(within(assignment).getByRole("button", { name: "سحب التكليف" }));

    const dialog = screen.getByRole("dialog", { name: /سحب تكليف التأخر الصباحي من أحمد الغامدي/ });
    expect(within(dialog).getByText(/ستبقى أدوار الموظف ومهامه الأصلية دون تغيير/)).toBeInTheDocument();
    expect(api.calls.some((call) => call.init?.method === "DELETE")).toBe(false);

    await user.click(within(dialog).getByRole("button", { name: "تأكيد سحب التكليف" }));
    await waitFor(() => expect(api.calls.some((call) =>
      call.url.includes("/staff/1/morning-attendance/") && call.init?.method === "DELETE",
    )).toBe(true));
  });

  it("requires typing the employee name before permanent deletion", async () => {
    const api = mockApi({
      "/staff/1/": { body: {} },
      "/auth/me/": { body: meWithRoles(["SCHOOL_MANAGER"]) },
      "/staff/": { body: STAFF_PAGE },
    });
    renderApp("/staff");
    const user = userEvent.setup();
    await user.click((await screen.findAllByRole("button", { name: "إدارة" }))[0]!);
    await user.click(screen.getByRole("button", { name: "حذف نهائي" }));
    const dialog = screen.getByRole("dialog", { name: /حذف أحمد الغامدي نهائيًا/ });
    const deleteButton = within(dialog).getByRole("button", { name: "حذف نهائي" });
    expect(deleteButton).toBeDisabled();
    await user.type(within(dialog).getByLabelText(/للتأكيد اكتب اسم الموظف/), "أحمد الغامدي");
    expect(deleteButton).toBeEnabled();
    await user.click(deleteButton);
    await waitFor(() => expect(api.calls.some((call) => call.url.includes("/staff/1/") && call.init?.method === "DELETE")).toBe(true));
  });

  it("يعيد المعلم من رابط الموظفين إلى مساحة عمله ولا يعرض رابط الدليل", async () => {
    mockApi({ "/auth/me/": { body: meWithRoles(["TEACHER"]) } });
    renderApp("/staff");
    await screen.findByTestId("active-school-name");
    expect(screen.queryByRole("link", { name: "الموظفون" })).not.toBeInTheDocument();
    expect(screen.queryByTestId("staff-page")).not.toBeInTheDocument();
  });
});

describe("StaffImportWizard", () => {
  beforeEach(() => {
    queryClient.clear();
    document.cookie = "csrftoken=test-token";
  });

  const UPLOADED = {
    id: 7, status: "UPLOADED", original_filename: "staff.xlsx",
    header_row: 15,
    headers: ["اسم المعلم", "رقم الجوال"],
    suggested_mapping: { full_name: 0, mobile: 1 },
    total_rows: 0, invalid_rows: 0, duplicate_rows: 0, summary: {}, error_code: "",
  };
  const READY = {
    ...UPLOADED, status: "READY_FOR_REVIEW", total_rows: 2,
    summary: { new: 1, invite: 1, add_role: 0, profile_update: 0, unchanged: 0,
               invitation_pending: 0, manual: 0, errors: 0, duplicates: 0 },
  };

  it("full flow shows one-time credentials in the result", async () => {
    mockApi({
      "/staff-imports/7/process/": { body: READY },
      "/staff-imports/7/preview/": {
        body: {
          count: 2, next: null, previous: null,
          results: [
            { row_number: 2, status: "NEW",
              data: { full_name: "معلم جديد", mobile_masked: "+9665****9001" },
              error_codes: [], error_message: "" },
            { row_number: 3, status: "EXISTING_USER_INVITE",
              data: { full_name: "موجود", mobile_masked: "+9665****9002" },
              error_codes: [], error_message: "" },
          ],
        },
      },
      "/staff-imports/7/commit/": {
        body: {
          ...READY, status: "COMPLETED",
          summary: { ...READY.summary, created: 1, invited: 1, roles_added: 0,
                     profiles_updated: 0 },
          new_credentials: [
            { name: "معلم جديد", mobile_masked: "+9665****9001",
              temporary_password: "Xy9-secret12" },
          ],
        },
      },
      "/staff-imports/7/": { body: READY },
      "/staff-imports/": { status: 201, body: UPLOADED },
      "/auth/me/": { body: meWithRoles(["SCHOOL_MANAGER"]) },
    });

    renderApp("/staff/import");
    const user = userEvent.setup();
    const file = new File([new Uint8Array([80, 75, 3, 4])], "staff.xlsx");
    await user.upload(
      (await screen.findByTestId("staff-file-input")) as HTMLInputElement, file,
    );
    await user.click(screen.getByRole("button", { name: "رفع الملف" }));

    expect(await screen.findByText("مطابقة الأعمدة")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("الصف 15");
    await user.click(screen.getByRole("button", { name: "بدء التحليل" }));

    expect(await screen.findByRole("tab", { name: "معلمون جدد (1)" })).toBeInTheDocument();
    expect(
      screen.getByRole("tab", { name: "حسابات موجودة — دعوة (1)" }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "متابعة إلى التأكيد" }));

    expect(await screen.findByTestId("staff-confirm-summary")).toHaveTextContent(
      "حسابات معلمين جدد: 1",
    );
    await user.click(screen.getByRole("button", { name: "اعتماد الاستيراد" }));

    const credentials = await screen.findByTestId("new-credentials");
    expect(credentials).toHaveTextContent("Xy9-secret12");
    expect(credentials).toHaveTextContent("مرة واحدة فقط");
  });
});

describe("Invitations & initial password", () => {
  beforeEach(() => {
    queryClient.clear();
    document.cookie = "csrftoken=test-token";
  });

  it("pending invitation shown on select-school and accept adds the school", async () => {
    const withInvite = buildMe({
      memberships: [membership(1, 10, "ثانوية الأندلس", ["TEACHER"])],
      invitations: [
        { id: 5, school: { id: 20, name: "مدارس الرواد", slug: "rowad" }, roles: ["TEACHER"] },
      ],
    });
    const afterAccept = buildMe({
      memberships: [
        membership(1, 10, "ثانوية الأندلس", ["TEACHER"]),
        membership(5, 20, "مدارس الرواد", ["TEACHER"]),
      ],
    });
    mockApi({
      "/auth/invitations/5/accept/": { body: afterAccept },
      "/auth/me/": { body: withInvite },
    });
    renderApp("/select-school");
    const user = userEvent.setup();

    const invitations = await screen.findByTestId("invitations-section");
    expect(invitations).toHaveTextContent("مدارس الرواد");
    await user.click(screen.getByRole("button", { name: "قبول" }));

    await waitFor(() => {
      expect(screen.queryByTestId("invitations-section")).not.toBeInTheDocument();
    });
    // المدرستان أصبحتا متاحتين للدخول
    expect(screen.getAllByRole("button", { name: "دخول" }).length).toBe(2);
  });

  it("must_change_password forces the change screen before the app", async () => {
    mockApi({
      "/auth/me/": { body: buildMe({ must_change_password: true }) },
    });
    renderApp("/");
    expect(
      await screen.findByRole("heading", { name: "تغيير كلمة المرور" }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("كلمة المرور الجديدة")).toBeInTheDocument();
  });

  it("unauthenticated user on change-password goes to login", async () => {
    mockApi({ "/auth/me/": UNAUTHENTICATED });
    renderApp("/change-password");
    expect(await screen.findByRole("button", { name: "تسجيل الدخول" })).toBeInTheDocument();
  });
});
