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
    expect(screen.getByText(/READ_ONLY/)).toBeInTheDocument();
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

    expect(await screen.findByText(/BLOCKED/)).toBeInTheDocument();
    expect(screen.getByText(/البيانات محفوظة/)).toBeInTheDocument();
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
    await user.selectOptions(await screen.findByLabelText("الباقة الجديدة"), "1");
    expect(within(await screen.findByTestId("plan-change-preview")).getAllByText(/تجاوز الحد/)).toHaveLength(2);
    expect(screen.getByText("لن تُحذف أي بيانات.")).toBeInTheDocument();
    expect(screen.queryByText("بيانات ولي الأمر")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "إيقاف" }));
    await waitFor(() => {
      expect(calls.some(({ url, init }) => url.includes("/subscription/suspend/") && init?.method === "POST")).toBe(true);
    });
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
