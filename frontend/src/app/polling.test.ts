import { describe, expect, it } from "vitest";
import { QueryClient } from "@tanstack/react-query";
import { ApiError } from "@/api/client";

import { activeJobPollingInterval, adaptivePollingInterval, POLLING } from "@/app/polling";

describe("high-scale polling policy", () => {
  it("stays inside the configured jitter window and backs off after failures", () => {
    const interval = adaptivePollingInterval(10_000);
    const healthy = interval({ state: { fetchFailureCount: 0 } });
    const failing = interval({ state: { fetchFailureCount: 2 } });

    expect(healthy).toBeGreaterThanOrEqual(8_500);
    expect(healthy).toBeLessThanOrEqual(11_500);
    expect(failing).toBe(healthy * 4);
  });

  it("keeps high-frequency defaults above the anti-herd floor", () => {
    expect(POLLING.monitoring).toBeGreaterThanOrEqual(5_000);
    expect(POLLING.teacherPeriod).toBeGreaterThanOrEqual(5_000);
    expect(POLLING.teacherAttention).toBeGreaterThanOrEqual(10_000);
    expect(POLLING.dashboardLive).toBeGreaterThanOrEqual(5_000);
    expect(POLLING.counselorDashboard).toBeGreaterThanOrEqual(10_000);
    expect(POLLING.counselorCases).toBeGreaterThanOrEqual(15_000);
  });

  it("backs off across real failed fetch cycles and resets after a successful poll", async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const options = { queryKey: ["pressure-poll"], queryFn: async () => { throw new Error("offline"); } };
    const interval = adaptivePollingInterval(10_000);
    for (let failures = 1; failures <= 3; failures++) {
      await client.fetchQuery(options).catch(() => undefined);
      const query = client.getQueryCache().find({ queryKey: options.queryKey })!;
      expect(query.state.fetchFailureCount).toBe(1); // TanStack resets this each fetch.
      expect(interval(query)).toBeGreaterThanOrEqual(8_500 * 2 ** failures);
      expect(interval(query)).toBeLessThanOrEqual(11_500 * 2 ** failures);
    }
    await client.fetchQuery({ ...options, queryFn: async () => "recovered" });
    const query = client.getQueryCache().find({ queryKey: options.queryKey })!;
    expect(interval(query)).toBeLessThanOrEqual(11_500);
    client.clear();
  });

  it("respects Retry-After and stops completed job polling", () => {
    const interval = activeJobPollingInterval(["PROCESSING", "IMPORTING"]);
    const error = new ApiError(429, { code: "RATE_LIMITED", message: "busy", details: {} }, null, 60_000);
    const busyQuery = { state: { data: { status: "PROCESSING" }, error } };
    expect(interval(busyQuery)).toBe(60_000);
    // A failed first read must recover too, before any job status was cached.
    const initialFailure = { state: { status: "error", error } };
    expect(interval(initialFailure)).toBe(60_000);
    expect(interval({ state: { data: { status: "COMPLETED" } } })).toBe(false);
  });
});
