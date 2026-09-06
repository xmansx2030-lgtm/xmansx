import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, BriefcaseBusiness, CalendarClock, CheckCircle2, CircleDot, ClipboardCheck, Inbox, ListFilter, MessageSquareReply, ShieldCheck, Sparkles, TriangleAlert, X } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { MetricCard } from "@/components/MetricCard";
import { PageHeader } from "@/components/PageHeader";
import { Spinner } from "@/components/Spinner";
import { schoolScopedKey, useMe } from "@/features/auth/useMe";
import { getCases, getCounselorDashboard } from "@/features/counseling/api";
import { useActiveSchoolId } from "@/features/settings/hooks";
import { roleLabel } from "@/utils/roles";

const KPI_CARDS: { key: keyof import("@/features/counseling/api").DashboardKpis; label: string; icon: LucideIcon; tone: "teal" | "blue" | "amber" | "red" | "violet" | "neutral" }[] = [
  { key: "new_referrals", label: "إحالات جديدة", icon: Inbox, tone: "blue" },
  { key: "open_cases", label: "حالات مفتوحة", icon: CircleDot, tone: "teal" },
  { key: "under_assessment", label: "قيد الدراسة", icon: ClipboardCheck, tone: "violet" },
  { key: "follow_up_active", label: "تحت المتابعة", icon: ShieldCheck, tone: "teal" },
  { key: "waiting_teacher_response", label: "بانتظار رد معلم", icon: MessageSquareReply, tone: "amber" },
  { key: "due_activities", label: "إجراءات مستحقة", icon: CalendarClock, tone: "red" },
  { key: "closed_this_month", label: "أغلقت هذا الشهر", icon: CheckCircle2, tone: "neutral" },
];

const CATEGORIES: Record<string, string> = {
  ATTENDANCE: "المواظبة",
  ACADEMIC: "الأداء الدراسي",
  CLASSROOM_BEHAVIOR: "سلوك صفي",
  SOCIAL: "اجتماعي",
  OTHER: "أخرى",
};

const STATUS_STYLES: Record<string, string> = {
  OPEN: "bg-blue-50 text-blue-800 ring-blue-100",
  UNDER_ASSESSMENT: "bg-violet-50 text-violet-800 ring-violet-100",
  FOLLOW_UP_ACTIVE: "bg-teal-50 text-teal-800 ring-teal-100",
  RESOLVED: "bg-emerald-50 text-emerald-800 ring-emerald-100",
  CLOSED: "bg-slate-100 text-slate-700 ring-slate-200",
};

const PRIORITY_STYLES: Record<string, string> = {
  URGENT: "bg-red-50 text-red-700 ring-red-100",
  HIGH: "bg-amber-50 text-amber-800 ring-amber-100",
  NORMAL: "bg-slate-100 text-slate-600 ring-slate-200",
  LOW: "bg-slate-50 text-slate-500 ring-slate-200",
};

