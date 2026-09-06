import type { SchoolRole, SchoolType } from "@/types/auth";

/** الأسماء العربية للعرض فقط — القيم الإنجليزية هي المنطق. */
export const ROLE_LABELS: Record<SchoolRole, string> = {
  SCHOOL_MANAGER: "مدير المدرسة",
  VICE_PRINCIPAL: "الوكيل",
  COUNSELOR: "المرشد الطلابي",
  TEACHER: "معلم",
};

export const FEMININE_ROLE_LABELS: Record<SchoolRole, string> = {
  SCHOOL_MANAGER: "مديرة المدرسة",
  VICE_PRINCIPAL: "الوكيلة",
  COUNSELOR: "المرشدة الطلابية",
  TEACHER: "معلمة",
};

export const ROLE_PLURAL_LABELS: Record<SchoolType, Record<SchoolRole, string>> = {
  BOYS: {
    SCHOOL_MANAGER: "مديرو المدرسة",
    VICE_PRINCIPAL: "الوكلاء",
    COUNSELOR: "المرشدون الطلابيون",
    TEACHER: "المعلمون",
  },
  GIRLS: {
    SCHOOL_MANAGER: "مديرات المدرسة",
    VICE_PRINCIPAL: "الوكيلات",
    COUNSELOR: "المرشدات الطلابيات",
    TEACHER: "المعلمات",
  },
};

const ROLE_GENITIVE_PLURAL_LABELS: Record<SchoolType, Record<SchoolRole, string>> = {
  BOYS: {
    SCHOOL_MANAGER: "مديري المدرسة",
    VICE_PRINCIPAL: "الوكلاء",
    COUNSELOR: "المرشدين الطلابيين",
    TEACHER: "المعلمين",
  },
  GIRLS: {
    SCHOOL_MANAGER: "مديرات المدرسة",
    VICE_PRINCIPAL: "الوكيلات",
    COUNSELOR: "المرشدات الطلابيات",
    TEACHER: "المعلمات",
  },
};

export function roleLabel(role: SchoolRole, schoolType: SchoolType = "BOYS"): string {
  return schoolType === "GIRLS" ? FEMININE_ROLE_LABELS[role] : ROLE_LABELS[role];
}

export function rolePluralLabel(role: SchoolRole, schoolType: SchoolType = "BOYS"): string {
  return ROLE_PLURAL_LABELS[schoolType][role];
}

export function roleGenitivePluralLabel(
  role: SchoolRole,
  schoolType: SchoolType = "BOYS",
): string {
  return ROLE_GENITIVE_PLURAL_LABELS[schoolType][role];
}

export function roleLabels(roles: SchoolRole[], schoolType: SchoolType = "BOYS"): string {
  return roles.map((role) => roleLabel(role, schoolType)).join("، ");
}

export function studentLabel(schoolType: SchoolType = "BOYS", definite = false): string {
  if (schoolType === "GIRLS") return definite ? "الطالبة" : "طالبة";
  return definite ? "الطالب" : "طالب";
}

export function studentPluralLabel(schoolType: SchoolType = "BOYS"): string {
  return schoolType === "GIRLS" ? "الطالبات" : "الطلاب";
}

export function studentCountLabel(schoolType: SchoolType = "BOYS"): string {
  return schoolType === "GIRLS" ? "طالبة" : "طالبًا";
}
