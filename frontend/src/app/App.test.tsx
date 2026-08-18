import { screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { renderApp } from "@/test/renderApp";
import { queryClient } from "@/app/queryClient";
import { mockApi, UNAUTHENTICATED } from "@/test/mockApi";

describe("App", () => {
  beforeEach(() => {
    queryClient.clear();
    mockApi({ "/auth/me/": UNAUTHENTICATED });
  });

  it("renders the login screen with the platform title", async () => {
    renderApp("/login");
    expect(await screen.findByRole("heading", { name: "منصة المواظبة" })).toBeInTheDocument();
  });

  it("document direction is RTL and language is Arabic", () => {
    document.documentElement.setAttribute("dir", "rtl");
    document.documentElement.setAttribute("lang", "ar");
    renderApp("/login");
    expect(document.documentElement).toHaveAttribute("dir", "rtl");
    expect(document.documentElement).toHaveAttribute("lang", "ar");
  });
});
