import type { SchoolRole } from "@/types/auth";

/** الأسماء العربية للعرض فقط — القيم الإنجليزية هي المنطق. */
export const ROLE_LABELS: Record<SchoolRole, string> = {
  SCHOOL_MANAGER: "مدير المدرسة",
  VICE_PRINCIPAL: "الوكيل",
  COUNSELOR: "المرشد الطلابي",
  TEACHER: "معلم",
};

export function roleLabels(roles: SchoolRole[]): string {
  return roles.map((role) => ROLE_LABELS[role] ?? role).join("، ");
}
