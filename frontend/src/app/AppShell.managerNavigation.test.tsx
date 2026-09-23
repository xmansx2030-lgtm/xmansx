import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import { queryClient } from "@/app/queryClient";
import { buildMe, membership, mockApi } from "@/test/mockApi";
import { renderApp } from "@/test/renderApp";

const MANAGER = buildMe({
  active_school: { id: 10, name: "ثانوية الأندلس", slug: "andalus" },
  roles: ["SCHOOL_MANAGER"],
  memberships: [membership(1, 10, "ثانوية الأندلس", ["SCHOOL_MANAGER"])],
});

const VICE_PRINCIPAL = buildMe({
  active_school: { id: 10, name: "ثانوية الأندلس", slug: "andalus" },
  roles: ["VICE_PRINCIPAL"],
  memberships: [membership(1, 10, "ثانوية الأندلس", ["VICE_PRINCIPAL"])],
});

describe("وضوح غلاف مدير المدرسة", () => {
  beforeEach(() => {
    queryClient.clear();
    document.cookie = "csrftoken=test-token";
  });

  it("يعرض المدرسة الوحيدة كمعلومة ثابتة بلا زر تبديل ميت", async () => {
    mockApi({ "/auth/me/": { body: MANAGER } });
    renderApp("/does-not-exist");

    const currentSchool = await screen.findByRole("group", { name: "المدرسة الحالية" });
    expect(within(currentSchool).getByTestId("active-school-name")).toHaveTextContent("ثانوية الأندلس");
    expect(screen.queryByRole("button", { name: /ثانوية الأندلس/ })).not.toBeInTheDocument();
  });

  it("يعرض إجراءات المتابعة الحساسة مباشرة ويبقي الأدوات الأقل تكرارًا منظمة", async () => {
    mockApi({ "/auth/me/": { body: MANAGER } });
    renderApp("/does-not-exist");

    const navigation = await screen.findByRole("navigation", { name: "التنقل الرئيسي" });
    expect(within(navigation).getByRole("link", { name: "الإنذارات" })).toHaveAttribute("href", "/warnings");
    expect(within(navigation).getByRole("link", { name: "الأعذار" })).toHaveAttribute("href", "/excuses");
    expect(within(navigation).getByRole("link", { name: "الإحالات" })).toHaveAttribute("href", "/referrals");

    const additionalNavigation = await screen.findByTestId("additional-navigation");
    expect(additionalNavigation).not.toHaveAttribute("open");
    expect(within(additionalNavigation).getByText("المتابعة وأدوات المدرسة")).toBeInTheDocument();
    expect(within(additionalNavigation).getByTestId("additional-navigation-preview")).toHaveTextContent(
      "الغياب والحضور، الإرشاد، التأخر الصباحي، والمزيد",
    );

    await userEvent.click(within(additionalNavigation).getByText("المتابعة وأدوات المدرسة"));
    expect(within(additionalNavigation).getByRole("link", { name: "الغياب والحضور" })).toHaveAttribute("href", "/attendance/analytics");
    expect(within(additionalNavigation).getByRole("link", { name: "الإرشاد" })).toHaveAttribute("href", "/counselor");
    expect(within(additionalNavigation).getByRole("link", { name: "التأخر الصباحي" })).toHaveAttribute("href", "/morning");
  });

  it("يعرض للوكيل لوحة متابعة وينقل الإنذارات والإحالات إلى التنقل الأساسي", async () => {
    mockApi({ "/auth/me/": { body: VICE_PRINCIPAL } });
    renderApp("/does-not-exist");

    const navigation = await screen.findByRole("navigation", { name: "التنقل الرئيسي" });
    expect(within(navigation).getByRole("link", { name: "لوحة المتابعة" })).toHaveAttribute("href", "/dashboard");
    expect(within(navigation).queryByRole("link", { name: "لوحة الإدارة" })).not.toBeInTheDocument();
    expect(within(navigation).getByRole("link", { name: "الإنذارات" })).toHaveAttribute("href", "/warnings");
    expect(within(navigation).getByRole("link", { name: "الإحالات" })).toHaveAttribute("href", "/referrals");

    const additionalNavigation = within(navigation).getByTestId("additional-navigation");
    expect(within(additionalNavigation).queryByRole("link", { name: "الإنذارات" })).not.toBeInTheDocument();
    expect(within(additionalNavigation).queryByRole("link", { name: "الإحالات" })).not.toBeInTheDocument();
  });
});
