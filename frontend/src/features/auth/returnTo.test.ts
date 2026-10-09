import { describe, expect, it } from "vitest";

import { safeReturnTo, withReturnTo } from "@/features/auth/returnTo";

describe("safe QR return paths", () => {
  it("allows only a bounded internal QR path", () => {
    expect(safeReturnTo("/qr/valid-token_123")).toBe("/qr/valid-token_123");
    expect(withReturnTo("/login", "/qr/valid-token_123")).toBe(
      "/login?returnTo=%2Fqr%2Fvalid-token_123",
    );
  });
  it("allows bounded parent destinations and school UUID registration only", () => {
    expect(safeReturnTo("/parent")).toBe("/parent");
    expect(safeReturnTo("/parent/register/11111111-1111-4111-8111-111111111111")).toBe("/parent/register/11111111-1111-4111-8111-111111111111");
    expect(safeReturnTo("/parent/activate#token=secret")).toBeNull();
    expect(safeReturnTo("/parent/register/token?next=evil")).toBeNull();
  });

  it("preserves the parent management page and its known tab after email completion", () => {
    expect(safeReturnTo("/parent-management")).toBe("/parent-management");
    expect(withReturnTo("/account/complete-email", "/parent-management?tab=registrations")).toBe(
      "/account/complete-email?returnTo=%2Fparent-management%3Ftab%3Dregistrations",
    );
    expect(safeReturnTo("/parent-management?tab=unknown")).toBeNull();
    expect(safeReturnTo("/parent-management?tab=registrations&next=https://evil.example")).toBeNull();
    expect(safeReturnTo("/parent-management#token=secret")).toBeNull();
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
