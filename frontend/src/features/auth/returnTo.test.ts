import { describe, expect, it } from "vitest";

import { safeReturnTo, withReturnTo } from "@/features/auth/returnTo";

describe("safe QR return paths", () => {
  it("allows only a bounded internal QR path", () => {
    expect(safeReturnTo("/qr/valid-token_123")).toBe("/qr/valid-token_123");
    expect(withReturnTo("/login", "/qr/valid-token_123")).toBe(
      "/login?returnTo=%2Fqr%2Fvalid-token_123",
    );
  });

  it.each([
    "https://evil.example/qr/token",
    "//evil.example/qr/token",
    "/students/1",
    "/qr/token?next=https://evil.example",
    `/qr/${"a".repeat(65)}`,
  ])("rejects an unsafe return destination: %s", (value) => {
    expect(safeReturnTo(value)).toBeNull();
    expect(withReturnTo("/login", value)).toBe("/login");
  });
});
