import { describe, expect, it } from "vitest";

import { ApiError } from "@/api/client";
import { queryClient } from "@/app/queryClient";

describe("bounded request retries", () => {
  it("retries transient network errors and honors HTTP retry delays", () => {
    const retry = queryClient.getDefaultOptions().queries?.retry;
    const delay = queryClient.getDefaultOptions().queries?.retryDelay;
    if (typeof retry !== "function" || typeof delay !== "function") throw new Error("Missing retry policy");
    const body = { code: "NETWORK_ERROR", message: "offline", details: {} };
    expect(retry(0, new ApiError(0, body, null))).toBe(true);
    expect(retry(2, new ApiError(0, body, null))).toBe(false);
    expect(retry(0, new ApiError(403, body, null))).toBe(false);
    expect(retry(0, new ApiError(429, body, null))).toBe(false);
    expect(delay(0, new ApiError(503, body, null, 20_000))).toBe(20_000);
  });
});
