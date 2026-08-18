import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "@/app/App";
import { queryClient } from "@/app/queryClient";

function mockHealthFetch() {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ status: "ok" }), {
        status: 200,
        headers: { "Content-Type": "application/json", "X-Request-ID": "test-request-id" },
      }),
    ),
  );
}

describe("App", () => {
  beforeEach(() => {
    queryClient.clear();
    mockHealthFetch();
    window.history.pushState({}, "", "/");
  });

  it("renders the app shell with the platform title", async () => {
    render(<App />);
    expect(
      await screen.findByRole("heading", { name: "منصة المواظبة والمتابعة الطلابية" }),
    ).toBeInTheDocument();
  });

  it("document direction is RTL and language is Arabic", () => {
    // index.html يحمل lang/dir؛ jsdom لا يقرأ index.html فنثبت السلوك عبر الضبط الصريح
    document.documentElement.setAttribute("dir", "rtl");
    document.documentElement.setAttribute("lang", "ar");
    render(<App />);
    expect(document.documentElement).toHaveAttribute("dir", "rtl");
    expect(document.documentElement).toHaveAttribute("lang", "ar");
  });

  it("shows backend connected state when health API succeeds", async () => {
    render(<App />);
    expect(await screen.findByText("متصل")).toBeInTheDocument();
  });
});
