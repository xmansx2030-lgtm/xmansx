import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import { renderApp } from "@/test/renderApp";
import { queryClient } from "@/app/queryClient";
import { buildMe, membership, mockApi, UNAUTHENTICATED } from "@/test/mockApi";

describe("LoginPage", () => {
  beforeEach(() => {
    queryClient.clear();
    document.cookie = "csrftoken=test-token";
  });

  it("renders Arabic RTL login form", async () => {
    mockApi({ "/auth/me/": UNAUTHENTICATED });
    renderApp("/login");
    expect(await screen.findByLabelText("رقم الجوال")).toBeInTheDocument();
    expect(screen.getByLabelText("كلمة المرور")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "تسجيل الدخول" })).toBeInTheDocument();
  });

  it("validates mobile before calling the API", async () => {
    const { calls } = mockApi({ "/auth/me/": UNAUTHENTICATED });
    renderApp("/login");
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("رقم الجوال"), "abc");
    await user.type(screen.getByLabelText("كلمة المرور"), "secret");
    await user.click(screen.getByRole("button", { name: "تسجيل الدخول" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("رقم جوال سعودي صحيح");
    expect(calls.some((c) => c.url.includes("/auth/login/"))).toBe(false);
  });

  it("shows API error message for invalid credentials", async () => {
    mockApi({
      "/auth/me/": UNAUTHENTICATED,
      "/auth/login/": {
        status: 401,
        body: {
          code: "INVALID_CREDENTIALS",
          message: "رقم الجوال أو كلمة المرور غير صحيحة.",
          details: {},
        },
      },
    });
    renderApp("/login");
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("رقم الجوال"), "0550000001");
    await user.type(screen.getByLabelText("كلمة المرور"), "wrong");
    await user.click(screen.getByRole("button", { name: "تسجيل الدخول" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "رقم الجوال أو كلمة المرور غير صحيحة.",
    );
  });

  it("shows rate limit message", async () => {
    mockApi({
      "/auth/me/": UNAUTHENTICATED,
      "/auth/login/": {
        status: 429,
        body: {
          code: "LOGIN_RATE_LIMITED",
          message: "عدد المحاولات تجاوز الحد المسموح، حاول بعد قليل.",
          details: {},
        },
      },
    });
    renderApp("/login");
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("رقم الجوال"), "0550000001");
    await user.type(screen.getByLabelText("كلمة المرور"), "x");
    await user.click(screen.getByRole("button", { name: "تسجيل الدخول" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("تجاوز الحد المسموح");
  });

  it("single-school user goes straight to the app shell", async () => {
    const meWithSchool = buildMe({
      active_school: { id: 10, name: "ثانوية الأندلس", slug: "andalus" },
      roles: ["TEACHER"],
      memberships: [membership(1, 10, "ثانوية الأندلس", ["TEACHER"])],
    });
    mockApi({
      "/auth/me/": UNAUTHENTICATED,
      "/auth/login/": { body: meWithSchool },
    });
    renderApp("/login");
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("رقم الجوال"), "0550000001");
    await user.type(screen.getByLabelText("كلمة المرور"), "secret");
    await user.click(screen.getByRole("button", { name: "تسجيل الدخول" }));
    expect(await screen.findByTestId("active-school-name")).toHaveTextContent("ثانوية الأندلس");
  });

  it("multi-school user is sent to school selection", async () => {
    const multi = buildMe({
      memberships: [
        membership(1, 10, "ثانوية الأندلس", ["TEACHER"]),
        membership(2, 20, "مدارس الرواد", ["TEACHER", "COUNSELOR"]),
      ],
    });
    mockApi({
      "/auth/me/": UNAUTHENTICATED,
      "/auth/login/": { body: multi },
    });
    renderApp("/login");
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("رقم الجوال"), "0550000001");
    await user.type(screen.getByLabelText("كلمة المرور"), "secret");
    await user.click(screen.getByRole("button", { name: "تسجيل الدخول" }));
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: "اختر المدرسة" })).toBeInTheDocument(),
    );
    expect(screen.getByText("ثانوية الأندلس")).toBeInTheDocument();
    expect(screen.getByText("مدارس الرواد")).toBeInTheDocument();
  });
});
