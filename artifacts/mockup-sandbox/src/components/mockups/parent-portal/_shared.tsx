import { Badge } from "./_Badge";
import type { ParentDay } from "./_types";

export const RELATION_LABELS: Record<string, string> = {
  ACTIVE: "علاقة معتمدة",
  PENDING: "بانتظار الاعتماد",
  SUSPENDED_CONTACT_REVIEW: "معلقة لمراجعة التواصل",
  REVOKED: "سُحبت الصلاحية",
  REJECTED: "لم تعتمد العلاقة",
  UNAVAILABLE: "المدرسة غير متاحة",
};
export const REQUEST_LABELS: Record<string, string> = {
  PENDING: "بانتظار مراجعة المدرسة",
  NEEDS_INFO: "يحتاج استكمالاً",
  APPROVED: "معتمد",
  ACTIVATED: "تم التفعيل",
  REJECTED: "مرفوض",
  CANCELLED: "ملغى",
};
export function timeOnly(value: string): string {
  return value.includes("T")
    ? new Intl.DateTimeFormat("ar-SA", {
        hour: "2-digit",
        minute: "2-digit",
        timeZone: "Asia/Riyadh",
      }).format(new Date(value))
    : value;
}
export function dateTime(value: string | null | undefined): string {
  return value
    ? new Intl.DateTimeFormat("ar-SA", {
        dateStyle: "medium",
        timeStyle: "short",
        timeZone: "Asia/Riyadh",
        calendar: "gregory",
      }).format(new Date(value))
    : "لم يسجل بعد";
}
export function todayDate(): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Riyadh",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
}
export function isIncomplete(day: ParentDay | null): boolean {
  // Timetable coverage does not determine the official daily attendance state.
  return (
    !!day &&
    (day.submitted_periods === 0 || day.absence_status === "UNDETERMINED")
  );
}
export function dayLabel(day: ParentDay | null): string {
  if (!day) return "لا توجد بيانات معتمدة اليوم";
  if (isIncomplete(day)) return "اليوم غير مكتمل";
  return {
    FULL: "غائب",
    PARTIAL: "حاضر مع غياب جزئي",
    NONE: "حاضر",
    UNDETERMINED: "اليوم غير مكتمل",
  }[day.absence_status];
}
export function DayBadge({ day }: { day: ParentDay | null }) {
  return (
    <Badge
      tone={
        !day || isIncomplete(day)
          ? "warning"
          : day.absence_status === "NONE"
            ? "success"
            : day.absence_status === "FULL"
              ? "danger"
              : "warning"
      }
    >
      {dayLabel(day)}
    </Badge>
  );
}
export const fieldGrid = "grid gap-4 sm:grid-cols-2";
export const surface =
  "rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-6";
