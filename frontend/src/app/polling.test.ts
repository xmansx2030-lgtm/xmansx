import { describe, expect, it } from "vitest";

import { adaptivePollingInterval, POLLING } from "@/app/polling";

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
    expect(POLLING.dashboardLive).toBeGreaterThanOrEqual(5_000);
  });
});
