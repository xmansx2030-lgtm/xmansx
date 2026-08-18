import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { queryClient } from "@/app/queryClient";
import { routes } from "@/routes";

describe("NotFoundPage", () => {
  beforeEach(() => {
    queryClient.clear();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(JSON.stringify({ status: "ok" }), { status: 200 })),
    );
  });

  it("renders 404 page for unknown routes", async () => {
    const router = createMemoryRouter(routes, {
      initialEntries: ["/this-route-does-not-exist"],
    });
    render(
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    );
    expect(await screen.findByText("الصفحة غير موجودة")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "العودة للرئيسية" })).toBeInTheDocument();
  });
});
