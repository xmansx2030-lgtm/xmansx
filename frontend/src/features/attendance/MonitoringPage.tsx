import { useQuery } from "@tanstack/react-query";
import { Activity, AlertTriangle, ArrowLeft, CheckCircle2, ClipboardCheck, Clock3, Layers3, LoaderCircle, RefreshCw } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { Button } from "@/components/Button";
import { ErrorState } from "@/components/ErrorState";
import { MetricCard } from "@/components/MetricCard";
import { PageHeader } from "@/components/PageHeader";
import { Spinner } from "@/components/Spinner";
import type { MonitoringResponse, MonitoringSection } from "@/features/attendance/api";
import { getMonitoring, getPreparationToday } from "@/features/attendance/api";
import { PreparationTodayCard, preparationKey } from "@/features/attendance/PreparationTodayCard";
import { sectionLabel } from "@/features/attendance/sectionLabel";
import {
  monitoringKey,
  monitoringPollInterval,
  statusPresentation,
} from "@/features/attendance/monitoringShared";
import { useMe } from "@/features/auth/useMe";
import { studentCountLabel } from "@/utils/roles";

type StatusFilter =
  | "ALL"
  | "INCOMPLETE"
  | "SUBMITTED"
  | "IN_PROGRESS"
  | "NOT_STARTED"
  | "OVERDUE"
  | "SUBMITTED_LATE";

const STATUS_FILTERS: { value: StatusFilter; label: string }[] = [
  { value: "ALL", label: "الكل" },
  { value: "INCOMPLETE", label: "لم يكتمل تحضيرها" },
  { value: "SUBMITTED", label: "تم التحضير" },
  { value: "IN_PROGRESS", label: "قيد التحضير" },
  { value: "NOT_STARTED", label: "لم يبدأ" },
  { value: "OVERDUE", label: "المتأخرون فقط" },
  { value: "SUBMITTED_LATE", label: "تم التحضير متأخرًا" },
];

function matchesFilter(section: MonitoringSection, filter: StatusFilter): boolean {
  switch (filter) {
    case "INCOMPLETE":
      return section.attendance_status !== "SUBMITTED";
    case "ALL":
      return true;
    case "OVERDUE":
      return section.timeliness_status === "OVERDUE";
    case "SUBMITTED_LATE":
      return section.attendance_status === "SUBMITTED" && section.timeliness_status === "OVERDUE";
    default:
      return section.attendance_status === filter;
  }
}

/** لوحة متابعة الحصة الحالية — وكيل/مدير. الحالة من الخادم؛ الواجهة تعدّ وتعرض فقط.
 *  ‏KPIs تتبع الفلاتر الحالية (قرار موثق) — «مسح الفلاتر» يعيد الأرقام الكلية. */
