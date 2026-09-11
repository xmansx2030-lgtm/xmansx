import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  AlertTriangle,
  ArrowLeft,
  BarChart3,
  BellRing,
  CalendarDays,
  CheckCircle2,
  ChevronDown,
  Clock3,
  DoorOpen,
  FileCheck2,
  Filter,
  GraduationCap,
  Settings,
  RefreshCw,
  Send,
  ShieldAlert,
  Sparkles,
  UsersRound,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { ApiError } from "@/api/client";
import { Button } from "@/components/Button";
import { ErrorState } from "@/components/ErrorState";
import { PageHeader } from "@/components/PageHeader";
import { Spinner } from "@/components/Spinner";
import { getAttendanceSections } from "@/features/attendance/api";
import { schoolScopedKey, useMe } from "@/features/auth/useMe";
import type {
  AttentionItem,
  Comparison,
  DashboardFilters,
  DashboardPreset,
  OverviewResponse,
  SectionsResponse,
  TodayOperations,
} from "@/features/dashboard/api";
import {
  getAttention,
  getOverview,
  getSections,
  getToday,
  getTrend,
} from "@/features/dashboard/api";
import { TrendChart } from "@/features/dashboard/TrendChart";
import { getStaff } from "@/features/staff/api";
import type { SchoolType } from "@/types/auth";
import { roleGenitivePluralLabel, roleLabel as schoolRoleLabel, studentCountLabel, studentLabel, studentPluralLabel } from "@/utils/roles";

/** تحديث متدرج: التشغيل أسرع، والتنبيهات أبطأ، والتحليلات لا تُحمّل كل عدة ثوانٍ. */
// نافذة قصيرة حتى تنعكس اعتمادات المعلمين على شاشة الإدارة دون إعادة تحميل.
const LIVE_POLL_MS = 5_000;
const ATTENTION_POLL_MS = 60_000;
const OVERVIEW_POLL_MS = 120_000;
const ANALYTICS_POLL_MS = 300_000;

const PRESETS: [DashboardPreset, string][] = [
  ["TODAY", "اليوم"],
  ["THIS_WEEK", "هذا الأسبوع"],
  ["LAST_7_DAYS", "آخر ٧ أيام"],
  ["LAST_30_DAYS", "آخر ٣٠ يومًا"],
  ["THIS_MONTH", "هذا الشهر"],
  ["CURRENT_SEMESTER", "الفصل الحالي"],
  ["CUSTOM", "فترة مخصصة"],
];

