import { describe, expect, it } from "vitest";

import { localIsoDate } from "@/utils/dates";

describe("localIsoDate", () => {
  it("keeps the local calendar day at both ends of the day", () => {
    // ‏toISOString يقفز يومًا عند الطرفين حسب الإزاحة: بعد منتصف الليل في المناطق
    // الموجبة وقبله في السالبة — والتاريخ المطلوب هو يوم المدرسة المحلي دائمًا.
    expect(localIsoDate(new Date(2026, 7, 20, 0, 30))).toBe("2026-08-20");
    expect(localIsoDate(new Date(2026, 7, 20, 23, 30))).toBe("2026-08-20");
  });

  it("pads month and day", () => {
    expect(localIsoDate(new Date(2026, 0, 5, 12, 0))).toBe("2026-01-05");
  });
});
