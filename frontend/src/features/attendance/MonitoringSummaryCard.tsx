import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { Spinner } from "@/components/Spinner";
import { getMonitoring } from "@/features/attendance/api";
import {
  MONITORING_POLL_MS,
  monitoringKey,
} from "@/features/attendance/monitoringShared";

interface MonitoringSummaryCardProps {
  activeSchoolId: number;
}

/** بطاقة الرئيسية للوكيل/المدير — ملخص الحصة الحالية ورابط التفاصيل.
 *  نفس مفتاح استعلام اللوحة → لا طلبات مزدوجة. */
export function MonitoringSummaryCard({ activeSchoolId }: MonitoringSummaryCardProps) {
  const query = useQuery({
    queryKey: monitoringKey(activeSchoolId),
    queryFn: ({ signal }) => getMonitoring(signal),
    refetchInterval: MONITORING_POLL_MS,
  });

  return (
    <section
      className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"
      data-testid="monitoring-summary-card"
    >
      <h3 className="mb-2 text-lg font-bold text-slate-800">متابعة الحصة الحالية</h3>
      {query.isPending && <Spinner />}
      {query.isError && (
        <p className="text-sm text-slate-500">تعذر تحميل ملخص المتابعة.</p>
      )}
      {query.isSuccess && !query.data.period && (
        <p className="text-slate-600">لا توجد حصة دراسية نشطة حاليًا.</p>
      )}
      {query.isSuccess && query.data.period && query.data.summary && (
        <div className="space-y-2">
          <p className="text-sm text-slate-500">
            {query.data.period.name} ·{" "}
            <span dir="ltr">
              {query.data.period.start_time} – {query.data.period.end_time}
            </span>
          </p>
          <p className="text-sm text-slate-700" data-testid="monitoring-summary-line">
            {query.data.summary.total} فصلًا: ✅ {query.data.summary.submitted} مكتمل · 🟠{" "}
            {query.data.summary.in_progress} قيد التحضير · ⚪{" "}
            {query.data.summary.not_started} لم يبدأ · 🔴 {query.data.summary.overdue_total}{" "}
            متأخر
          </p>
        </div>
      )}
      <p className="mt-3">
        <Link to="/attendance/monitoring" className="text-sm font-medium text-blue-700 underline">
          عرض تفاصيل الفصول
        </Link>
      </p>
    </section>
  );
}
