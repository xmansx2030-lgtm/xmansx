import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, CheckCheck, ClipboardCheck, Clock3, Layers3 } from "lucide-react";
import { Link } from "react-router-dom";

import { ErrorState } from "@/components/ErrorState";
import { Spinner } from "@/components/Spinner";
import { getPreparationToday } from "@/features/attendance/api";
import { monitoringPollInterval } from "@/features/attendance/monitoringShared";
import { schoolScopedKey } from "@/features/auth/useMe";

export const preparationKey = (schoolId: number) => schoolScopedKey(schoolId, "attendance", "preparation-today");

export function PreparationTodayCard({ schoolId, selectedPeriod = 0 }: { schoolId: number; selectedPeriod?: number }) {
  const query = useQuery({
    queryKey: preparationKey(schoolId), queryFn: ({ signal }) => getPreparationToday(signal),
    enabled: schoolId > 0, refetchInterval: monitoringPollInterval,
    refetchIntervalInBackground: false, refetchOnWindowFocus: "always",
  });
  const data = query.data;
  const incomplete = data?.periods.reduce((sum, period) => sum + (period.summary?.incomplete ?? 0), 0) ?? 0;
  return (
    <section className="overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-sm" data-testid="preparation-today-card" aria-label="متابعة تحضير اليوم">
      <div className="relative overflow-hidden bg-slate-950 px-5 py-6 text-white sm:px-7">
        <div aria-hidden className="pointer-events-none absolute -end-12 -top-20 size-64 rounded-full bg-teal-400/10 blur-3xl" />
        <div className="relative flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <span className="grid size-12 shrink-0 place-items-center rounded-2xl bg-teal-300/10 text-teal-200 ring-1 ring-teal-300/20"><ClipboardCheck aria-hidden size={23} /></span>
            <div><p className="mb-1 text-[10px] font-bold tracking-wider text-teal-200">التشغيل اليومي</p><h2 className="text-xl font-black">متابعة تحضير اليوم</h2><p className="mt-1 text-xs leading-5 text-slate-300">اختر عدد الفصول لفتح القائمة وتحضيرها أو استكمال اعتمادها.</p></div>
          </div>
          {data && data.periods.some((period) => period.summary) && <span className={`rounded-xl px-3 py-2 text-xs font-bold ring-1 ${incomplete > 0 ? "bg-amber-300/10 text-amber-100 ring-amber-200/20" : "bg-teal-300/10 text-teal-100 ring-teal-200/20"}`}>{incomplete > 0 ? `${incomplete} حالات تحضير غير مكتملة عبر حصص اليوم` : "تحاضير الحصص التي بدأت مكتملة"}</span>}
        </div>
      </div>
      <div className="p-4 sm:p-5">
        {query.isPending && <Spinner label="جارٍ تحميل تحضير اليوم..." />}
        {query.isError && <ErrorState error={query.error} />}
        {data && (!data.is_school_day || data.periods.length === 0) && <p className="rounded-2xl bg-slate-50 p-5 text-sm text-slate-600">لا توجد حصص تحضير مجدولة لهذا اليوم.</p>}
        {data && <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {data.periods.map((period) => {
            const summary = period.summary;
            const upcoming = period.state === "UPCOMING";
            const complete = summary?.incomplete === 0;
            const to = `/attendance/monitoring?date=${data.date}&period=${period.sequence}`;
            return (
              <article key={period.sequence} data-testid={`preparation-period-${period.sequence}`} className={`rounded-2xl border p-4 transition ${period.sequence === selectedPeriod ? "border-teal-500 ring-2 ring-teal-100" : period.state === "CURRENT" ? "border-teal-200 bg-teal-50/40" : "border-slate-200"} ${upcoming ? "bg-slate-50 text-slate-500" : "bg-white"}`}>
                <div className="flex items-start justify-between gap-2"><div><h3 className="font-black text-slate-900">{period.name}</h3><p className="mt-1 flex items-center gap-1 text-xs text-slate-500"><Clock3 aria-hidden size={13} /><span dir="ltr">{period.start_time} – {period.end_time}</span></p></div><span className={`shrink-0 rounded-lg px-2 py-1 text-[10px] font-bold ${period.state === "CURRENT" ? "bg-teal-100 text-teal-800" : "bg-slate-100 text-slate-500"}`}>{period.state === "CURRENT" ? "الحصة الحالية" : upcoming ? "لم تبدأ" : "انتهت"}</span></div>
                {summary ? <>
                  <div className="mt-4 flex items-center justify-between text-xs text-slate-600"><span className="flex items-center gap-1"><Layers3 aria-hidden size={13} />{summary.total} فصلًا مطلوبًا</span><span className="font-bold text-teal-700">{summary.submitted} معتمد</span></div>
                  <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-100"><div className="h-full rounded-full bg-teal-500" style={{ width: `${summary.total ? summary.submitted / summary.total * 100 : 0}%` }} /></div>
                  <Link to={`${to}&status=${complete ? "ALL" : "INCOMPLETE"}`} aria-label={`${period.name}: ${summary.incomplete} فصول لم يكتمل تحضيرها، عرض الفصول`} className={`mt-4 flex min-h-16 items-center justify-between gap-3 rounded-xl px-4 py-3 transition focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-600 ${complete ? "bg-teal-50 text-teal-800 hover:bg-teal-100" : "bg-amber-50 text-amber-950 hover:bg-amber-100"}`}>
                    <div className="flex items-center gap-3">{complete ? <CheckCheck aria-hidden size={24} /> : <strong className="text-3xl font-black tabular-nums">{summary.incomplete}</strong>}<div><span className="block text-xs font-black">{complete ? "اكتمل تحضير الفصول" : "لم يكتمل تحضيرها"}</span><span className="mt-1 block text-[10px] opacity-70">{complete ? "عرض التحاضير المعتمدة" : `${summary.not_started} لم تبدأ · ${summary.in_progress} قيد التحضير`}</span></div></div><ArrowLeft aria-hidden size={17} />
                  </Link>
                  {summary.overdue > 0 && <p className="mt-2 text-[11px] font-medium text-red-700">منها {summary.overdue} تجاوزت مهلة التحضير</p>}
                </> : <p className="mt-5 rounded-xl bg-slate-100 p-3 text-xs leading-6">تبدأ المتابعة عند دخول وقت الحصة.</p>}
              </article>
            );
          })}
        </div>}
      </div>
    </section>
  );
}