function localIsoDate(offsetDays = 0): string {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

/**
 * لوحة إدارة المدرسة (م15) — طبقة قراءة فوق أنظمة قائمة.
 *
 * كل رقم هنا مصدره الخادم، بما فيه المقارنة مع الفترة السابقة: الواجهة لا تحسب
 * نسبًا ولا تجمع مؤشرات، وإلا اختلف رقم اللوحة عن رقم التقرير المتخصص.
 */
export function DashboardPage() {
  const me = useMe();
  const activeSchoolId = me.data?.active_school?.id ?? 0;

  const [preset, setPreset] = useState<DashboardPreset>("LAST_7_DAYS");
  const [fromDate, setFromDate] = useState(localIsoDate(-6));
  const [toDate, setToDate] = useState(localIsoDate());
  const [gradeId, setGradeId] = useState<number | "">("");
  const [sectionId, setSectionId] = useState<number | "">("");

  const filters: DashboardFilters = { preset, fromDate, toDate, gradeId, sectionId };
  const filterKey = [preset, fromDate, toDate, gradeId, sectionId];
  const enabled = activeSchoolId > 0;
  const canManageCalendar = me.data?.roles.includes("SCHOOL_MANAGER") ?? false;
  const analyticsEnabled = enabled;

  const sectionsListQuery = useQuery({
    queryKey: schoolScopedKey(activeSchoolId, "attendance", "sections"),
    queryFn: ({ signal }) => getAttendanceSections(signal),
    enabled: analyticsEnabled,
  });
  const teachersQuery = useQuery({
    queryKey: schoolScopedKey(activeSchoolId, "dashboard", "setup", "teachers"),
    queryFn: ({ signal }) =>
      getStaff({ page: 1, role: "TEACHER", status: "ACTIVE" }, signal),
    enabled: enabled && canManageCalendar,
  });
  const overviewQuery = useQuery({
    queryKey: schoolScopedKey(activeSchoolId, "dashboard", "overview", ...filterKey),
    queryFn: ({ signal }) => getOverview(filters, signal),
    enabled: analyticsEnabled,
    refetchInterval: OVERVIEW_POLL_MS,
  });
  const todayQuery = useQuery({
    queryKey: schoolScopedKey(activeSchoolId, "dashboard", "today"),
    queryFn: ({ signal }) => getToday(signal),
    enabled,
    refetchInterval: LIVE_POLL_MS,
    refetchIntervalInBackground: true,
  });
  const trendQuery = useQuery({
    queryKey: schoolScopedKey(activeSchoolId, "dashboard", "trend", ...filterKey),
    queryFn: ({ signal }) => getTrend(filters, signal),
    enabled: analyticsEnabled,
    refetchInterval: ANALYTICS_POLL_MS,
  });
  const sectionsQuery = useQuery({
    queryKey: schoolScopedKey(activeSchoolId, "dashboard", "sections", ...filterKey),
    queryFn: ({ signal }) => getSections(filters, signal),
    enabled: analyticsEnabled,
    refetchInterval: ANALYTICS_POLL_MS,
  });
  const attentionQuery = useQuery({
    queryKey: schoolScopedKey(activeSchoolId, "dashboard", "attention"),
    queryFn: ({ signal }) => getAttention(signal),
    enabled,
    refetchInterval: ATTENTION_POLL_MS,
  });

  const academicSetupRequired = [
    overviewQuery.error,
    todayQuery.error,
    trendQuery.error,
    sectionsQuery.error,
    attentionQuery.error,
  ].some(
    (error) =>
      error instanceof ApiError && error.code === "ACTIVE_ACADEMIC_YEAR_REQUIRED",
  );
  const schoolType = me.data?.active_school?.school_type ?? "BOYS";
  const workspaceRoleLabel = schoolRoleLabel(
    canManageCalendar ? "SCHOOL_MANAGER" : "VICE_PRINCIPAL",
    schoolType,
  );
  const liveToday = todayQuery.data ?? (canManageCalendar ? overviewQuery.data?.today_operations : undefined);
  const highPriorityCount =
    attentionQuery.data?.items.filter((item) => item.priority === "HIGH").length ?? 0;
  const lastUpdatedAt = Math.max(
    todayQuery.dataUpdatedAt,
    attentionQuery.dataUpdatedAt,
    canManageCalendar ? overviewQuery.dataUpdatedAt : 0,
  );
  const isRefreshing =
    todayQuery.isFetching || attentionQuery.isFetching || overviewQuery.isFetching;
  const needsStudentImport =
    sectionsListQuery.isSuccess &&
    (sectionsListQuery.data.length === 0 ||
      sectionsListQuery.data.every((section) => section.students_count === 0));
  const needsTeacherImport = teachersQuery.isSuccess && teachersQuery.data.count === 0;

  const grades = useMemo(() => {
    const map = new Map<number, string>();
    for (const s of sectionsListQuery.data ?? []) {
      if (s.grade_id != null) map.set(s.grade_id, s.grade_name);
    }
    return [...map.entries()];
  }, [sectionsListQuery.data]);
  const sectionOptions = (sectionsListQuery.data ?? []).filter(
    (s) => gradeId === "" || s.grade_id === gradeId,
  );

  function refreshOperationalData() {
    const refreshes: Promise<unknown>[] = [todayQuery.refetch(), attentionQuery.refetch()];
    if (canManageCalendar) refreshes.push(overviewQuery.refetch());
    void Promise.all(refreshes);
  }

  return (
    <div className="ds-page" data-testid="dashboard-page">
      <PageHeader
        icon={Sparkles}
        eyebrow="مركز قيادة المدرسة"
        title={me.data?.active_school?.name ?? "لوحة إدارة المدرسة"}
        description="متابعة مباشرة لما يحدث الآن، وما يحتاج إلى إجراء إداري دون تأخير."
        tone="executive"
        badge={workspaceRoleLabel}
        meta={overviewQuery.isSuccess ? (
          <span className="flex flex-wrap items-center gap-2" data-testid="dashboard-context">
            <CalendarDays aria-hidden size={14} />
            {overviewQuery.data.context.academic_year?.name ?? "لا يوجد عام دراسي نشط"}
            {overviewQuery.data.context.semester ? ` · ${overviewQuery.data.context.semester.name}` : ""}
            <span>· {overviewQuery.data.context.today}</span>
          </span>
        ) : undefined}
        actions={(
          <div className="flex flex-col items-start gap-3 lg:items-end">
            <div className="flex flex-wrap items-center gap-2">
              {highPriorityCount > 0 && (
                <span className="inline-flex items-center gap-2 rounded-xl bg-red-500/15 px-3 py-2 text-xs font-bold text-red-100 ring-1 ring-red-400/25">
                  <ShieldAlert aria-hidden size={16} /> {highPriorityCount} إجراء عالي الأولوية
                </span>
              )}
              <Button variant="headerGhost" onClick={refreshOperationalData} disabled={isRefreshing}>
                <RefreshCw aria-hidden size={16} className={isRefreshing ? "animate-spin" : ""} />
                تحديث الآن
              </Button>
            </div>
            <p className="flex items-center gap-2 text-[11px] text-slate-400" data-testid="dashboard-last-updated">
              <span className="relative flex size-2"><span className="absolute inline-flex size-full animate-ping rounded-full bg-emerald-400 opacity-40" /><span className="relative inline-flex size-2 rounded-full bg-emerald-400" /></span>
              تحديث تلقائي كل 5 ثوانٍ
              {lastUpdatedAt > 0 && ` · آخر تحديث ${new Date(lastUpdatedAt).toLocaleTimeString("ar-SA", { hour: "2-digit", minute: "2-digit" })}`}
            </p>
          </div>
        )}
      >
        {canManageCalendar && (
          <nav aria-label="إجراءات سريعة" className="relative flex flex-wrap gap-2">
            <QuickLink to="/attendance/monitoring" icon={Activity}>متابعة التحضير</QuickLink>
            <QuickLink to="/staff" icon={UsersRound}>فريق المدرسة</QuickLink>
            <QuickLink to="/settings" icon={Settings}>إعدادات المدرسة</QuickLink>
          </nav>
        )}
      </PageHeader>

      {canManageCalendar && (needsStudentImport || needsTeacherImport) && (
        <SchoolSetupAlerts
          schoolType={schoolType}
          needsStudentImport={needsStudentImport}
          needsTeacherImport={needsTeacherImport}
        />
      )}

      {academicSetupRequired ? (
        <section className="rounded-3xl border border-amber-200 bg-amber-50 p-6 shadow-sm" role="status" data-testid="academic-setup-required">
          <div className="flex items-start gap-4">
            <span className="grid size-11 shrink-0 place-items-center rounded-2xl bg-amber-100 text-amber-800"><AlertTriangle aria-hidden size={22} /></span>
            <div>
              <h2 className="text-lg font-black text-amber-950">يلزم تفعيل عام دراسي لبدء التشغيل</h2>
              <p className="mt-2 max-w-3xl text-sm leading-6 text-amber-900">تعتمد مؤشرات الحضور والتنبيهات والفصول على عام دراسي نشط. لن تعرض اللوحة أرقامًا ناقصة أو مضللة قبل اكتمال الإعداد.</p>
              <p className="mt-2 text-sm text-amber-800">{canManageCalendar ? "أنشئ عامًا دراسيًا أو فعّل العام القادم، ثم ارجع إلى هذه اللوحة." : `يمكنك مراجعة التقويم، ويحتاج التفعيل إلى ${schoolRoleLabel("SCHOOL_MANAGER", schoolType)}.`}</p>
              {canManageCalendar && (
                <Link to="/settings?section=calendar" className="mt-4 inline-flex rounded-xl bg-amber-900 px-4 py-2.5 text-sm font-bold text-white hover:bg-amber-950">
                  إعداد العام الدراسي
                </Link>
              )}
            </div>
          </div>
        </section>
      ) : (
        <>
          {!canManageCalendar && (
            <RoleWorkspace
              isManager={false}
              schoolType={schoolType}
              today={liveToday}
              attention={attentionQuery.data}
              isLiveLoading={todayQuery.isPending || attentionQuery.isPending}
            />
          )}

          {liveToday ? (
            <>
              <SchoolTodayStatusCard data={liveToday} schoolType={schoolType} showPreparation={!canManageCalendar} />
              {canManageCalendar && <TodayCard data={liveToday} />}
            </>
          ) : todayQuery.isPending ? (
            <div className="grid min-h-48 place-items-center rounded-3xl border border-slate-200 bg-white"><Spinner label="جارٍ تحميل التشغيل المباشر..." /></div>
          ) : null}

          <AttentionSection query={attentionQuery} schoolType={schoolType} compact />

          {analyticsEnabled && <details className="group overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-sm" data-testid="manager-analytics">
          <summary className="flex cursor-pointer list-none items-center justify-between gap-4 p-5 transition hover:bg-slate-50 sm:p-6">
            <span className="flex items-start gap-3">
              <span className="grid size-11 shrink-0 place-items-center rounded-2xl bg-violet-50 text-violet-700"><BarChart3 aria-hidden size={21} /></span>
              <span><strong className="block text-lg font-black text-slate-900">التحليلات والتقارير</strong><span className="mt-1 block text-xs leading-5 text-slate-500">الفترات والمقارنات واتجاه الغياب وترتيب الفصول.</span></span>
            </span>
            <span className="inline-flex items-center gap-2 text-xs font-bold text-slate-600">عرض التفاصيل <ChevronDown aria-hidden size={18} className="transition-transform group-open:rotate-180" /></span>
          </summary>
          <div className="space-y-5 border-t border-slate-100 bg-slate-50/40 p-4 sm:p-5">
          <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="flex items-start gap-3">
                <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-slate-100 text-slate-600"><Filter aria-hidden size={18} /></span>
                <div><h2 className="font-black text-slate-900">نطاق التحليل</h2><p className="mt-1 text-xs text-slate-500">خصص الفترة أو الصف أو الفصل. التشغيل المباشر أعلاه يبقى لليوم الحالي.</p></div>
              </div>
              {overviewQuery.isSuccess && <p className="text-xs text-slate-500" data-testid="dashboard-range">الفترة {overviewQuery.data.context.range.from_date} إلى {overviewQuery.data.context.range.to_date} ({overviewQuery.data.context.range.days} يومًا) · تُقارن بـ {overviewQuery.data.context.previous_range.from_date} إلى {overviewQuery.data.context.previous_range.to_date} ({overviewQuery.data.context.previous_range.days} يومًا)</p>}
            </div>

            <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <label className="text-xs font-bold text-slate-600">الفترة
                <select value={preset} onChange={(event) => setPreset(event.target.value as DashboardPreset)} className="mt-1 h-10 w-full rounded-xl border border-slate-300 bg-white px-3 text-sm font-medium" data-testid="dashboard-preset">
                  {PRESETS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                </select>
              </label>
              {preset === "CUSTOM" ? (
                <div className="grid grid-cols-2 gap-2 sm:col-span-2">
                  <label className="text-xs font-bold text-slate-600">من<input type="date" value={fromDate} onChange={(event) => setFromDate(event.target.value)} className="mt-1 h-10 w-full rounded-xl border border-slate-300 px-2 text-sm" data-testid="dashboard-from" /></label>
                  <label className="text-xs font-bold text-slate-600">إلى<input type="date" value={toDate} onChange={(event) => setToDate(event.target.value)} className="mt-1 h-10 w-full rounded-xl border border-slate-300 px-2 text-sm" data-testid="dashboard-to" /></label>
                </div>
              ) : null}
              <label className="text-xs font-bold text-slate-600">الصف
                <select value={gradeId} onChange={(event) => { setGradeId(event.target.value === "" ? "" : Number(event.target.value)); setSectionId(""); }} className="mt-1 h-10 w-full rounded-xl border border-slate-300 bg-white px-3 text-sm font-medium" data-testid="dashboard-grade">
                  <option value="">كل الصفوف</option>
                  {grades.map(([id, name]) => <option key={id} value={id}>{name}</option>)}
                </select>
              </label>
              <label className="text-xs font-bold text-slate-600">الفصل
                <select value={sectionId} onChange={(event) => setSectionId(event.target.value === "" ? "" : Number(event.target.value))} className="mt-1 h-10 w-full rounded-xl border border-slate-300 bg-white px-3 text-sm font-medium" data-testid="dashboard-section">
                  <option value="">كل الفصول</option>
                  {sectionOptions.map((section) => <option key={section.id} value={section.id}>{section.grade_name} / {section.name}</option>)}
                </select>
              </label>
            </div>
          </section>

          {overviewQuery.isPending && <div className="grid min-h-40 place-items-center rounded-2xl border border-slate-200 bg-white"><Spinner label="جارٍ تحميل مؤشرات المدرسة..." /></div>}
          {overviewQuery.isError && <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"><ErrorState error={overviewQuery.error} /></section>}
          {overviewQuery.isSuccess && <OverviewBody data={overviewQuery.data} schoolType={schoolType} />}

          <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5">
            <div className="mb-4 flex items-start gap-3"><span className="grid size-10 shrink-0 place-items-center rounded-xl bg-violet-50 text-violet-700"><BarChart3 aria-hidden size={19} /></span><div><h2 className="font-black text-slate-900">اتجاه الغياب</h2><p className="mt-1 text-xs text-slate-500">تغير مؤشرات المواظبة داخل الفترة المحددة.</p></div></div>
            {trendQuery.isPending && <Spinner />}
            {trendQuery.isError && <ErrorState error={trendQuery.error} />}
            {trendQuery.isSuccess && <>{trendQuery.data.granularity === "WEEK" && <p className="mb-3 rounded-xl bg-amber-50 p-3 text-xs text-amber-800" data-testid="trend-aggregated">الفترة طويلة — النقاط مجمّعة أسبوعيًا.</p>}<TrendChart points={trendQuery.data.points} granularity={trendQuery.data.granularity} schoolType={schoolType} /></>}
          </section>

          <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
            <div className="flex items-start gap-3 border-b border-slate-100 p-4 sm:p-5"><span className="grid size-10 shrink-0 place-items-center rounded-xl bg-blue-50 text-blue-700"><GraduationCap aria-hidden size={19} /></span><div><h2 className="font-black text-slate-900">الفصول الأكثر احتياجًا للمتابعة</h2><p className="mt-1 text-xs text-slate-500">مرتبة وصفيًا حسب الغياب بدون عذر في الفترة المحددة.</p></div></div>
            {sectionsQuery.isPending && <div className="p-5"><Spinner /></div>}
            {sectionsQuery.isError && <div className="p-5"><ErrorState error={sectionsQuery.error} /></div>}
            {sectionsQuery.isSuccess && <SectionsTable data={sectionsQuery.data} schoolType={schoolType} />}
          </section>
          </div>
          </details>}
        </>
      )}
    </div>
  );
}

function OverviewBody({ data, schoolType }: { data: OverviewResponse; schoolType: SchoolType }) {
  const a = data.attendance;
  return (
    <>
      {a.completeness.is_significant && (
        <p
          className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900"
          data-testid="completeness-warning"
        >
          ⚠️ {a.completeness.incomplete_pct}% من أيام-{schoolType === "GIRLS" ? "الطالبات" : "الطلاب"} في هذه الفترة لم يكتمل تحضيرها،
          فالأرقام أدناه أقل من الواقع بالضرورة.
        </p>
      )}

      <section>
        <div className="mb-3 flex items-start gap-3"><span className="grid size-10 shrink-0 place-items-center rounded-xl bg-teal-50 text-teal-700"><BarChart3 aria-hidden size={19} /></span><div><h2 className="font-black text-slate-900">مؤشرات الفترة</h2><p className="mt-1 text-xs text-slate-500">ملخص مواظبة المدرسة مع المقارنة بالفترة السابقة.</p></div></div>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4" data-testid="dashboard-kpis">
        <Kpi
          testId="kpi-unexcused-full"
          label="غياب يوم كامل بدون عذر"
          value={a.unexcused_full_absence_days}
          comparison={data.comparison.unexcused_full_absence_days}
        />
        <Kpi
          testId="kpi-excused-full"
          label="غياب يوم كامل بعذر"
          value={a.excused_full_absence_days}
        />
        <Kpi
          testId="kpi-partial"
          label="غياب جزئي"
          value={a.partial_absence_days}
          comparison={data.comparison.partial_absence_days}
        />
        <Kpi
          testId="kpi-morning-late"
          label="تأخر صباحي (مرات)"
          value={a.morning_late_occurrences}
          comparison={data.comparison.morning_late_occurrences}
        />
        <Kpi testId="kpi-absent-periods" label="حصص غياب" value={a.absent_periods} />
        <Kpi
          testId="kpi-undetermined"
          label="أيام غير مكتملة البيانات"
          value={a.undetermined_days}
        />
        <Kpi testId="kpi-student-days" label={`أيام-${studentLabel(schoolType)} مشمولة`} value={a.student_days} />
        </div>
      </section>
      <p className="rounded-xl bg-slate-100 px-3 py-2 text-xs text-slate-500" data-testid="unit-note">
        الوحدة: أيام-{studentLabel(schoolType)} (لا عدد {studentPluralLabel(schoolType)} متفردين) · {a.distinct_students} {studentCountLabel(schoolType)} ضمن الفترة ·
        مصدر التأخر: سجل الوصول الصباحي.
      </p>

      <div className="grid gap-3 md:grid-cols-2">
        <FollowUpCard title="الإنذارات" testId="card-warnings">
          <p className="text-sm text-slate-700">
            صادرة في الفترة:{" "}
            <b data-testid="warnings-issued">{data.warnings.issued_in_range.total}</b>{" "}
            (أول {data.warnings.issued_in_range.level_1} · ثانٍ{" "}
            {data.warnings.issued_in_range.level_2} · ثالث{" "}
            {data.warnings.issued_in_range.level_3})
          </p>
          <p className="mt-1 text-sm text-slate-700" data-testid="warnings-due">
            مستحقة ولم تصدر:{" "}
            <b>
              {Object.values(data.warnings.due_students_by_type).reduce((a2, b) => a2 + b, 0)}
            </b>{" "}
            {studentCountLabel(schoolType)}
          </p>
          <p className="mt-1 text-xs text-slate-500">
            «مستحق» حالة لحظية لا تتبع الفترة المحددة، ولا يُجمع مع «الصادر». الإصدار قرار
            إداري يدوي — لا إصدار تلقائي.
          </p>
          <Link to="/warnings" className="mt-2 inline-block text-xs text-blue-700">
            فتح الإنذارات ←
          </Link>
        </FollowUpCard>

        <FollowUpCard title="الإحالات" testId="card-referrals">
          <p className="text-sm text-slate-700">
            أُنشئت في الفترة:{" "}
            <b data-testid="referrals-created">{data.referrals.created_in_range.total}</b>
          </p>
          <p className="mt-1 text-sm text-slate-700">
            مفتوحة الآن: <b data-testid="referrals-open">{data.referrals.open_now}</b> · بلا
            مرشد معيّن: <b>{data.referrals.unassigned_now}</b>
          </p>
          <p className="mt-1 text-xs text-slate-500">
            أعداد فقط — وصف الإحالة وملاحظات المرشد لا تُعرض في لوحة الإدارة.
          </p>
          <Link to="/referrals" className="mt-2 inline-block text-xs text-blue-700">
            فتح الإحالات ←
          </Link>
        </FollowUpCard>

        <FollowUpCard title="الإجراءات والمستندات" testId="card-actions">
          <p className="text-sm text-slate-700">
            إجراءات منفذة: <b data-testid="actions-total">{data.actions.total}</b>
          </p>
          <p className="mt-1 text-sm text-slate-700">
            مستندات جاهزة: <b data-testid="documents-ready">{data.documents.ready}</b> · قيد
            الإنشاء {data.documents.pending} · فاشلة{" "}
            <span className={data.documents.failed > 0 ? "text-red-700" : ""}>
              {data.documents.failed}
            </span>
          </p>
          <p className="mt-1 text-xs text-slate-500">
            عدد الإجراءات نشاط إداري لا مقياس نجاح.
          </p>
        </FollowUpCard>

        <FollowUpCard title="الحالات الإرشادية" testId="card-counseling">
          {data.counseling.available ? (
            <p className="text-sm text-slate-700">
              حالات مفتوحة: <b data-testid="counseling-open">{data.counseling.open_cases}</b> ·
              بانتظار رد {schoolRoleLabel("TEACHER", schoolType)}: {data.counseling.waiting_teacher_responses} · أنشطة متأخرة:{" "}
              {data.counseling.overdue_activities}
            </p>
          ) : (
            <p className="text-sm text-slate-600" data-testid="counseling-unavailable">
              وحدة الإرشاد غير مفعّلة في هذا الإصدار — لا تُعرض أرقام تقديرية بديلة.
            </p>
          )}
        </FollowUpCard>
      </div>
    </>
  );
}

function SchoolSetupAlerts({
  schoolType,
  needsStudentImport,
  needsTeacherImport,
}: {
  schoolType: SchoolType;
  needsStudentImport: boolean;
  needsTeacherImport: boolean;
}) {
  return (
    <section
      className="rounded-3xl border border-amber-200 bg-amber-50/80 p-4 shadow-sm sm:p-5"
      aria-labelledby="school-setup-alerts-title"
      data-testid="school-setup-alerts"
    >
      <div className="flex items-start gap-3">
        <span className="grid size-11 shrink-0 place-items-center rounded-2xl bg-amber-100 text-amber-800">
          <AlertTriangle aria-hidden size={21} />
        </span>
        <div>
          <h2 id="school-setup-alerts-title" className="font-black text-amber-950">
            استكمل بيانات المدرسة
          </h2>
          <p className="mt-1 text-sm leading-6 text-amber-900">
            نفّذ الخطوات التالية لتصبح شاشة الإدارة والتشغيل جاهزة بالبيانات الفعلية.
          </p>
        </div>
      </div>

      <div className="mt-4 grid gap-3 lg:grid-cols-2">
        {needsStudentImport && (
          <SetupAlert
            to="/students/import"
            icon={GraduationCap}
            title={`استورد بيانات ${studentPluralLabel(schoolType)} والفصول من ملف إكسل (نور)`}
            description="سيتم إنشاء الصفوف والفصول وربط الطلاب بها بعد مراجعة الملف واعتماده."
            testId="setup-alert-students"
          />
        )}
        {needsTeacherImport && (
          <SetupAlert
            to="/staff/import"
            icon={UsersRound}
            title={`استورد بيانات ${roleGenitivePluralLabel("TEACHER", schoolType)} من ملف إكسل (نور)`}
            description="راجع بيانات المعلمين وأدوارهم قبل اعتمادها وإضافتها إلى فريق المدرسة."
            testId="setup-alert-teachers"
          />
        )}
      </div>
    </section>
  );
}

function SetupAlert({
  to,
  icon: Icon,
  title,
  description,
  testId,
}: {
  to: string;
  icon: LucideIcon;
  title: string;
  description: string;
  testId: string;
}) {
  return (
    <article className="rounded-2xl border border-amber-200 bg-white p-4" data-testid={testId}>
      <div className="flex items-start gap-3">
        <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-blue-50 text-blue-700">
          <Icon aria-hidden size={19} />
        </span>
        <div className="min-w-0">
          <h3 className="font-black leading-6 text-slate-900">{title}</h3>
          <p className="mt-1 text-xs leading-5 text-slate-600">{description}</p>
          <Link
            to={to}
            className="mt-3 inline-flex min-h-10 items-center gap-2 rounded-xl bg-amber-900 px-3.5 py-2 text-sm font-bold text-white transition hover:bg-amber-950"
          >
            بدء الاستيراد <ArrowLeft aria-hidden size={15} />
          </Link>
        </div>
      </div>
    </article>
  );
}

function QuickLink({ to, icon: Icon, children }: { to: string; icon: LucideIcon; children: React.ReactNode }) {
  return (
    <Link to={to} className="inline-flex items-center gap-2 rounded-xl bg-white/7 px-3 py-2 text-xs font-bold text-slate-200 ring-1 ring-white/10 transition hover:bg-white/12 hover:text-white">
      <Icon aria-hidden size={15} />{children}<ArrowLeft aria-hidden size={13} className="opacity-60" />
    </Link>
  );
}

/**
 * لا نعرض «لوحة واحدة للجميع»: الوكيل يبدأ بتشغيل اليوم، بينما المدير يبدأ
 * بالإشراف على الحالة والفريق. الأرقام الآنية مصدرها نقاط API القائمة فقط.
 */
function RoleWorkspace({
  isManager,
  schoolType,
  today,
  attention,
  isLiveLoading,
}: {
  isManager: boolean;
  schoolType: SchoolType;
  today?: TodayOperations;
  attention?: import("@/features/dashboard/api").AttentionResponse;
  isLiveLoading: boolean;
}) {
  const overdue = actionableOverdue(today?.summary);
  const submitted = today?.summary?.submitted ?? 0;
  const totalSections = today?.summary?.total ?? 0;
  const highPriority = attention?.items.filter((item) => item.priority === "HIGH").length ?? 0;
  const hasAction = overdue > 0 || highPriority > 0;
  const title = isManager
    ? `مساحة ${schoolType === "GIRLS" ? "المديرة" : "المدير"}`
    : `محطة عمل ${schoolType === "GIRLS" ? "الوكيلة" : "الوكيل"}`;
  const description = isManager
    ? "نظرة إشرافية تجمع التشغيل الفوري مع قرارات إدارة المدرسة."
    : "ابدأ من المهام التي تحفظ انسيابية اليوم الدراسي وتمنع التأخير.";
  const focus = isManager
    ? hasAction
      ? "يوجد ما يحتاج قرارًا أو متابعة"
      : "وضع المدرسة مستقر الآن"
    : overdue > 0
      ? "التحضير يحتاج تدخلاً الآن"
      : today?.has_active_period
        ? "متابعة التحضير أثناء الحصة"
        : "استعداد للمتابعة التالية";
  const metric = isManager
    ? { value: highPriority, label: "أولوية عالية" }
    : today?.has_active_period
      ? { value: `${submitted}/${totalSections}`, label: "فصول تم اعتمادها" }
      : { value: attention?.total ?? 0, label: "مهام مفتوحة" };
  const primary = isManager
    ? { to: "/attendance/monitoring", label: hasAction ? "فتح التشغيل والمتابعة" : "مراجعة التشغيل اليومي", icon: Activity }
    : { to: "/attendance/monitoring", label: overdue > 0 ? "معالجة التحضير المتأخر" : "فتح متابعة التحضير", icon: Activity };
  const secondary = isManager
    ? { to: "/staff", label: "إدارة فريق المدرسة", icon: UsersRound }
    : { to: "/excuses", label: "مراجعة الأعذار", icon: FileCheck2 };
  const PrimaryIcon = primary.icon;
  const SecondaryIcon = secondary.icon;

  return (
    <section
      className="relative overflow-hidden rounded-3xl border border-teal-100 bg-gradient-to-l from-teal-50 via-white to-white p-5 shadow-sm sm:p-6"
      aria-live="polite"
      data-testid="role-workspace"
      data-role={isManager ? "SCHOOL_MANAGER" : "VICE_PRINCIPAL"}
    >
      <div aria-hidden className="absolute -left-10 -bottom-16 size-48 rounded-full bg-teal-200/35 blur-3xl" />
      <div className="relative grid gap-5 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-center">
        <div className="flex min-w-0 items-start gap-4">
          <span className={`grid size-12 shrink-0 place-items-center rounded-2xl ${isManager ? "bg-slate-900 text-teal-200" : "bg-teal-700 text-white"}`}>
            {isManager ? <ShieldAlert aria-hidden size={23} /> : <Activity aria-hidden size={23} />}
          </span>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-xs font-black text-teal-800">{title}</p>
              <span className="inline-flex items-center gap-1.5 text-[11px] font-bold text-slate-500">
                <span className={`size-1.5 rounded-full ${isLiveLoading ? "bg-amber-400" : "bg-emerald-500"}`} />
                {isLiveLoading ? "جارٍ تحديث الحالة" : "حالة مباشرة"}
              </span>
            </div>
            <h2 className="mt-1.5 text-lg font-black text-slate-900">{focus}</h2>
            <p className="mt-1 max-w-2xl text-sm leading-6 text-slate-600">{description}</p>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
          {isManager && (
            <div className={`min-w-32 rounded-2xl border px-4 py-3 ${hasAction ? "border-amber-200 bg-amber-50" : "border-emerald-200 bg-emerald-50"}`} data-testid="role-workspace-metric">
              <p className={`text-2xl font-black tabular-nums ${hasAction ? "text-amber-900" : "text-emerald-800"}`}>{metric.value}</p>
              <p className="mt-1 text-[11px] font-bold text-slate-600">{metric.label}</p>
            </div>
          )}
          <Link to={primary.to} className="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl bg-slate-900 px-4 py-2.5 text-sm font-bold text-white shadow-sm transition hover:-translate-y-0.5 hover:bg-slate-800">
            <PrimaryIcon aria-hidden size={16} /> {primary.label}
          </Link>
          <Link to={secondary.to} className="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-bold text-slate-700 transition hover:border-teal-300 hover:text-teal-800">
            <SecondaryIcon aria-hidden size={16} /> {secondary.label}
          </Link>
          {!isManager && (
            <Link to="/student-leaves" className="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-bold text-slate-700 transition hover:border-teal-300 hover:text-teal-800">
              <DoorOpen aria-hidden size={16} /> استئذان {studentLabel(schoolType)}
            </Link>
          )}
        </div>
      </div>
    </section>
  );
}

function TodayCard({ data: today }: { data: TodayOperations }) {
  const openOverdue = actionableOverdue(today.summary);
  const state = today.operational_state ?? (
    !today.has_active_period
      ? "IDLE"
      : openOverdue > 0
        ? "ACTION_REQUIRED"
        : today.submission_completion_pct === 100
          ? "ON_TRACK"
          : "IN_PROGRESS"
  );
  const presentation = {
    ACTION_REQUIRED: { label: "يلزم إجراء", icon: ShieldAlert, shell: "border-red-200 bg-gradient-to-l from-red-50 to-white", iconClass: "bg-red-100 text-red-700", badge: "bg-red-100 text-red-800 ring-red-200" },
    ON_TRACK: { label: "التشغيل مكتمل", icon: CheckCircle2, shell: "border-emerald-200 bg-gradient-to-l from-emerald-50 to-white", iconClass: "bg-emerald-100 text-emerald-700", badge: "bg-emerald-100 text-emerald-800 ring-emerald-200" },
    IN_PROGRESS: { label: "تشغيل مباشر", icon: Activity, shell: "border-blue-200 bg-gradient-to-l from-blue-50 to-white", iconClass: "bg-blue-100 text-blue-700", badge: "bg-blue-100 text-blue-800 ring-blue-200" },
    IDLE: { label: "لا توجد حصة", icon: Clock3, shell: "border-slate-200 bg-white", iconClass: "bg-slate-100 text-slate-600", badge: "bg-slate-100 text-slate-700 ring-slate-200" },
  }[state];
  const StateIcon = presentation.icon;
  const summary = today.summary;

  return (
    <section
      className={`overflow-hidden rounded-3xl border p-5 shadow-sm sm:p-6 ${presentation.shell}`}
      data-testid="today-card"
      data-state={state}
      id="live-operations"
    >
      <div className="flex flex-col justify-between gap-5 lg:flex-row lg:items-center">
        <div className="flex min-w-0 items-start gap-4">
          <span className={`grid size-12 shrink-0 place-items-center rounded-2xl ${presentation.iconClass}`}><StateIcon aria-hidden size={24} /></span>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-lg font-black text-slate-900">التشغيل المباشر</h2>
              <span className={`rounded-full px-2.5 py-1 text-[11px] font-bold ring-1 ${presentation.badge}`}>{presentation.label}</span>
            </div>
            <p className="mt-2 text-sm font-bold leading-6 text-slate-800">
              {today.headline ?? (!today.has_active_period ? "لا توجد حصة جارية الآن." : `${today.period?.name ?? "الحصة الحالية"} قيد التشغيل.`)}
            </p>
            <p className="mt-1 flex items-center gap-1.5 text-xs text-slate-500"><Clock3 aria-hidden size={13} />{today.date} · <span dir="ltr">{formatSchoolTime(today.school_time)}</span></p>
          </div>
        </div>
        <Link to="/attendance/monitoring" className="inline-flex min-h-10 shrink-0 items-center justify-center gap-2 rounded-xl bg-slate-900 px-4 py-2 text-sm font-bold text-white shadow-sm hover:bg-slate-800">
          عرض تفاصيل الفصول <ArrowLeft aria-hidden size={15} />
        </Link>
      </div>
      {!today.has_active_period ? (
        <p className="mt-5 rounded-2xl border border-slate-200 bg-white/70 p-4 text-sm text-slate-600" data-testid="no-active-period">لا توجد حصة جارية الآن. ستتحول البطاقة تلقائيًا عند بداية الحصة التالية.</p>
      ) : summary && (
        <div className="mt-5" data-testid="monitoring-summary-card">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <p className="text-sm font-bold text-slate-800" data-testid="active-period">{today.period?.name} <span dir="ltr" className="font-medium text-slate-500">{today.period?.start_time}–{today.period?.end_time}</span></p>
            <p className="text-xs font-bold text-slate-600" data-testid="submission-pct">نسبة الاعتماد: {today.submission_completion_pct ?? 0}%</p>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-slate-200"><div className={`h-full rounded-full transition-all duration-500 ${openOverdue > 0 ? "bg-red-500" : "bg-emerald-500"}`} style={{ width: `${Math.min(100, today.submission_completion_pct ?? 0)}%` }} /></div>
          <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4" data-testid="monitoring-summary-line">
            <p className="sr-only">{summary.total} فصلًا: {summary.submitted} مكتمل، {summary.in_progress} قيد التحضير، {summary.not_started} لم يبدأ، {openOverdue} يحتاج متابعة الآن.</p>
            <LiveMetric label="إجمالي الفصول" value={summary.total} tone="slate" />
            <LiveMetric label="تم الاعتماد" value={summary.submitted} tone="green" />
            <LiveMetric label="قيد التحضير" value={summary.in_progress} tone="blue" />
            <LiveMetric label="يحتاج متابعة الآن" value={openOverdue} tone={openOverdue > 0 ? "red" : "slate"} testId="overdue-total" />
          </div>
          {(summary.overdue_submitted ?? 0) > 0 && <p className="mt-3 text-xs font-medium text-amber-800">اعتمد متأخرًا: {summary.overdue_submitted} فصل — معلومة متابعة تاريخية وليست مهمة مفتوحة.</p>}
        </div>
      )}
    </section>
  );
}

function SchoolTodayStatusCard({ data: today, schoolType, showPreparation }: { data: TodayOperations; schoolType: SchoolType; showPreparation: boolean }) {
  const daily = today.daily_attendance;
  const live = today.live_attendance?.status === "AVAILABLE" ? today.live_attendance : undefined;
  const summary = today.summary;
  const openOverdue = actionableOverdue(summary);
  const periodLabel = today.period?.name ?? "لا توجد حصة جارية";
  const studentWord = studentLabel(schoolType);

  return (
    <section className="overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-sm" data-testid="school-today-status-card" aria-live="polite">
      <div className="flex flex-col justify-between gap-4 border-b border-slate-100 bg-gradient-to-l from-blue-50 via-white to-white p-5 sm:flex-row sm:items-start sm:p-6">
        <div className="flex items-start gap-3">
          <span className="grid size-11 shrink-0 place-items-center rounded-2xl bg-blue-100 text-blue-800"><UsersRound aria-hidden size={21} /></span>
          <div>
            <h2 className="text-lg font-black text-slate-900">حالة المدرسة حتى الآن</h2>
            <p className="mt-1 text-sm leading-6 text-slate-600">الحضور تراكمي لليوم، والغياب المتتابع لا يشمل غياب حصة واحدة فقط.</p>
          </div>
        </div>
        <Link to="/attendance/monitoring" className="inline-flex min-h-10 shrink-0 items-center justify-center gap-2 rounded-xl bg-slate-900 px-4 py-2 text-sm font-bold text-white shadow-sm hover:bg-slate-800">
          عرض تفاصيل الفصول <ArrowLeft aria-hidden size={15} />
        </Link>
      </div>

      <div className="grid gap-3 p-4 sm:grid-cols-3 sm:p-5" data-testid="vice-day-summary">
        <SchoolDayMetric testId="school-daily-present" label="حضر اليوم" value={daily?.present_students ?? 0} detail={`ثبت حضور ${studentWord} في حصة واحدة على الأقل`} tone="green" />
        <SchoolDayMetric testId="school-continuous-absent" label="غائب حتى الآن" value={live?.daily_absent_students ?? "—"} detail={live ? "غاب في كل الحصص المكتملة حتى الحالية" : "يظهر أثناء الحصة الجارية بعد اكتمال التحضير"} tone="red" />
        <SchoolDayMetric testId="school-current-leave" label="مستأذن الآن" value={live?.leave_students ?? "—"} detail="قد يكون ضمن الحضور اليومي إذا حضر قبل خروجه" tone="blue" />
      </div>

      <div className="space-y-2 border-t border-slate-100 bg-slate-50/70 px-4 py-4 text-xs leading-5 text-slate-700 sm:px-5">
        {live ? (
          <p data-testid="school-current-period-line">
            <strong>{periodLabel} الآن:</strong> {live.present_students} حاضرًا · {live.absent_students} غائبًا عن الحصة · {live.leave_students} مستأذنًا.
            {live.pending_students > 0 ? ` التغطية ${live.covered_students} من ${live.total_students}؛ بانتظار تحضير ${live.pending_sections} فصل.` : ""}
          </p>
        ) : (
          <p data-testid="school-no-active-period"><strong>لا توجد حصة جارية الآن.</strong> يبقى «حضر اليوم» محفوظًا ولا يُصفّر بانتقال الوقت.</p>
        )}
        {showPreparation && summary && (
          <div data-testid="monitoring-summary-card">
            <p data-testid="monitoring-summary-line"><strong>اعتماد التحضير:</strong> {summary.submitted} من {summary.total} فصلًا · {summary.in_progress} قيد التحضير · {openOverdue} يحتاج متابعة الآن.</p>
          </div>
        )}
        {live && (
          <p className={live.daily_pending_sections > 0 ? "text-amber-800" : "text-emerald-800"} data-testid="school-coverage-line">
            {live.daily_pending_sections > 0
              ? `رقم الغياب المتتابع مكتمل لـ ${live.daily_covered_students} من ${live.total_students} ${studentCountLabel(schoolType)}؛ بانتظار اكتمال تحضير ${live.daily_pending_sections} فصل.`
              : `تغطية الغياب المتتابع مكتملة لجميع ${live.total_students} ${studentCountLabel(schoolType)} من أول حصة حتى الحالية.`}
          </p>
        )}
      </div>
    </section>
  );
}

function SchoolDayMetric({ testId, label, value, detail, tone }: { testId: string; label: string; value: number | string; detail: string; tone: "green" | "red" | "blue" }) {
  const tones = {
    green: "border-emerald-200 bg-emerald-50 text-emerald-900",
    red: "border-red-200 bg-red-50 text-red-900",
    blue: "border-blue-200 bg-blue-50 text-blue-900",
  };
  return (
    <div className={`rounded-2xl border p-4 ${tones[tone]}`} data-testid={testId}>
      <p className="text-3xl font-black tabular-nums">{value}</p>
      <p className="mt-1 text-sm font-black">{label}</p>
      <p className="mt-2 border-t border-current/10 pt-2 text-[11px] font-bold leading-5 opacity-75">{detail}</p>
    </div>
  );
}

function actionableOverdue(summary: TodayOperations["summary"] | undefined): number {
  if (!summary) return 0;
  if (summary.overdue_not_started !== undefined || summary.overdue_in_progress !== undefined) {
    return (summary.overdue_not_started ?? 0) + (summary.overdue_in_progress ?? 0);
  }
  return summary.overdue_total;
}

function formatSchoolTime(value: string): string {
  const time = value.includes("T") ? value.split("T")[1] : value;
  return time?.slice(0, 5) ?? value;
}

function LiveMetric({ label, value, tone, testId }: { label: string; value: number; tone: "slate" | "green" | "blue" | "red"; testId?: string }) {
  const tones = { slate: "border-slate-200 bg-white/70 text-slate-800", green: "border-emerald-200 bg-emerald-50 text-emerald-800", blue: "border-blue-200 bg-blue-50 text-blue-800", red: "border-red-200 bg-red-50 text-red-800" };
  return <div className={`rounded-2xl border p-3 ${tones[tone]}`} data-testid={testId}><p className="text-2xl font-black">{value}</p><p className="mt-1 text-[11px] font-bold opacity-80">{label}</p></div>;
}

function Kpi({
  testId,
  label,
  value,
  comparison,
}: {
  testId: string;
  label: string;
  value: number;
  comparison?: Comparison;
}) {
  return (
    <div
      className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm transition hover:-translate-y-0.5 hover:shadow-md"
      data-testid={testId}
    >
      <p className="text-2xl font-black text-slate-900 sm:text-3xl">{value}</p>
      <p className="mt-1 text-xs font-bold leading-5 text-slate-500">{label}</p>
      {comparison && <ComparisonNote comparison={comparison} />}
    </div>
  );
}

/** المقارنة كما حسبها الخادم — «جديد» بدل نسبة لا نهائية عند أساس صفري. */
function ComparisonNote({ comparison }: { comparison: Comparison }) {
  if (comparison.change_pct === null) {
    return (
      <p className="mt-1 text-[11px] text-slate-500" data-testid="comparison-new">
        {comparison.is_new ? "جديد — لا نظير في الفترة السابقة" : "لا تغيّر"}
      </p>
    );
  }
  const up = comparison.delta > 0;
  return (
    <p
      className={`mt-1 text-[11px] ${up ? "text-red-700" : "text-green-700"}`}
      data-testid="comparison-pct"
    >
      {up ? "▲" : "▼"} {Math.abs(comparison.change_pct)}% مقارنة بالفترة السابقة (
      {comparison.previous})
    </p>
  );
}

function FollowUpCard({
  title,
  testId,
  children,
}: {
  title: string;
  testId: string;
  children: React.ReactNode;
}) {
  return (
    <section
      className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"
      data-testid={testId}
    >
      <h3 className="mb-3 font-black text-slate-900">{title}</h3>
      {children}
    </section>
  );
}

const ATTENTION_GROUPS: { key: string; label: string; icon: LucideIcon }[] = [
  { key: "attendance_overdue", label: "تحضير متأخر", icon: Activity },
  { key: "warning_due", label: "إنذارات مستحقة", icon: BellRing },
  { key: "excuse_pending", label: "أعذار معلقة", icon: FileCheck2 },
  { key: "referral_unassigned", label: "إحالات بلا مرشد", icon: Send },
  { key: "counseling", label: "متابعة إرشادية", icon: UsersRound },
];

function AttentionSection({
  query,
  schoolType,
  compact = false,
}: {
  query: ReturnType<typeof useQuery<import("@/features/dashboard/api").AttentionResponse>>;
  schoolType: SchoolType;
  compact?: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const groups = compact && query.data
    ? ATTENTION_GROUPS.filter(({ key }) => (query.data.counts[key] ?? 0) > 0)
    : ATTENTION_GROUPS;
  const compactItems = query.data ? representativeAttentionItems(query.data.items, 5) : [];
  const visibleItems = compact && !expanded ? compactItems : (query.data?.items ?? []);
  const hasHiddenItems = compact && query.data ? query.data.items.length > compactItems.length : false;

  return (
    <section
      className="overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-sm"
      data-testid="attention-section"
    >
      <div className={`border-b p-5 sm:p-6 ${query.data && query.data.total > 0 ? "border-red-100 bg-gradient-to-l from-red-50 to-white" : "border-emerald-100 bg-gradient-to-l from-emerald-50 to-white"}`}>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex items-start gap-3">
            <span className={`grid size-11 shrink-0 place-items-center rounded-2xl ${query.data && query.data.total > 0 ? "bg-red-100 text-red-700" : "bg-emerald-100 text-emerald-700"}`}>
              {query.data && query.data.total > 0 ? <ShieldAlert aria-hidden size={22} /> : <CheckCircle2 aria-hidden size={22} />}
            </span>
            <div>
              <h2 className="text-lg font-black text-slate-900">{compact ? "ما يحتاج تدخلك" : "تنبيهات وإجراءات مطلوبة"}</h2>
              <p className="mt-1 text-xs leading-5 text-slate-500">
                {compact
                  ? `أعلى الحالات أولوية الآن في قائمة قصيرة؛ ليست تصنيفًا ${schoolType === "GIRLS" ? "للطالبات" : "للطلاب"}.`
                  : <>قائمة عمل إداري لحظية — ليست تصنيفًا {schoolType === "GIRLS" ? "للطالبات" : "للطلاب"} ولا تقييمًا لأحد، ولا يترتب عليها أي إجراء تلقائي.</>}
              </p>
            </div>
          </div>
          {query.isSuccess && (
            <span className={`rounded-full px-3 py-1.5 text-xs font-black ring-1 ${query.data.total > 0 ? "bg-red-100 text-red-800 ring-red-200" : "bg-emerald-100 text-emerald-800 ring-emerald-200"}`}>
              {query.data.total > 0 ? `${query.data.total} تحتاج متابعة` : "الوضع مستقر"}
            </span>
          )}
        </div>
      </div>
      {query.isPending && (
        <div className="p-4">
          <Spinner />
        </div>
      )}
      {query.isError && (
        <div className="p-4">
          <ErrorState error={query.error} />
        </div>
      )}
      {query.isSuccess && (
        <>
          <div className={`grid grid-cols-2 gap-2 p-4 sm:p-5 ${compact ? "sm:grid-cols-3 lg:grid-cols-4" : "sm:grid-cols-3 lg:grid-cols-5"}`}>
            {groups.map(({ key, label, icon: Icon }) => {
              const count = query.data.counts[key] ?? 0;
              return (
                <div key={key} className={`rounded-2xl border p-3 ${count > 0 ? "border-amber-200 bg-amber-50" : "border-slate-200 bg-slate-50"}`} data-testid={`attention-count-${key}`}>
                  <div className="flex items-center justify-between gap-2"><Icon aria-hidden size={16} className={count > 0 ? "text-amber-700" : "text-slate-400"} /><strong className={`text-lg font-black ${count > 0 ? "text-amber-900" : "text-slate-500"}`}>{count}</strong></div>
                  <p className="mt-2 text-[11px] font-bold text-slate-600">{label}</p>
                </div>
              );
            })}
          </div>
          {query.data.items.length === 0 ? (
            <div className="px-5 pb-6 text-center" data-testid="attention-empty"><p className="text-sm font-bold text-emerald-800">لا يوجد ما يحتاج متابعة الآن.</p><p className="mt-1 text-xs text-slate-500">ستظهر هنا أي حالة تتطلب تدخلًا إداريًا.</p></div>
          ) : (
            <ul className="space-y-2 border-t border-slate-100 bg-slate-50/60 p-4 sm:p-5" data-testid="attention-items">
              {visibleItems.map((item) => (
                <AttentionRow key={`${item.kind}-${item.entity_id}`} item={item} />
              ))}
              {hasHiddenItems && (
                <li className="pt-2 text-center">
                  <button type="button" className="rounded-xl border border-slate-300 bg-white px-4 py-2 text-xs font-bold text-slate-700 hover:border-teal-300 hover:text-teal-800" onClick={() => setExpanded((value) => !value)}>
                    {expanded ? "عرض القائمة المختصرة" : `عرض بقية المهام (${query.data.items.length - compactItems.length})`}
                  </button>
                </li>
              )}
            </ul>
          )}
        </>
      )}
    </section>
  );
}

/** يضمن أن الملخص لا تمتلئ أسطره بنوع واحد بينما تختفي أنواع أخرى مهمة. */
function representativeAttentionItems(items: AttentionItem[], limit: number): AttentionItem[] {
  const selected: AttentionItem[] = [];
  const representedKinds = new Set<string>();

  for (const item of items) {
    if (!representedKinds.has(item.kind)) {
      selected.push(item);
      representedKinds.add(item.kind);
    }
    if (selected.length === limit) return selected;
  }
  for (const item of items) {
    if (!selected.includes(item)) selected.push(item);
    if (selected.length === limit) break;
  }
  return selected;
}

function AttentionRow({ item }: { item: AttentionItem }) {
  const presentation: Record<string, { icon: LucideIcon; action: string }> = {
    ATTENDANCE_OVERDUE: { icon: Activity, action: "متابعة التحضير" },
    WARNING_DUE: { icon: BellRing, action: "مراجعة الإنذار" },
    EXCUSE_PENDING: { icon: FileCheck2, action: "مراجعة العذر" },
    REFERRAL_UNASSIGNED: { icon: Send, action: "تعيين مرشد" },
  };
  const meta = presentation[item.kind] ?? { icon: AlertTriangle, action: "فتح المتابعة" };
  const Icon = meta.icon;
  const high = item.priority === "HIGH";
  return (
    <li
      className={`flex flex-col justify-between gap-3 rounded-2xl border p-4 sm:flex-row sm:items-center ${high ? "border-red-200 bg-white shadow-sm shadow-red-100/40" : "border-amber-200 bg-white"}`}
      data-testid={`attention-item-${item.kind}-${item.entity_id}`}
    >
      <div className="flex min-w-0 items-start gap-3">
        <span className={`grid size-9 shrink-0 place-items-center rounded-xl ${high ? "bg-red-100 text-red-700" : "bg-amber-100 text-amber-700"}`}><Icon aria-hidden size={17} /></span>
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2"><span className={`rounded-full px-2 py-0.5 text-[10px] font-black ${high ? "bg-red-100 text-red-800" : "bg-amber-100 text-amber-800"}`} aria-label={high ? "أولوية عالية" : "أولوية عادية"}>{high ? "أولوية عالية" : "متابعة"}</span></div>
          <p className="mt-1.5 text-sm font-bold leading-6 text-slate-800">{item.display_text}</p>
        </div>
      </div>
      <Link to={item.target_url} className={`inline-flex min-h-9 shrink-0 items-center justify-center gap-1.5 rounded-xl px-3 py-2 text-xs font-bold ${high ? "bg-red-600 text-white hover:bg-red-700" : "bg-amber-100 text-amber-900 hover:bg-amber-200"}`}>
        {meta.action} <ArrowLeft aria-hidden size={14} />
      </Link>
    </li>
  );
}

function SectionsTable({ data, schoolType }: { data: SectionsResponse; schoolType: SchoolType }) {
  if (data.sections.length === 0) {
    return (
      <p className="p-6 text-sm text-slate-600" data-testid="sections-empty">
        لا توجد بيانات فصول في هذه الفترة.
      </p>
    );
  }
  return (
    <div>
      <table className="block w-full text-sm md:table" data-testid="sections-table">
        <thead className="hidden bg-slate-50 text-slate-600 md:table-header-group">
          <tr>
            <th className="p-2 text-start">الفصل</th>
            <th className="p-2 text-start">{schoolType === "GIRLS" ? "طالبات" : "طلاب"}</th>
            <th className="p-2 text-start">غياب كامل بدون عذر</th>
            <th className="p-2 text-start">غياب كامل (الكل)</th>
            <th className="p-2 text-start">غياب جزئي</th>
            <th className="p-2 text-start">تأخر صباحي</th>
          </tr>
        </thead>
        <tbody className="grid gap-3 p-3 md:table-row-group md:p-0">
          {data.sections.map((row) => (
            <tr
              key={row.section_id}
              className="grid grid-cols-2 gap-3 rounded-2xl border border-slate-200 p-4 md:table-row md:border-x-0 md:border-b-0 md:p-0"
              data-testid={`section-row-${row.section_id}`}
            >
              <td className="col-span-2 p-0 font-bold text-slate-800 md:table-cell md:p-2 md:font-normal">
                <span className="mb-1 block text-xs font-bold text-slate-500 md:hidden">الفصل</span>
                {row.grade_name} / {row.section_name}
              </td>
              <td className="p-0 text-slate-600 md:table-cell md:p-2"><span className="mb-1 block text-xs font-bold text-slate-500 md:hidden">{schoolType === "GIRLS" ? "طالبات" : "طلاب"}</span>{row.students}</td>
              <td className="p-0 font-medium text-slate-800 md:table-cell md:p-2">
                <span className="mb-1 block text-xs font-bold text-slate-500 md:hidden">غياب بلا عذر</span>
                {row.unexcused_full_absence_days}
              </td>
              <td className="p-0 text-slate-600 md:table-cell md:p-2"><span className="mb-1 block text-xs font-bold text-slate-500 md:hidden">الغياب الكامل</span>{row.full_absence_days}</td>
              <td className="p-0 text-slate-600 md:table-cell md:p-2"><span className="mb-1 block text-xs font-bold text-slate-500 md:hidden">الغياب الجزئي</span>{row.partial_absence_days}</td>
              <td className="p-0 text-slate-600 md:table-cell md:p-2"><span className="mb-1 block text-xs font-bold text-slate-500 md:hidden">التأخر الصباحي</span>{row.morning_late_occurrences}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="p-3 text-xs text-slate-500">
        الترتيب وصفي بأعداد أيام-{studentLabel(schoolType)} داخل الفترة — لا يقيس أداء معلم ولا يصنف فصلًا
        «الأسوأ»، وأعداد {studentPluralLabel(schoolType)} المختلفة بين الفصول تجعل المقارنة المباشرة غير عادلة.
      </p>
    </div>
  );
}
