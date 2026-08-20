import { QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "react-router-dom";

import { queryClient } from "@/app/queryClient";
import { PwaStatus } from "@/app/PwaStatus";
import { router } from "@/routes";

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
      <PwaStatus />
    </QueryClientProvider>
  );
}
