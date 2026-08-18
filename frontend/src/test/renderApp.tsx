import { QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";

import { queryClient } from "@/app/queryClient";
import { routes } from "@/routes";

/** يركب التطبيق بمسار ابتدائي معزول لكل اختبار (router جديد كل مرة). */
export function renderApp(initialPath: string = "/") {
  const router = createMemoryRouter(routes, { initialEntries: [initialPath] });
  return render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
}
