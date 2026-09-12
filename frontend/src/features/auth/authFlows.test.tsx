import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

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
    const cancelQueries = vi.spyOn(queryClient, "cancelQueries");
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
    expect(cancelQueries).toHaveBeenCalled();
    cancelQueries.mockRestore();
  });
});

describe("Initial password change", () => {
  beforeEach(() => {
    queryClient.clear();
    document.cookie = "csrftoken=test-token";
  });

  const TEMP_ACCOUNT = buildMe({
    mobile: "+966550000001",
    must_change_password: true,
    active_school: { id: 10, name: "ثانوية الأندلس", slug: "andalus" },
    roles: ["SCHOOL_MANAGER"],
    memberships: [membership(1, 10, "ثانوية الأندلس", ["SCHOOL_MANAGER"])],
  });

  it("shows every password rule and a supported help path before submission", async () => {
    mockApi({ "/auth/me/": { body: TEMP_ACCOUNT } });
    renderApp("/change-password");

    expect(await screen.findByRole("heading", { name: "تغيير كلمة المرور" })).toBeInTheDocument();
    expect(screen.getByText("ثمانية أحرف على الأقل.")).toBeInTheDocument();
    expect(screen.getByText("ليست أرقامًا فقط.")).toBeInTheDocument();
    expect(screen.getByText("ليست رقم جوالك.")).toBeInTheDocument();
    expect(screen.getByText("مختلفة عن كلمة المرور المؤقتة.")).toBeInTheDocument();
    expect(screen.getByText("مطابقة لما ستكتبه في حقل التأكيد.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "تواصل مع الدعم عبر واتساب" })).toHaveAttribute(
      "href",
      expect.stringContaining("https://wa.me/966537720207?text="),
    );
  });

  it.each([
    ["Temp-12345", "12345678", "12345678", "لا يمكن أن تكون أرقامًا فقط"],
    ["Temp-12345", "+966550000001", "+966550000001", "لا يمكن أن تكون رقم جوالك"],
    ["Temp-12345", "Temp-12345", "Temp-12345", "يجب أن تختلف"],
  ])("rejects an invalid new password before the API call", async (current, next, confirm, message) => {
    const { calls } = mockApi({ "/auth/me/": { body: TEMP_ACCOUNT } });
    renderApp("/change-password");
    const user = userEvent.setup();

    await user.type(await screen.findByLabelText("كلمة المرور الحالية"), current);
    await user.type(screen.getByLabelText("كلمة المرور الجديدة"), next);
    await user.type(screen.getByLabelText("تأكيد كلمة المرور"), confirm);
    await user.click(screen.getByRole("button", { name: "حفظ كلمة المرور" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(message);
    expect(calls.some(({ url }) => url.includes("/auth/change-initial-password/"))).toBe(false);
  });

  it("lets a user leave the mandatory screen by logging out", async () => {
    let loggedOut = false;
    const { calls } = mockApi({
      "/auth/me/": () => (loggedOut ? UNAUTHENTICATED : { body: TEMP_ACCOUNT }),
      "/auth/logout/": () => {
        loggedOut = true;
        return { body: { detail: "ok" } };
      },
    });
    renderApp("/change-password");
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "تسجيل الخروج" }));

    expect(await screen.findByRole("button", { name: "تسجيل الدخول" })).toBeInTheDocument();
    expect(calls.some(({ url, init }) => url.includes("/auth/logout/") && init?.method === "POST")).toBe(true);
  });
});