/** لوحة المرشد: مؤشرات + قائمة الحالات بفلاترها وترتيبها (البنود 56-61). */
export function CounselorDashboardPage() {
  const schoolId = useActiveSchoolId();
  const me = useMe();
  const schoolType = me.data?.active_school?.school_type ?? "BOYS";
  const [status, setStatus] = useState("live");
  const [category, setCategory] = useState("");
  const [sort, setSort] = useState("recent");
  const [page, setPage] = useState(1);

  const kpis = useQuery({
    queryKey: schoolScopedKey(schoolId, "counselor-dashboard"),
    queryFn: ({ signal }) => getCounselorDashboard(signal),
    enabled: schoolId > 0,
  });
  const cases = useQuery({
    queryKey: schoolScopedKey(schoolId, "counselor-cases", status, category, sort, page),
    queryFn: ({ signal }) => getCases({ status, category, sort, page }, signal),
    enabled: schoolId > 0,
  });

  if (me.isPending || kpis.isPending) return <Spinner />;
  if (kpis.isError) return <ErrorState error={kpis.error} />;

  const rows = cases.data?.results ?? [];
  const count = cases.data?.count ?? 0;
  const needsAttention = (kpis.data?.due_activities ?? 0) + (kpis.data?.waiting_teacher_response ?? 0);
  const hasActiveFilters = status !== "live" || category !== "" || sort !== "recent";

  const resetFilters = () => {
    setStatus("live");
    setCategory("");
    setSort("recent");
    setPage(1);
  };

  return (
    <div className="space-y-5">
      <PageHeader
        icon={BriefcaseBusiness}
        eyebrow={`مساحة ${roleLabel("COUNSELOR", schoolType)}`}
        title="لوحة الإرشاد الطلابي"
        description="صندوق عمل موحّد للإحالات والحالات وخطط المتابعة، مرتب حسب ما يحتاج إلى تدخل أولًا."
        tone="counselor"
        badge={me.data?.active_school?.name ?? roleLabel("COUNSELOR", schoolType)}
        meta={`${kpis.data?.due_activities ?? 0} إجراءات مستحقة · ${kpis.data?.waiting_teacher_response ?? 0} بانتظار رد ${roleLabel("TEACHER", schoolType)}`}
        actions={<Link to="/referrals" className="inline-flex min-h-11 items-center gap-2 rounded-xl bg-white px-4 py-2.5 text-sm font-bold text-slate-950 shadow-lg transition hover:bg-slate-50"><Inbox aria-hidden size={18} /> صندوق الإحالات</Link>}
        testId="counselor-workspace-header"
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4" data-testid="counselor-kpis">
        {KPI_CARDS.map((card) => (
          <MetricCard
            key={card.key}
            label={card.key === "waiting_teacher_response" ? `بانتظار رد ${roleLabel("TEACHER", schoolType)}` : card.label}
            value={kpis.data?.[card.key] ?? 0}
            icon={card.icon}
            tone={card.tone}
            testId={`kpi-${card.key}`}
          />
        ))}
      </div>

      <section className="overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-sm">
        <div className="grid gap-4 border-b border-slate-100 bg-gradient-to-l from-teal-50 via-white to-violet-50 px-4 py-4 sm:px-5 lg:grid-cols-[1fr_auto] lg:items-center">
          <div className="flex items-start gap-3">
            <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-slate-950 text-teal-200 shadow-lg shadow-slate-950/10"><Sparkles aria-hidden size={18} /></span>
            <div>
              <p className="text-xs font-bold text-teal-800">بداية منظمة</p>
              <h2 className="mt-0.5 font-black text-slate-900">ركّز على الإجراء التالي</h2>
              <p className="mt-1 text-xs leading-5 text-slate-600">{needsAttention > 0 ? `لديك ${needsAttention} بندًا يحتاج متابعة؛ رتّب الحالات ثم افتح ملف الطالب مباشرة.` : "لا توجد إجراءات عاجلة الآن؛ راجع الحالات النشطة لضمان استمرارية المتابعة."}</p>
            </div>
          </div>
          <div className="inline-flex items-center gap-2 self-start rounded-full bg-white/90 px-3 py-2 text-xs font-bold text-slate-700 ring-1 ring-slate-200 lg:self-auto">
            <TriangleAlert aria-hidden size={15} className={needsAttention > 0 ? "text-amber-600" : "text-teal-700"} />
            {needsAttention > 0 ? `${needsAttention} تحتاج انتباهك` : "صندوق العمل مستقر"}
          </div>
        </div>
        <div className="p-4 sm:p-5">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <span className="grid size-8 place-items-center rounded-lg bg-slate-100 text-slate-600"><ListFilter aria-hidden size={16} /></span>
              <div><h3 className="text-sm font-black text-slate-900">تنظيم صندوق الحالات</h3><p className="text-xs text-slate-500">المرشحات لا تغيّر بيانات الحالة.</p></div>
            </div>
            {hasActiveFilters && <button type="button" onClick={resetFilters} className="inline-flex min-h-9 items-center gap-1.5 rounded-lg px-2.5 text-xs font-bold text-teal-800 transition hover:bg-teal-50"><X aria-hidden size={15} /> مسح المرشحات</button>}
          </div>
          <div className="grid gap-3 sm:grid-cols-3">
        <label className="flex flex-col gap-1.5 text-xs font-bold text-slate-600">
          الحالة
          <select
            data-testid="case-status-filter"
            value={status}
            onChange={(event) => {
              setStatus(event.target.value);
              setPage(1);
            }}
            className="w-full rounded-xl border border-slate-300 px-3 py-2"
          >
            <option value="live">الحالات الحية</option>
            <option value="OPEN">مفتوحة</option>
            <option value="UNDER_ASSESSMENT">قيد الدراسة</option>
            <option value="FOLLOW_UP_ACTIVE">متابعة جارية</option>
            <option value="RESOLVED">تم التحسن</option>
            <option value="CLOSED">مغلقة</option>
            <option value="">الكل</option>
          </select>
        </label>

        <label className="flex flex-col gap-1.5 text-xs font-bold text-slate-600">
          الفئة
          <select
            data-testid="case-category-filter"
            value={category}
            onChange={(event) => {
              setCategory(event.target.value);
              setPage(1);
            }}
            className="w-full rounded-xl border border-slate-300 px-3 py-2"
          >
            <option value="">كل الفئات</option>
            {Object.entries(CATEGORIES).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>

        <label className="flex flex-col gap-1.5 text-xs font-bold text-slate-600">
          الترتيب
          <select
            data-testid="case-sort"
            value={sort}
            onChange={(event) => setSort(event.target.value)}
            className="w-full rounded-xl border border-slate-300 px-3 py-2"
          >
            <option value="recent">الأحدث نشاطًا</option>
            <option value="oldest_unattended">الأقدم بلا متابعة</option>
            <option value="opened">الأحدث فتحًا</option>
          </select>
        </label>
          </div>
        </div>
      </section>

      {cases.isError && <ErrorState error={cases.error} />}
      {cases.isPending ? (
        <Spinner />
      ) : rows.length === 0 ? (
        <EmptyState title="لا توجد حالات مطابقة" description="جرّب تغيير الفلاتر، أو راجع صندوق الإحالات الجديدة لبدء حالة متابعة." testId="no-cases" />
      ) : (
        <>
        <div className="hidden overflow-x-auto rounded-3xl border border-slate-200 bg-white shadow-sm lg:block">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-slate-600">
              <tr>
                <th className="p-3 text-start">الطالب</th>
                <th className="p-3 text-start">الصف/الفصل</th>
                <th className="p-3 text-start">سبب الإحالة</th>
                <th className="p-3 text-start">المرشد</th>
                <th className="p-3 text-start">الحالة</th>
                <th className="p-3 text-start">آخر نشاط</th>
                <th className="p-3 text-start">الإجراء القادم</th>
                <th className="p-3 text-start"></th>
              </tr>
            </thead>
            <tbody data-testid="cases-table">
              {rows.map((row) => (
                <tr key={row.id} className="border-b border-slate-100" data-testid={`case-row-${row.id}`}>
                  <td className="p-4"><div className="flex items-center gap-2.5"><span className="grid size-9 shrink-0 place-items-center rounded-xl bg-teal-50 text-xs font-black text-teal-800">{row.student_name.slice(0, 1)}</span><span className="font-black text-slate-900">{row.student_name}</span></div></td>
                  <td className="p-4">
                    {row.grade_name ?? "—"} / {row.section_name ?? "—"}
                  </td>
                  <td className="p-4"><p className="font-bold text-slate-700">{row.referral_reason_label}</p><span className={`mt-1 inline-flex rounded-full px-2 py-0.5 text-[11px] font-bold ring-1 ${PRIORITY_STYLES[row.priority] ?? PRIORITY_STYLES.NORMAL}`}>{row.priority_label}</span></td>
                  <td className="p-4">{row.counselor_name ?? "—"}</td>
                  <td className="p-4"><span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-bold ring-1 ${STATUS_STYLES[row.status] ?? STATUS_STYLES.OPEN}`}>{row.status_label}</span></td>
                  <td className="p-4 whitespace-nowrap text-slate-600">{row.last_activity_at.slice(0, 10)}</td>
                  <td className="p-4 whitespace-nowrap font-bold text-slate-700">{row.next_activity_due ?? "—"}</td>
                  <td className="p-4">
                    <Link
                      to={`/counselor/cases/${row.id}`}
                      className="inline-flex items-center gap-1.5 whitespace-nowrap font-bold text-blue-700 underline decoration-blue-200 underline-offset-4"
                      data-testid={`open-case-${row.id}`}
                    >
                      فتح الملف <ArrowLeft aria-hidden size={15} />
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="grid gap-3 lg:hidden">
          {rows.map((row) => (
            <article key={row.id} className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm" data-testid={`case-mobile-${row.id}`}>
              <div className="flex items-start justify-between gap-3">
                <div className="flex min-w-0 items-center gap-2.5"><span className="grid size-10 shrink-0 place-items-center rounded-xl bg-teal-50 text-sm font-black text-teal-800">{row.student_name.slice(0, 1)}</span><div className="min-w-0"><h3 className="truncate font-black text-slate-900">{row.student_name}</h3><p className="mt-0.5 text-xs text-slate-500">{row.grade_name ?? "—"} / {row.section_name ?? "—"}</p></div></div>
                <span className={`shrink-0 rounded-full px-2.5 py-1 text-[11px] font-bold ring-1 ${STATUS_STYLES[row.status] ?? STATUS_STYLES.OPEN}`}>{row.status_label}</span>
              </div>
              <div className="mt-4 grid grid-cols-2 gap-3 rounded-xl bg-slate-50 p-3 text-xs"><div><p className="text-slate-500">سبب الإحالة</p><p className="mt-1 font-bold text-slate-800">{row.referral_reason_label}</p></div><div><p className="text-slate-500">الإجراء القادم</p><p className="mt-1 font-bold text-slate-800">{row.next_activity_due ?? "—"}</p></div></div>
              <div className="mt-3 flex items-center justify-between gap-3"><span className={`inline-flex rounded-full px-2 py-0.5 text-[11px] font-bold ring-1 ${PRIORITY_STYLES[row.priority] ?? PRIORITY_STYLES.NORMAL}`}>{row.priority_label}</span><Link to={`/counselor/cases/${row.id}`} className="inline-flex min-h-9 items-center gap-1.5 rounded-lg bg-slate-950 px-3 text-xs font-bold text-white shadow-sm transition hover:bg-teal-900" data-testid={`open-case-mobile-${row.id}`}>فتح الملف <ArrowLeft aria-hidden size={14} /></Link></div>
            </article>
          ))}
        </div>
        </>
      )}

      {count > rows.length && (
        <div className="flex flex-wrap items-center gap-3 rounded-2xl border border-slate-200 bg-white p-3 text-sm shadow-sm">
          <button
            type="button"
            onClick={() => setPage((value) => Math.max(1, value - 1))}
            disabled={page === 1}
            className="min-h-10 rounded-xl border border-slate-300 px-3 disabled:opacity-50"
          >
            السابق
          </button>
          <span>
            صفحة {page} — الإجمالي {count}
          </span>
          <button
            type="button"
            onClick={() => setPage((value) => value + 1)}
            disabled={rows.length === 0}
            className="min-h-10 rounded-xl border border-slate-300 px-3 disabled:opacity-50"
          >
            التالي
          </button>
        </div>
      )}
    </div>
  );
}
