import { QueryClient } from "@tanstack/react-query";

import { ApiError } from "@/api/client";

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry(failureCount, error) {
        // لا إعادة محاولة لأخطاء العميل (4xx) — فقط لمشاكل الشبكة/الخادم
        if (error instanceof ApiError && error.status > 0 && error.status < 500) {
          return false;
        }
        return failureCount < 2;
      },
      retryDelay(attempt, error) {
        return Math.max(
          Math.min(1000 * 2 ** attempt, 30_000),
          error instanceof ApiError ? error.retryAfterMs : 0,
        );
      },
    },
  },
});
