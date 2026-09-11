import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import { queryClient } from "@/app/queryClient";
import { buildMe, membership, mockApi } from "@/test/mockApi";
import { renderApp } from "@/test/renderApp";

const SCHOOL = { id: 7, name: "مدرسة النور", slug: "school-7" };
const USAGE = {
  students: { used: 120, limit: 100, over_limit: true, remaining: 0 },
  staff: { used: 10, limit: 20, over_limit: false, remaining: 10 },
  devices: { used: 4, limit: 2, over_limit: true, remaining: 0 },
  storage: { used: 966367642, limit: 1073741824, over_limit: false, near_limit: true, remaining: 107374182, used_gb: 0.9, limit_gb: 1 },
};
const PLAN = {
  id: 1,
  code: "basic",
  name_ar: "الأساسية",
  name_en: "Basic",
  description: "",
  is_active: true,
  is_public: false,
  billing_period: "ANNUAL",
  price_amount: "100.00",
  currency: "SAR",
  trial_days_default: 30,
  entitlements: { MAX_STUDENTS: 100, MAX_STAFF: 20, MAX_DEVICES: 2, MAX_STORAGE_GB: 1 },
};

describe("platform and subscription UI", () => {
  beforeEach(() => {
    queryClient.clear();
  });

  it("shows the platform dashboard for platform admins", async () => {
    mockApi({
      "/auth/me/": {
        body: buildMe({ is_platform_admin: true, name: "مشرف المنصة" }),
      },
      "/platform/overview/": {
        body: {
          schools_total: 12,
          subscriptions: { active: 8, trial: 2, grace: 1, expired: 1, suspended: 3 },
          usage_totals: { active_students: 900, active_staff: 70, active_devices: 16 },
          expiring_soon: [{ school_id: 1, school_name: "مدرسة", plan: "pro", ends_at: "2026-09-01T00:00:00Z", days_remaining: 12 }],
        },
      },
      "/platform/plans/": { body: [] },
    });

    renderApp("/platform");

    const heading = await screen.findByRole("heading", { name: "إدارة المنصة" });
    expect(heading).toBeInTheDocument();
    expect(heading.closest("main")).toHaveClass("px-4", "sm:px-6", "lg:px-8");
    expect(await screen.findByText("12")).toBeInTheDocument();
    expect(screen.getByText("900")).toBeInTheDocument();
  });

  it.each(["/", "/select-school"])(
    "redirects platform admins from school route %s to the platform console",
    async (path) => {
      mockApi({
        "/auth/me/": {
          body: buildMe({ is_platform_admin: true, name: "مشرف المنصة" }),
        },
        "/platform/overview/": {
          body: {
            schools_total: 0,
            subscriptions: { active: 0, trial: 0, grace: 0, expired: 0, suspended: 0 },
            usage_totals: { active_students: 0, active_staff: 0, active_devices: 0 },
            expiring_soon: [],
          },
        },
        "/platform/plans/": { body: [] },
      });

      renderApp(path);

      expect(await screen.findByRole("heading", { name: "إدارة المنصة" })).toBeInTheDocument();
      expect(screen.queryByRole("heading", { name: "لا توجد مدارس مرتبطة بحسابك" })).not.toBeInTheDocument();
    },
  );

  it("keeps school managers out of the platform area", async () => {
    mockApi({
      "/auth/me/": {
        body: buildMe({
          active_school: SCHOOL,
          roles: ["SCHOOL_MANAGER"],
          memberships: [membership(1, SCHOOL.id, SCHOOL.name, ["SCHOOL_MANAGER"])],
        }),
      },
    });

    renderApp("/platform");

    expect(await screen.findByTestId("active-school-name")).toHaveTextContent(SCHOOL.name);
    expect(screen.queryByRole("heading", { name: "إدارة المنصة" })).not.toBeInTheDocument();
  });

  it("creates a girls school, manager, and active subscription in one guided form", async () => {
    const user = userEvent.setup();
    const { calls } = mockApi({
      "/auth/me/": { body: buildMe({ is_platform_admin: true }) },
      "/platform/overview/": {
        body: { schools_total: 0, subscriptions: {}, usage_totals: {}, expiring_soon: [] },
      },
      "/platform/plans/": { body: [PLAN] },
      "/platform/schools/": (init) => init?.method === "POST"
        ? { status: 400, body: { code: "TEST", message: "test", details: {} } }
        : { body: { count: 0, next: null, previous: null, results: [] } },
    });

    renderApp("/platform");
    await user.click(await screen.findByRole("button", { name: "المدارس" }));
    await user.click(screen.getByRole("button", { name: "إضافة مدرسة جديدة" }));
    const createButton = screen.getByRole("button", { name: "إنشاء المدرسة بدون اشتراك" });
    expect(createButton).toBeDisabled();

    await user.selectOptions(screen.getByLabelText("نوع المدرسة الجديدة"), "GIRLS");
    expect(screen.getByPlaceholderText("اسم المديرة")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("جوال المديرة")).toBeInTheDocument();
    await user.type(screen.getByPlaceholderText("اسم المدرسة"), "ثانوية البنات");
    await user.type(screen.getByPlaceholderText("اسم المديرة"), "نورة");
    await user.type(screen.getByPlaceholderText("جوال المديرة"), "0550000000");
    await user.selectOptions(screen.getByLabelText("باقة الاشتراك عند الإنشاء"), "1");
    await user.selectOptions(screen.getByLabelText("نوع الاشتراك عند الإنشاء"), "ACTIVE");
    const duration = screen.getByLabelText("مدة الاشتراك عند الإنشاء");
    await user.clear(duration);
    await user.type(duration, "6");
    await user.click(screen.getByRole("button", { name: "إنشاء المدرسة والاشتراك" }));

    await waitFor(() => {
      const request = calls.find((call) => call.url.includes("/platform/schools/") && call.init?.method === "POST");
      expect(JSON.parse(String(request?.init?.body))).toMatchObject({
        school_type: "GIRLS",
        plan_id: 1,
        subscription_mode: "ACTIVE",
        months: 6,
      });
    });
  });

  it("shows expired subscription state and over-limit usage to school managers", async () => {
    mockApi({
      "/auth/me/": {
        body: buildMe({
          active_school: SCHOOL,
          roles: ["SCHOOL_MANAGER"],
          memberships: [membership(1, SCHOOL.id, SCHOOL.name, ["SCHOOL_MANAGER"])],
        }),
      },
      "/school/subscription/": {
        body: {
          subscription: {
            has_subscription: true,
            status: "EXPIRED",
            access_mode: "READ_ONLY",
            plan: { code: "basic", name: "الأساسية", billing_period: "ANNUAL" },
            starts_at: "2026-01-01T00:00:00Z",
            ends_at: "2026-08-01T00:00:00Z",
            days_remaining: 0,
            grace_ends_at: null,
            trial_ends_at: null,
          },
          usage: USAGE,
        },
      },
    });

    renderApp("/subscription");

    expect(await screen.findByRole("heading", { name: "اشتراك المدرسة" })).toBeInTheDocument();
    expect(screen.getAllByText("قراءة فقط").length).toBeGreaterThan(0);
    expect(screen.getAllByText("تجاوز الحد")).toHaveLength(2);
    expect(screen.getByText("قريب من الحد")).toBeInTheDocument();
  });

  it("shows suspended schools as blocked with preserved-data guidance", async () => {
    mockApi({
      "/auth/me/": {
        body: buildMe({
          active_school: SCHOOL,
          roles: ["SCHOOL_MANAGER"],
          memberships: [membership(1, SCHOOL.id, SCHOOL.name, ["SCHOOL_MANAGER"])],
        }),
      },
      "/school/subscription/": {
        body: {
          subscription: {
            has_subscription: true,
            status: "SUSPENDED",
            access_mode: "BLOCKED",
            plan: { code: "basic", name: "الأساسية", billing_period: "ANNUAL" },
            starts_at: "2026-01-01T00:00:00Z",
            ends_at: "2027-01-01T00:00:00Z",
            days_remaining: 120,
            grace_ends_at: null,
            trial_ends_at: null,
          },
          usage: USAGE,
        },
      },
    });

    renderApp("/subscription");

    expect((await screen.findAllByText("الوصول موقوف")).length).toBeGreaterThan(0);
    expect(screen.getByText(/البيانات محفوظة/)).toBeInTheDocument();
  });

  it("activates a subscription for an existing school from the simplified form", async () => {
    const user = userEvent.setup();
    const row = {
      id: SCHOOL.id,
      name: SCHOOL.name,
      slug: SCHOOL.slug,
      school_type: "BOYS",
      school_status: "ACTIVE",
      subscription_status: null,
      plan: null,
      plan_name: null,
      starts_at: null,
      ends_at: null,
      manager: { id: 4, name: "مدير النور" },
      usage: USAGE,
    };
    const { calls } = mockApi({
      "/auth/me/": { body: buildMe({ is_platform_admin: true }) },
      "/platform/overview/": { body: { schools_total: 1, subscriptions: {}, usage_totals: {}, expiring_soon: [] } },
      "/platform/plans/": { body: [PLAN] },
      "/platform/schools/7/subscription/activate/": { body: { id: 8, status: "ACTIVE" } },
      "/platform/schools/7/subscription/events/": { body: [] },
      "/platform/schools/7/subscription/": { body: { current: null, history: [] } },
      "/platform/schools/7/": {
        body: {
          ...row,
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
          managers: [],
          subscription: {
            has_subscription: false,
            status: null,
            access_mode: "BLOCKED",
            plan: null,
            starts_at: null,
            ends_at: null,
            days_remaining: null,
            grace_ends_at: null,
            trial_ends_at: null,
          },
          entitlements: {},
        },
      },
      "/platform/schools/": { body: { count: 1, next: null, previous: null, results: [row] } },
    });

    renderApp("/platform");
    await user.click(await screen.findByRole("button", { name: "المدارس" }));
    await user.click(await screen.findByRole("button", { name: new RegExp(SCHOOL.name) }));
    expect(await screen.findByLabelText("اسم المدير الجديد")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "تعيين مدير" })).toBeInTheDocument();
    await user.selectOptions(await screen.findByLabelText("الباقة الجديدة"), "1");
    const duration = screen.getByLabelText("المدة");
    await user.clear(duration);
    await user.type(duration, "6");
    await user.click(screen.getByRole("button", { name: "تفعيل اشتراك" }));

    await waitFor(() => {
      const request = calls.find((call) => call.url.includes("/subscription/activate/") && call.init?.method === "POST");
      expect(JSON.parse(String(request?.init?.body))).toMatchObject({ plan_id: 1, months: 6 });
    });
  });

  it("lists SaaS metadata, previews a safe downgrade, and runs suspension", async () => {
    const user = userEvent.setup();
    const row = {
      id: SCHOOL.id,
      name: SCHOOL.name,
      slug: SCHOOL.slug,
      school_status: "ACTIVE",
      subscription_status: "ACTIVE",
      plan: PLAN.code,
      plan_name: PLAN.name_ar,
      starts_at: "2026-01-01T00:00:00Z",
      ends_at: "2027-01-01T00:00:00Z",
      manager: { id: 4, name: "مدير النور" },
      usage: USAGE,
    };
    const { calls } = mockApi({
      "/auth/me/": { body: buildMe({ is_platform_admin: true }) },
      "/platform/overview/": {
        body: { schools_total: 1, subscriptions: {}, usage_totals: { active_students: 120, active_staff: 10, active_devices: 4 }, expiring_soon: [] },
      },
      "/platform/schools/7/subscription/plan-preview/": {
        body: {
          plan: { id: 1, code: "basic", name: "الأساسية" },
          impact: {
            students: { used: 120, new_limit: 100, over_limit: true },
            staff: { used: 10, new_limit: 20, over_limit: false },
            devices: { used: 4, new_limit: 2, over_limit: true },
            storage: { used_gb: 0, new_limit_gb: 1, over_limit: false },
          },
          deletes_data: false,
        },
      },
      "/platform/schools/7/subscription/suspend/": { body: { id: 8, status: "SUSPENDED" } },
      "/platform/schools/7/subscription/events/": { body: [{ id: 2, event_type: "ACTIVATED", reason: "", metadata: {}, created_at: "2026-01-01T00:00:00Z" }] },
      "/platform/schools/7/subscription/": { body: { current: null, history: [] } },
      "/platform/schools/7/": {
        body: {
          ...row,
          subscription: {
            has_subscription: true,
            status: "ACTIVE",
            access_mode: "FULL",
            plan: { code: "basic", name: "الأساسية", billing_period: "ANNUAL" },
            starts_at: row.starts_at,
            ends_at: row.ends_at,
            days_remaining: 100,
            grace_ends_at: null,
            trial_ends_at: null,
          },
          entitlements: {},
        },
      },
      "/platform/schools/": { body: { count: 1, next: null, previous: null, results: [row] } },
      "/platform/plans/": { body: [PLAN] },
    });

    renderApp("/platform");
    await user.click(await screen.findByRole("button", { name: "المدارس" }));
    const schoolButton = await screen.findByRole("button", { name: new RegExp(SCHOOL.name) });
    expect(schoolButton).toHaveTextContent("مدير النور");
    await user.click(schoolButton);
    await user.selectOptions(await screen.findByLabelText("إجراء الاشتراك"), "change-plan");
    await user.selectOptions(await screen.findByLabelText("الباقة الجديدة"), "1");
    expect(within(await screen.findByTestId("plan-change-preview")).getAllByText(/تجاوز الحد/)).toHaveLength(2);
    expect(screen.getByText("لن تُحذف أي بيانات.")).toBeInTheDocument();
    expect(screen.queryByText("بيانات ولي الأمر")).not.toBeInTheDocument();
    await user.click(screen.getByText("إجراءات متقدمة"));
    await user.click(screen.getByRole("button", { name: "إيقاف" }));
    await waitFor(() => {
      expect(calls.some(({ url, init }) => url.includes("/subscription/suspend/") && init?.method === "POST")).toBe(true);
    });
  });

  it("requires typing the exact school name before permanent deletion", async () => {
    const user = userEvent.setup();
    const row = {
      id: SCHOOL.id,
      name: SCHOOL.name,
      slug: SCHOOL.slug,
      school_type: "BOYS",
      school_status: "ACTIVE",
      subscription_status: null,
      plan: null,
      plan_name: null,
      starts_at: null,
      ends_at: null,
      manager: null,
      usage: USAGE,
    };
    const detail = {
      ...row,
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
      managers: [],
      subscription: {
        has_subscription: false,
        status: null,
        access_mode: "BLOCKED",
        plan: null,
        starts_at: null,
        ends_at: null,
        days_remaining: null,
        grace_ends_at: null,
        trial_ends_at: null,
      },
      entitlements: {},
    };
    const { calls } = mockApi({
      "/auth/me/": { body: buildMe({ is_platform_admin: true }) },
      "/platform/overview/": { body: { schools_total: 1, subscriptions: {}, usage_totals: {}, expiring_soon: [] } },
      "/platform/plans/": { body: [] },
      "/platform/schools/7/subscription/events/": { body: [] },
      "/platform/schools/7/subscription/": { body: { current: null, history: [] } },
      "/platform/schools/7/": (init) => init?.method === "DELETE"
        ? {
            body: {
              deleted: true,
              school_id: SCHOOL.id,
              school_name: SCHOOL.name,
              database_records_deleted: 30,
              user_accounts_deleted: 1,
              storage_objects_deleted: 2,
              storage_objects_failed: 0,
            },
          }
        : { body: detail },
      "/platform/schools/": { body: { count: 1, next: null, previous: null, results: [row] } },
    });

    renderApp("/platform");
    await user.click(await screen.findByRole("button", { name: "المدارس" }));
    await user.click(await screen.findByRole("button", { name: new RegExp(SCHOOL.name) }));
    await user.click(await screen.findByRole("button", { name: "حذف المدرسة نهائيًا" }));
    const confirmButton = screen.getByRole("button", { name: "تأكيد الحذف النهائي" });
    expect(confirmButton).toBeDisabled();

    await user.type(screen.getByLabelText("اكتب اسم المدرسة للتأكيد"), SCHOOL.name);
    expect(confirmButton).toBeEnabled();
    await user.click(confirmButton);

    await waitFor(() => {
      const request = calls.find(({ url, init }) => url.includes("/platform/schools/7/") && init?.method === "DELETE");
      expect(JSON.parse(String(request?.init?.body))).toEqual({
        confirmation_name: SCHOOL.name,
        acknowledge_permanent_deletion: true,
      });
    });
    expect(await screen.findByText(`حُذفت مدرسة ${SCHOOL.name} وجميع بياناتها نهائيًا.`)).toBeInTheDocument();
  });

  it("manages school profile, manager login credentials, and one-time password reset", async () => {
    const user = userEvent.setup();
    const manager = {
      membership_id: 41,
      user_id: 51,
      name: "مدير النور",
      mobile: "+966550123456",
      membership_status: "ACTIVE",
      account_active: true,
      must_change_password: false,
      last_login: "2026-09-01T10:00:00Z",
      joined_at: "2026-01-01T00:00:00Z",
      shared_with_other_schools: false,
    };
    const row = {
      id: SCHOOL.id,
      name: SCHOOL.name,
      slug: SCHOOL.slug,
      school_status: "ACTIVE",
      subscription_status: "ACTIVE",
      plan: PLAN.code,
      plan_name: PLAN.name_ar,
      starts_at: "2026-01-01T00:00:00Z",
      ends_at: "2027-01-01T00:00:00Z",
      manager: { id: manager.membership_id, name: manager.name },
      usage: USAGE,
    };
    const detail = {
      ...row,
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
      managers: [manager],
      subscription: {
        has_subscription: true,
        status: "ACTIVE",
        access_mode: "FULL",
        plan: { code: "basic", name: "الأساسية", billing_period: "ANNUAL" },
        starts_at: row.starts_at,
        ends_at: row.ends_at,
        days_remaining: 100,
        grace_ends_at: null,
        trial_ends_at: null,
      },
      entitlements: {},
    };
    const resetResult = {
      manager: { ...manager, must_change_password: true },
      temporary_password: "Xm-Reset-Once",
    };
    const { calls } = mockApi({
      "/platform/schools/7/managers/41/reset-password/": { body: resetResult },
      "/platform/schools/7/subscription/events/": { body: [] },
      "/platform/schools/7/subscription/": { body: { current: null, history: [] } },
      "/platform/schools/7/": { body: detail },
      "/platform/schools/": { body: { count: 1, next: null, previous: null, results: [row] } },
      "/platform/overview/": { body: { schools_total: 1, subscriptions: {}, usage_totals: {}, expiring_soon: [] } },
      "/platform/plans/": { body: [PLAN] },
      "/auth/me/": { body: buildMe({ is_platform_admin: true }) },
    });

    renderApp("/platform");
    await user.click(await screen.findByRole("button", { name: "المدارس" }));
    await user.click(await screen.findByRole("button", { name: new RegExp(SCHOOL.name) }));

    expect(await screen.findByRole("heading", { name: "بيانات المدرسة والدخول" })).toBeInTheDocument();
    expect(screen.getByDisplayValue("+966550123456")).toBeInTheDocument();
    expect(screen.getByText("بيانات الدخول مفعلة")).toBeInTheDocument();
    expect(screen.getByText("إدارة الاشتراك")).toBeInTheDocument();
    expect(screen.getByText("صلاحية الاستخدام")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "حفظ بيانات المدرسة" }));
    await waitFor(() => expect(calls.some(({ url, init }) => url.includes("/platform/schools/7/") && init?.method === "PATCH")).toBe(true));

    await user.click(screen.getByRole("button", { name: "إعادة ضبط كلمة المرور" }));
    await user.click(screen.getByRole("button", { name: "تأكيد" }));
    expect(await screen.findByText("Xm-Reset-Once")).toBeInTheDocument();

    expect(screen.getByText(/المدرسة محمية بحساب مدير واحد/)).toBeInTheDocument();
    expect(screen.queryByLabelText("اسم المدير الجديد")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "تعيين مدير" })).not.toBeInTheDocument();
    expect(calls.some(({ url, init }) => url.endsWith("/platform/schools/7/managers/") && init?.method === "POST")).toBe(false);
  });

  it("edits plan limits through the plan editor", async () => {
    const user = userEvent.setup();
    const { calls } = mockApi({
      "/auth/me/": { body: buildMe({ is_platform_admin: true }) },
      "/platform/overview/": {
        body: { schools_total: 0, subscriptions: {}, usage_totals: { active_students: 0, active_staff: 0, active_devices: 0 }, expiring_soon: [] },
      },
      "/platform/plans/1/": { body: PLAN },
      "/platform/plans/": { body: [PLAN] },
    });

    renderApp("/platform");
    await user.click(await screen.findByRole("button", { name: "الباقات" }));
    await user.click(await screen.findByRole("button", { name: "تعديل" }));
    const name = screen.getByPlaceholderText("اسم الباقة");
    await user.clear(name);
    await user.type(name, "الأساسية المحدثة");
    await user.click(screen.getByRole("button", { name: "حفظ التعديل" }));

    await waitFor(() => {
      expect(calls.some(({ url, init }) => url.includes("/platform/plans/1/") && init?.method === "PATCH")).toBe(true);
    });
  });
});