export function MonitoringPage() {
  const me = useMe();
  const activeSchoolId = me.data?.active_school?.id ?? 0;
  const schoolType = me.data?.active_school?.school_type ?? "BOYS";
  const [params, setParams] = useSearchParams();
  const requestedSequence = Number(params.get("period"));
  const selectedSequence = Number.isInteger(requestedSequence) && requestedSequence > 0 ? requestedSequence : 0;
  const statusFilter = STATUS_FILTERS.find((filter) => filter.value === params.get("status"))?.value ?? "ALL";
  const setStatusFilter = (value: StatusFilter) => setParams((previous) => {
    previous.set("status", value);
    return previous;
  });
  const [gradeFilter, setGradeFilter] = useState<number | "">("");
  const [search, setSearch] = useState("");

  const currentQuery = useQuery({
    queryKey: monitoringKey(activeSchoolId),
    queryFn: ({ signal }) => getMonitoring(signal),
    enabled: activeSchoolId > 0 && selectedSequence === 0,
    refetchInterval: monitoringPollInterval,
    // لا نستهلك API/DB عندما لا تكون شاشة المتابعة معروضة للمستخدم.
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: "always",
  });

  const dayQuery = useQuery({
    queryKey: preparationKey(activeSchoolId), queryFn: ({ signal }) => getPreparationToday(signal),
    enabled: activeSchoolId > 0 && selectedSequence > 0, refetchInterval: monitoringPollInterval,
    refetchIntervalInBackground: false, refetchOnWindowFocus: "always",
  });
  const query = selectedSequence > 0 ? dayQuery : currentQuery;
  const refreshMonitoring = () => {
    void query.refetch();
    if (selectedSequence === 0) void dayQuery.refetch();
  };
  const selectedPeriod = dayQuery.data?.periods.find((period) => period.sequence === selectedSequence);
  const data: MonitoringResponse | undefined = selectedSequence > 0 ? dayQuery.data && {
    date: dayQuery.data.date, school_time: dayQuery.data.school_time,
    period: selectedPeriod?.summary ? selectedPeriod : null, alert: null,
    sections: selectedPeriod?.sections ?? [], summary: null,
  } : currentQuery.data;
  const wrongDate = selectedSequence > 0 && !!dayQuery.data && !!params.get("date") && params.get("date") !== dayQuery.data.date;
  const listRef = useRef<HTMLElement>(null);
  useEffect(() => {
    if (selectedSequence > 0 && query.isSuccess && !wrongDate) {
      listRef.current?.scrollIntoView?.({ behavior: "smooth", block: "start" });
      listRef.current?.focus({ preventScroll: true });
    }
  }, [selectedSequence, query.isSuccess, wrongDate]);

  const grades = useMemo(() => {
    const map = new Map<number, string>();
    for (const s of data?.sections ?? []) map.set(s.grade_id, s.grade_name);
    return [...map.entries()];
  }, [data?.sections]);

  const filtered = useMemo(
    () =>
      (data?.sections ?? []).filter(
        (s) =>
          matchesFilter(s, statusFilter) &&
          (gradeFilter === "" || s.grade_id === gradeFilter) &&
          (search === "" || sectionLabel(s.grade_name, s.section_name, s.department).includes(search.trim())),
      ),
    [data?.sections, statusFilter, gradeFilter, search],
  );

  // ‏KPIs من عدّ حالات الخادم على القائمة المفلترة — لا إعادة اشتقاق للحالة
  const kpis = useMemo(() => {
    let submitted = 0;
    let inProgress = 0;
    let notStarted = 0;
    let overdue = 0;
    for (const s of filtered) {
      if (s.attendance_status === "SUBMITTED") submitted += 1;
      else if (s.attendance_status === "IN_PROGRESS") inProgress += 1;
      else notStarted += 1;
      if (s.timeliness_status === "OVERDUE") overdue += 1;
    }
    return { total: filtered.length, submitted, inProgress, notStarted, overdue };
  }, [filtered]);

  const hasFilters = statusFilter !== "ALL" || gradeFilter !== "" || search !== "";
  const lastUpdated = query.dataUpdatedAt
    ? new Date(query.dataUpdatedAt).toLocaleTimeString("ar-SA")
    : null;

  if (query.isPending || me.isPending) {
    return <Spinner label="جارٍ تحميل لوحة المتابعة..." />;
  }
  if (query.isError) {
    return (
      <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <ErrorState error={query.error} />
      </section>
    );
  }
  if (wrongDate) return <section className="rounded-2xl border border-amber-200 bg-amber-50 p-6"><p className="font-bold text-amber-950">هذا الرابط يخص يومًا سابقًا. افتح حصص اليوم لمتابعة التحضير.</p><Link to="/attendance/monitoring" className="mt-4 inline-block text-amber-900 underline">متابعة اليوم</Link></section>;
  if (!data) return null;

  return (
    <div className="ds-page">
      <PageHeader
        icon={Activity}
        eyebrow="غرفة العمليات المباشرة"
        title={selectedSequence > 0 ? `متابعة تحضير ${data.period?.name ?? "الحصة المحددة"}` : "متابعة تحضير الحصة الحالية"}
        description={data.period ? "تابع الفصول التي لم يكتمل تحضيرها، وافتح الفصل للتحضير أو استكمال الاعتماد." : "اختر من بطاقة اليوم حصة بدأ وقتها لمتابعة الفصول واستكمال التحضير."}
        tone="executive"
        badge={data.period?.name ?? "خارج وقت الحصص"}
        meta={data.period ? <span data-testid="monitoring-period"><Clock3 aria-hidden size={14} className="inline" /> {data.period.name} · <span dir="ltr">{data.period.start_time} – {data.period.end_time}</span>{data.alert && <> · التنبيه <span dir="ltr">{data.alert.alert_at}</span> ({data.alert.minutes} دقيقة)</>}</span> : <span data-testid="monitoring-no-period">لا توجد حصة دراسية نشطة حاليًا — لا تنبيهات خارج الحصص.</span>}
        actions={<div className="flex flex-wrap items-center gap-2">{lastUpdated && <span className="text-xs text-slate-300" data-testid="last-updated">آخر تحديث: {lastUpdated}</span>}<Button variant="header" onClick={refreshMonitoring} disabled={query.isFetching} data-testid="manual-refresh"><RefreshCw aria-hidden size={17} className={query.isFetching ? "animate-spin" : ""} /> تحديث</Button></div>}
      />

      <PreparationTodayCard schoolId={activeSchoolId} selectedPeriod={selectedSequence} />

      {data.period && (
        <>
          <section className="grid grid-cols-2 gap-2 sm:grid-cols-5" data-testid="monitoring-kpis">
            <MetricCard testId="kpi-total" label="الفصول" value={kpis.total} icon={Layers3} valueFirst />
            <MetricCard testId="kpi-submitted" label="تم التحضير" value={kpis.submitted} icon={CheckCircle2} tone="teal" valueFirst />
            <MetricCard testId="kpi-in-progress" label="قيد التحضير" value={kpis.inProgress} icon={LoaderCircle} tone="blue" valueFirst />
            <MetricCard testId="kpi-not-started" label="لم يبدأ" value={kpis.notStarted} icon={Clock3} tone="amber" valueFirst />
            <MetricCard testId="kpi-overdue" label="متأخر" value={kpis.overdue} icon={AlertTriangle} tone="red" valueFirst />
          </section>

          <section className="flex flex-wrap items-center gap-2 rounded-xl border border-slate-200 bg-white p-3 shadow-sm">
            <label className="text-sm text-slate-600">
              الحالة{" "}
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value as StatusFilter)}
                className="rounded-lg border border-slate-300 px-2 py-1.5"
                data-testid="status-filter"
              >
                {STATUS_FILTERS.map((f) => (
                  <option key={f.value} value={f.value}>
                    {f.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="text-sm text-slate-600">
              الصف{" "}
              <select
                value={gradeFilter}
                onChange={(e) =>
                  setGradeFilter(e.target.value === "" ? "" : Number(e.target.value))
                }
                className="rounded-lg border border-slate-300 px-2 py-1.5"
                data-testid="grade-filter"
              >
                <option value="">الكل</option>
                {grades.map(([id, name]) => (
                  <option key={id} value={id}>
                    {name}
                  </option>
                ))}
              </select>
            </label>
            <input
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="بحث بالصف أو الفصل أو القسم"
              aria-label="بحث بالصف أو الفصل أو القسم"
              className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm"
            />
            {hasFilters && (
              <Button
                variant="secondary"
                onClick={() => {
                  setStatusFilter("ALL");
                  setGradeFilter("");
                  setSearch("");
                }}
                data-testid="clear-filters"
              >
                مسح الفلاتر
              </Button>
            )}
          </section>

          <section ref={listRef} tabIndex={-1} className="scroll-mt-28 rounded-2xl border border-slate-200 bg-white shadow-sm focus:outline-none" aria-label="قائمة فصول الحصة">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 px-4 py-4 sm:px-5">
              <div><h2 className="font-black text-slate-900">فصول {data.period.name}</h2><p className="mt-1 text-xs text-slate-500">راجع الفصل والقسم، ثم افتح التحضير أو استكمل الجلسة القائمة.</p></div>
              <span className="rounded-lg bg-slate-100 px-3 py-1.5 text-xs font-bold text-slate-600">{filtered.length} من {data.sections.length} فصول</span>
            </div>
            {filtered.length === 0 ? (
              <p className="p-6 text-slate-600" data-testid="monitoring-empty">
                {statusFilter === "INCOMPLETE" && data.sections.length > 0 && data.sections.every((section) => section.attendance_status === "SUBMITTED")
                  ? "اكتمل تحضير جميع فصول هذه الحصة."
                  : data.sections.length === 0
                  ? "لا توجد فصول نشطة."
                  : "لا توجد فصول مطابقة للفلاتر الحالية."}
              </p>
            ) : (
              <ul className="divide-y divide-slate-100" data-testid="monitoring-list">
                {filtered.map((section) => {
                  const p = statusPresentation(section);
                  return (
                    <li
                      key={section.section_id}
                      className="flex flex-col gap-4 p-4 transition hover:bg-slate-50/70 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between sm:p-5"
                      data-testid={`monitoring-section-${section.section_id}`}
                    >
                      <div className="min-w-28">
                        <p className="font-medium text-slate-800">{sectionLabel(section.grade_name, section.section_name, section.department)}</p>
                        <p className="text-xs text-slate-500">
                          {section.students_count} {studentCountLabel(schoolType)}
                        </p>
                      </div>
                      <span
                        className={`rounded-full px-3 py-1 text-sm ${p.className}`}
                        data-testid="section-status"
                      >
                        <span aria-hidden>{p.icon}</span> {p.label}
                      </span>
                      <div className="flex gap-4 text-sm text-slate-600">
                        <span>
                          البدء: <span dir="ltr">{section.started_at ?? "—"}</span>
                        </span>
                        <span>
                          الاعتماد: <span dir="ltr">{section.submitted_at ?? "—"}</span>
                        </span>
                        <span className="min-w-24">{section.teacher_name ?? "—"}</span>
                      </div>
                      {data.period && (
                        <Link
                          to={`/attendance/section/${section.section_id}?date=${data.date}&period=${data.period?.sequence}`}
                          data-testid={`${section.attendance_status === "SUBMITTED" ? "correct" : "prepare"}-section-${section.section_id}`}
                          className="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl bg-slate-900 px-4 py-2 text-sm font-bold text-white shadow-sm transition hover:bg-teal-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-700"
                        >
                          <ClipboardCheck aria-hidden size={17} />
                          {section.attendance_status === "SUBMITTED" ? "عرض / تصحيح التحضير" : section.attendance_status === "IN_PROGRESS" ? "استكمال التحضير" : "تحضير الفصل"}
                          <ArrowLeft aria-hidden size={15} />
                        </Link>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}
          </section>
        </>
      )}
    </div>
  );
}
