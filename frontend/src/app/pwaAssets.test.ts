import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

describe("PWA visual assets", () => {
  it("ships a real 512px maskable icon instead of a blank placeholder", () => {
    const path = resolve(process.cwd(), "public", "icons", "pwa-maskable-512-v2.png");
    const image = readFileSync(path);

    expect(image.subarray(1, 4).toString()).toBe("PNG");
    expect(image.readUInt32BE(16)).toBe(512);
    expect(image.readUInt32BE(20)).toBe(512);
    expect(image.byteLength).toBeGreaterThan(50_000);
  });
});
