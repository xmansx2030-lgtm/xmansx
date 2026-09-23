import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import { queryClient } from "@/app/queryClient";
import { renderApp } from "@/test/renderApp";
import { buildMe, membership, mockApi, UNAUTHENTICATED } from "@/test/mockApi";

const PLAN = {
  id: 7,
  code: "launch",
  name: "باقة الانطلاقة",
  description: "تشغيل متكامل للمدارس",
  billing_period: "ANNUAL",
  price_amount: "990.00",
  currency: "SAR",
  duration_value: 3,
  duration_unit: "MONTHS" as const,
  trial_days: 21,
  can_self_register: true,
  entitlements: { MAX_STUDENTS: 500, MAX_STAFF: 50, MAX_DEVICES: 2 },
};

const FREE_PLAN = {
  ...PLAN,
  id: 8,
  name: "الباقة المجانية",
  price_amount: "0.00",
  trial_days: 0,
};

const CONTACT_PLAN = {
  ...PLAN,
  id: 9,
  code: "enterprise",
  name: "باقة المؤسسات",
  price_amount: "2490.00",
  trial_days: 0,
  can_self_register: false,
};

describe("Public landing and school registration", () => {
  beforeEach(() => {
    queryClient.clear();
    document.cookie = "csrftoken=test-token";
  });

  it("explains the product, loads public plans and changes the interactive story", async () => {
    mockApi({
      "/auth/me/": UNAUTHENTICATED,
      "/auth/registration/plans/": { body: [PLAN] },
    });
    renderApp("/");

    expect(await screen.findByRole("heading", { name: /كل تفاصيل المواظبة/ })).toBeInTheDocument();
    expect(await screen.findByText("باقة الانطلاقة")).toBeInTheDocument();
    expect(screen.getByText("مدة الباقة: ٣ أشهر")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /أنشئ مدرستك الآن/ }).at(0)).toHaveAttribute("href", "/register");

    const user = userEvent.setup();
    await user.click(screen.getByRole("tab", { name: /متابعة تربط المعلومة بالإجراء/ }));
    expect(screen.getByRole("tabpanel")).toHaveTextContent("الأعذار والإنذارات والإحالات");
  });

  it("presents a zero-price plan as permanently free instead of a trial", async () => {
    mockApi({
      "/auth/me/": UNAUTHENTICATED,
      "/auth/registration/plans/": { body: [FREE_PLAN] },
    });

    renderApp("/register?plan=8");

    expect(await screen.findByText("الباقة المجانية")).toBeInTheDocument();
    expect(screen.getByText("مدة الباقة: ٣ أشهر")).toBeInTheDocument();
    expect(screen.getByText("استخدام مجاني طوال مدة الباقة")).toBeInTheDocument();
    expect(screen.getByText("مجانية")).toBeInTheDocument();
  });

  it("shows paid plans without trials on the landing page with a contact action", async () => {
    mockApi({
      "/auth/me/": UNAUTHENTICATED,
      "/auth/registration/plans/": { body: [PLAN, CONTACT_PLAN] },
    });

    renderApp("/");

    expect(await screen.findByText("باقة المؤسسات")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /اطلب هذه الباقة/ })).toHaveAttribute(
      "href",
      expect.stringContaining("https://wa.me/966537720207?text="),
    );
  });

  it("keeps paid plans without trials out of the self-registration choices", async () => {
    mockApi({
      "/auth/me/": UNAUTHENTICATED,
      "/auth/registration/plans/": { body: [PLAN, CONTACT_PLAN] },
    });

    renderApp("/register");

    expect(await screen.findByText("باقة الانطلاقة")).toBeInTheDocument();
    expect(screen.queryByText("باقة المؤسسات")).not.toBeInTheDocument();
  });

  it("creates a school through the two-step flow and enters its workspace", async () => {
    const registered = buildMe({
      id: 88,
      name: "ريم القحطاني",
      mobile: "+966551234567",
      active_school: { id: 44, name: "ثانوية الإتقان التجريبية", slug: "school-44", school_type: "GIRLS" },
      roles: ["SCHOOL_MANAGER"],
      memberships: [membership(90, 44, "ثانوية الإتقان التجريبية", ["SCHOOL_MANAGER"])],
    });
    const { calls } = mockApi({
      "/auth/me/": UNAUTHENTICATED,
      "/auth/registration/plans/": { body: [PLAN] },
      "/auth/register-school/": { status: 201, body: registered },
    });
    renderApp("/register?plan=7");
    const user = userEvent.setup();

    await user.type(await screen.findByLabelText("اسم المدرسة"), "ثانوية الإتقان التجريبية");
    await user.click(screen.getByRole("radio", { name: "بنات" }));
    await user.click(screen.getByRole("button", { name: /متابعة إلى حساب المدير/ }));

    await user.type(screen.getByLabelText("اسم مدير المدرسة"), "ريم القحطاني");
    await user.type(screen.getByLabelText("رقم الجوال"), "0551234567");
    await user.type(screen.getByLabelText("كلمة المرور"), "Safe-School-2026!");
    await user.type(screen.getByLabelText("تأكيد كلمة المرور"), "Safe-School-2026!");
    await user.click(screen.getByRole("checkbox"));
    await user.click(screen.getByRole("button", { name: /إنشاء المدرسة وبدء التجربة/ }));

    await waitFor(() => expect(calls.some(({ url }) => url.includes("/auth/register-school/"))).toBe(true));
    expect(await screen.findByTestId("active-school-name")).toHaveTextContent("ثانوية الإتقان التجريبية");

    const registrationCall = calls.find(({ url }) => url.includes("/auth/register-school/"));
    expect(JSON.parse(String(registrationCall?.init?.body))).toMatchObject({
      school_name: "ثانوية الإتقان التجريبية",
      school_type: "GIRLS",
      manager_mobile: "+966551234567",
      plan_id: 7,
      terms_accepted: true,
    });
  });
});
