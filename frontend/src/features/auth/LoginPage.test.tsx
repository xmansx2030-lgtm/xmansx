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
    expect(screen.getByText("مرحبًا بك")).toBeInTheDocument();
    expect(screen.queryByText("مرحبًا بعودتك")).not.toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "تواصل معنا عبر واتساب على الرقم 0537720207" }),
    ).toHaveAttribute(
      "href",
      expect.stringContaining("https://wa.me/966537720207?text="),
    );
    const whatsappLink = screen.getByRole("link", {
      name: "تواصل معنا عبر واتساب على الرقم 0537720207",
    });
    expect(decodeURIComponent(whatsappLink.getAttribute("href") ?? "")).toContain(
      "منصة المواظبة XMANSX",
    );
  });

  it("validates mobile before calling the API", async () => {
    const { calls } = mockApi({ "/auth/me/": UNAUTHENTICATED });
    renderApp("/login");
    const user = userEvent.setup();
    const mobile = await screen.findByLabelText("رقم الجوال");
    await user.type(mobile, "+971550000001");
    expect(mobile).toHaveValue("+971550000001");
    await user.type(screen.getByLabelText("كلمة المرور"), "secret");
    await user.click(screen.getByRole("button", { name: "تسجيل الدخول" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("05XXXXXXXX أو +9665XXXXXXXX");
    expect(calls.some((c) => c.url.includes("/auth/login/"))).toBe(false);
  });

  it.each([
    ["0550000001", "+966550000001"],
    ["966550000001", "+966550000001"],
    ["+966550000001", "+966550000001"],
    ["00966550000001", "+966550000001"],
    ["٠٥٥٠٠٠٠٠٠١", "+966550000001"],
  ])("accepts %s when pasted and sends canonical mobile %s", async (entered, expected) => {
    const { calls } = mockApi({
      "/auth/me/": UNAUTHENTICATED,
      "/auth/login/": { status: 401, body: { code: "INVALID_CREDENTIALS", message: "بيانات غير صحيحة", details: {} } },
    });
    renderApp("/login");
    const user = userEvent.setup();
    const mobile = await screen.findByLabelText("رقم الجوال");
    expect(mobile).toHaveAttribute("maxlength", "20");
    await user.click(mobile);
    await user.paste(entered);
    expect(mobile).toHaveValue(entered === "٠٥٥٠٠٠٠٠٠١" ? "0550000001" : entered);
    await user.type(screen.getByLabelText("كلمة المرور"), "secret");
    await user.click(screen.getByRole("button", { name: "تسجيل الدخول" }));
    await screen.findByRole("alert");
    const loginCall = calls.find((call) => call.url.includes("/auth/login/"));
    expect(JSON.parse(String(loginCall?.init?.body))).toMatchObject({ mobile: expected });
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

  it("returns an authorized employee to the scanned QR after login", async () => {
    const teacher = buildMe({
      active_school: { id: 10, name: "ثانوية الأندلس", slug: "andalus" },
      roles: ["TEACHER"],
      memberships: [membership(1, 10, "ثانوية الأندلس", ["TEACHER"])],
    });
    const { calls } = mockApi({
      "/auth/me/": UNAUTHENTICATED,
      "/auth/login/": { body: teacher },
      "/attendance/qr/resolve/": {
        status: 404,
        body: {
          code: "SECTION_QR_INVALID",
          message: "رمز QR غير صالح أو تم تجديده.",
          details: {},
        },
      },
    });

    renderApp("/login?returnTo=%2Fqr%2Ftok-abc123");
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("رقم الجوال"), "0550000001");
    await user.type(screen.getByLabelText("كلمة المرور"), "secret");
    await user.click(screen.getByRole("button", { name: "تسجيل الدخول" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("رمز QR غير صالح");
    expect(calls.some((call) => call.url.includes("/attendance/qr/resolve/"))).toBe(true);
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

  it("platform admin goes directly to the platform console", async () => {
    const platformAdmin = buildMe({ is_platform_admin: true });
    mockApi({
      "/auth/me/": UNAUTHENTICATED,
      "/auth/login/": { body: platformAdmin },
      "/platform/dashboard/": { body: {} },
    });
    renderApp("/login");
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("رقم الجوال"), "0550000016");
    await user.type(screen.getByLabelText("كلمة المرور"), "secret");
    await user.click(screen.getByRole("button", { name: "تسجيل الدخول" }));
    expect(await screen.findByRole("heading", { name: "إدارة المنصة" })).toBeInTheDocument();
  });
});
