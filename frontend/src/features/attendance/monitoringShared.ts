import type { MonitoringSection } from "@/features/attendance/api";
import { schoolScopedKey } from "@/features/auth/useMe";

/** نافذة قصيرة لالتقاط تعديل توقيت الجدول والتحضير على شاشات الإدارة. */
export const MONITORING_POLL_MS = 5_000;

export const monitoringKey = (activeSchoolId: number) =>
  schoolScopedKey(activeSchoolId, "attendance", "monitoring");

function minutesSuffix(minutes: number | null): string {
  if (minutes == null) return "";
  return minutes > 0 ? ` ${minutes} دقيقة` : "";
}

/** وصف الحالة نصًا وأيقونة — لا اعتماد على اللون وحده (إتاحة).
 *  الدقائق تعرض كما وصلت من الخادم — لا حساب حالة في الواجهة. */
export function statusPresentation(section: MonitoringSection): {
  icon: string;
  label: string;
  className: string;
} {
  const overdue = section.timeliness_status === "OVERDUE";
  switch (section.attendance_status) {
    case "SUBMITTED":
      return overdue
        ? {
            icon: "⚠️",
            label: `تم التحضير متأخرًا${minutesSuffix(section.minutes_overdue)}`,
            className: "bg-amber-100 text-amber-900",
          }
        : { icon: "✅", label: "تم التحضير", className: "bg-green-100 text-green-800" };
    case "IN_PROGRESS":
      return overdue
        ? {
            icon: "🟠",
            label: `بدأ ولم يعتمد — متأخر${minutesSuffix(section.minutes_overdue) || " أقل من دقيقة"}`,
            className: "bg-orange-100 text-orange-900",
          }
        : { icon: "🟠", label: "قيد التحضير", className: "bg-orange-50 text-orange-800" };
    default:
      return overdue
        ? {
            icon: "🔴",
            label: `لم يتم التحضير — متأخر${minutesSuffix(section.minutes_overdue) || " أقل من دقيقة"}`,
            className: "bg-red-100 text-red-800",
          }
        : { icon: "⚪", label: "لم يبدأ", className: "bg-slate-100 text-slate-600" };
  }
}
