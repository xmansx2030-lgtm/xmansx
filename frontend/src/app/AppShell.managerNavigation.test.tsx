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

  it("يكشف نوع الأدوات المهمة وأمثلة منها قبل فتح المجموعة المطوية", async () => {
    mockApi({ "/auth/me/": { body: MANAGER } });
    renderApp("/does-not-exist");

    const additionalNavigation = await screen.findByTestId("additional-navigation");
    expect(additionalNavigation).not.toHaveAttribute("open");
    expect(within(additionalNavigation).getByText("المتابعة وأدوات المدرسة")).toBeInTheDocument();
    expect(within(additionalNavigation).getByTestId("additional-navigation-preview")).toHaveTextContent(
      "الإنذارات، الأعذار، الإحالات، والمزيد",
    );

    await userEvent.click(within(additionalNavigation).getByText("المتابعة وأدوات المدرسة"));
    expect(within(additionalNavigation).getByRole("link", { name: "الإنذارات" })).toHaveAttribute("href", "/warnings");
    expect(within(additionalNavigation).getByRole("link", { name: "الأعذار" })).toHaveAttribute("href", "/excuses");
    expect(within(additionalNavigation).getByRole("link", { name: "الإحالات" })).toHaveAttribute("href", "/referrals");
  });
});
