import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import { renderApp } from "@/test/renderApp";
import { queryClient } from "@/app/queryClient";
import { buildMe, membership, mockApi, UNAUTHENTICATED } from "@/test/mockApi";

const ME_A = buildMe({
  active_school: { id: 10, name: "ثانوية الأندلس", slug: "andalus" },
  roles: ["TEACHER"],
  memberships: [
    membership(1, 10, "ثانوية الأندلس", ["TEACHER"]),
    membership(2, 20, "مدارس الرواد", ["TEACHER", "COUNSELOR"]),
  ],
});

const ME_B = buildMe({
  active_school: { id: 20, name: "مدارس الرواد", slug: "rowad" },
  roles: ["TEACHER", "COUNSELOR"],
  memberships: ME_A.memberships,
});

describe("Protected routes & guards", () => {
  beforeEach(() => {
    queryClient.clear();
    document.cookie = "csrftoken=test-token";
  });

  it("unauthenticated user is redirected to login (401/403 handling)", async () => {
    mockApi({ "/auth/me/": UNAUTHENTICATED });
        renderApp("/");
    expect(await screen.findByRole("button", { name: "تسجيل الدخول" })).toBeInTheDocument();
  });

  it("authenticated user without active school is sent to selection", async () => {
    mockApi({
      "/auth/me/": {
        body: buildMe({ memberships: ME_A.memberships }),
      },
    });
        renderApp("/");
    expect(await screen.findByRole("heading", { name: "اختر المدرسة" })).toBeInTheDocument();
  });

  it("authenticated user with active school sees the shell with name, school and roles", async () => {
    mockApi({ "/auth/me/": { body: ME_A } });
        renderApp("/");
    expect(await screen.findByTestId("active-school-name")).toHaveTextContent("ثانوية الأندلس");
    expect(screen.getByTestId("user-name")).toHaveTextContent("أحمد المعلم");
    expect(screen.getByTestId("user-roles")).toHaveTextContent("معلم");
  });

  it("unknown route under the shell shows 404 page", async () => {
    mockApi({ "/auth/me/": { body: ME_A } });
        renderApp("/does-not-exist");
    expect(await screen.findByText("الصفحة غير موجودة")).toBeInTheDocument();
  });
});

describe("School switching", () => {
  beforeEach(() => {
    queryClient.clear();
    document.cookie = "csrftoken=test-token";
  });

  it("switching school updates shell and clears previous tenant cache", async () => {
    let currentMe = ME_A;
    mockApi({
      "/auth/me/": () => ({ body: currentMe }),
      "/session/active-school/": () => {
        currentMe = ME_B;
        return { body: ME_B };
      },
    });
    // بيانات مدرسية قديمة مزروعة في الـ cache — يجب أن تختفي بعد التبديل
    queryClient.setQueryData(["school", 10, "students"], ["stale-data"]);

        renderApp("/");
    const user = userEvent.setup();

    await screen.findByTestId("active-school-name");
    await user.click(screen.getByRole("button", { name: /ثانوية الأندلس/ }));
    await user.click(await screen.findByRole("button", { name: /مدارس الرواد/ }));

    await waitFor(() =>
      expect(screen.getByTestId("active-school-name")).toHaveTextContent("مدارس الرواد"),
    );
    expect(screen.getByTestId("user-roles")).toHaveTextContent("المرشد الطلابي");
    // الـ cache المدرسي القديم أزيل بالكامل
    expect(queryClient.getQueryData(["school", 10, "students"])).toBeUndefined();
  });

  it("logout clears state and returns to login", async () => {
    let loggedOut = false;
    mockApi({
      "/auth/me/": () => (loggedOut ? UNAUTHENTICATED : { body: ME_A }),
      "/auth/logout/": () => {
        loggedOut = true;
        return { body: { detail: "ok" } };
      },
    });
        renderApp("/");
    const user = userEvent.setup();
    await screen.findByTestId("active-school-name");
    await user.click(screen.getByRole("button", { name: "تسجيل الخروج" }));
    expect(await screen.findByRole("button", { name: "تسجيل الدخول" })).toBeInTheDocument();
  });
});
