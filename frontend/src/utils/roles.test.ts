import { describe, expect, it } from "vitest";

import { roleLabels, studentCountLabel, studentLabel, studentPluralLabel } from "@/utils/roles";

describe("school role labels", () => {
  it("uses masculine labels for boys schools", () => {
    expect(
      roleLabels(["SCHOOL_MANAGER", "VICE_PRINCIPAL", "COUNSELOR", "TEACHER"], "BOYS"),
    ).toBe("مدير المدرسة، الوكيل، المرشد الطلابي، معلم");
  });

  it("uses feminine labels for girls schools", () => {
    expect(
      roleLabels(["SCHOOL_MANAGER", "VICE_PRINCIPAL", "COUNSELOR", "TEACHER"], "GIRLS"),
    ).toBe("مديرة المدرسة، الوكيلة، المرشدة الطلابية، معلمة");
  });

  it("uses the school type for student labels", () => {
    expect([studentLabel("BOYS"), studentLabel("BOYS", true), studentPluralLabel("BOYS"), studentCountLabel("BOYS")]).toEqual([
      "طالب", "الطالب", "الطلاب", "طالبًا",
    ]);
    expect([studentLabel("GIRLS"), studentLabel("GIRLS", true), studentPluralLabel("GIRLS"), studentCountLabel("GIRLS")]).toEqual([
      "طالبة", "الطالبة", "الطالبات", "طالبة",
    ]);
  });
});
