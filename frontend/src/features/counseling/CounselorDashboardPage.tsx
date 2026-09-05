import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, BriefcaseBusiness, CalendarClock, CheckCircle2, CircleDot, ClipboardCheck, Filter, Inbox, MessageSquareReply, ShieldCheck } from "lucide-react";
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

/** لوحة المرشد: مؤشرات + قائمة الحالات بفلاترها وترتيبها (البنود 56-61). */
export function CounselorDashboardPage() {
  const schoolId = useActiveSchoolId();
  const me = useMe();
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

  return (
    <div className="space-y-5">
      <PageHeader
        icon={BriefcaseBusiness}
        eyebrow="مساحة المرشد الطلابي"
        title="لوحة الإرشاد الطلابي"
        description="صندوق عمل موحّد للإحالات والحالات وخطط المتابعة، مرتب حسب ما يحتاج إلى تدخل أولًا."
        tone="counselor"
        badge={me.data?.active_school?.name ?? "المرشد الطلابي"}
        meta={`${kpis.data?.due_activities ?? 0} إجراءات مستحقة · ${kpis.data?.waiting_teacher_response ?? 0} بانتظار رد معلم`}
        actions={<Link to="/referrals" className="inline-flex min-h-11 items-center gap-2 rounded-xl bg-white px-4 py-2.5 text-sm font-bold text-slate-950 shadow-lg transition hover:bg-slate-50"><Inbox aria-hidden size={18} /> صندوق الإحالات</Link>}
        testId="counselor-workspace-header"
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4" data-testid="counselor-kpis">
        {KPI_CARDS.map((card) => (
          <MetricCard
            key={card.key}
            label={card.label}
            value={kpis.data?.[card.key] ?? 0}
            icon={card.icon}
            tone={card.tone}
            testId={`kpi-${card.key}`}
          />
        ))}
      </div>

      <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5">
        <div className="mb-4 flex items-start gap-3"><span className="grid size-10 place-items-center rounded-xl bg-slate-100 text-slate-600"><Filter aria-hidden size={18} /></span><div><h2 className="font-black text-slate-900">تنظيم صندوق الحالات</h2><p className="mt-1 text-xs text-slate-500">فلترة الحالات وترتيبها لاختيار الإجراء التالي بوضوح.</p></div></div>
      <div className="grid gap-3 sm:grid-cols-3">
        <label className="flex flex-col gap-1 text-sm">
          الحالة
          <select
            data-testid="case-status-filter"
            value={status}
            onChange={(event) => {
              setStatus(event.target.value);
              setPage(1);
            }}
            className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2"
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

        <label className="flex flex-col gap-1 text-sm">
          الفئة
          <select
            data-testid="case-category-filter"
            value={category}
            onChange={(event) => {
              setCategory(event.target.value);
              setPage(1);
            }}
            className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2"
          >
            <option value="">كل الفئات</option>
            {Object.entries(CATEGORIES).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>

        <label className="flex flex-col gap-1 text-sm">
          الترتيب
          <select
            data-testid="case-sort"
            value={sort}
            onChange={(event) => setSort(event.target.value)}
            className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2"
          >
            <option value="recent">الأحدث نشاطًا</option>
            <option value="oldest_unattended">الأقدم بلا متابعة</option>
            <option value="opened">الأحدث فتحًا</option>
          </select>
        </label>
      </div></section>

      {cases.isError && <ErrorState error={cases.error} />}
      {cases.isPending ? (
        <Spinner />
      ) : rows.length === 0 ? (
        <EmptyState title="لا توجد حالات مطابقة" description="جرّب تغيير الفلاتر، أو راجع صندوق الإحالات الجديدة لبدء حالة متابعة." testId="no-cases" />
      ) : (
        <div className="overflow-x-auto rounded-2xl border border-slate-200 bg-white shadow-sm">
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
                <tr key={row.id} className="border-b" data-testid={`case-row-${row.id}`}>
                  <td className="p-3 font-bold text-slate-900">{row.student_name}</td>
                  <td className="p-3">
                    {row.grade_name ?? "—"} / {row.section_name ?? "—"}
                  </td>
                  <td className="p-3">{row.referral_reason_label}</td>
                  <td className="p-3">{row.counselor_name ?? "—"}</td>
                  <td className="p-3"><span className="inline-flex rounded-full bg-teal-50 px-2.5 py-1 text-xs font-bold text-teal-800 ring-1 ring-teal-100">{row.status_label}</span></td>
                  <td className="p-3">{row.last_activity_at.slice(0, 10)}</td>
                  <td className="p-3">{row.next_activity_due ?? "—"}</td>
                  <td className="p-3">
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
      )}

      {count > rows.length && (
        <div className="flex items-center gap-3 text-sm">
          <button
            type="button"
            onClick={() => setPage((value) => Math.max(1, value - 1))}
            disabled={page === 1}
            className="rounded-lg border border-slate-300 px-3 py-1 disabled:opacity-50"
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
            className="rounded-lg border border-slate-300 px-3 py-1 disabled:opacity-50"
          >
            التالي
          </button>
        </div>
      )}
    </div>
  );
}
