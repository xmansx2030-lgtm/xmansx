import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { ErrorState } from "@/components/ErrorState";
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
} from "@/features/dashboard/api";
import {
  getAttention,
  getOverview,
  getSections,
  getTrend,
} from "@/features/dashboard/api";
import { TrendChart } from "@/features/dashboard/TrendChart";

/** «يحتاج متابعة» طابور عمل لحظي — يُحدَّث تلقائيًا، وبقية اللوحة عند التنقل فقط. */
const ATTENTION_POLL_MS = 60_000;

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

  const sectionsListQuery = useQuery({
    queryKey: schoolScopedKey(activeSchoolId, "attendance", "sections"),
    queryFn: ({ signal }) => getAttendanceSections(signal),
    enabled,
  });
  const overviewQuery = useQuery({
    queryKey: schoolScopedKey(activeSchoolId, "dashboard", "overview", ...filterKey),
    queryFn: ({ signal }) => getOverview(filters, signal),
    enabled,
  });
  const trendQuery = useQuery({
    queryKey: schoolScopedKey(activeSchoolId, "dashboard", "trend", ...filterKey),
    queryFn: ({ signal }) => getTrend(filters, signal),
    enabled,
  });
  const sectionsQuery = useQuery({
    queryKey: schoolScopedKey(activeSchoolId, "dashboard", "sections", ...filterKey),
    queryFn: ({ signal }) => getSections(filters, signal),
    enabled,
  });
  const attentionQuery = useQuery({
    queryKey: schoolScopedKey(activeSchoolId, "dashboard", "attention"),
    queryFn: ({ signal }) => getAttention(signal),
    enabled,
    refetchInterval: ATTENTION_POLL_MS,
  });

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

  return (
    <div className="space-y-4" data-testid="dashboard-page">
      <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-lg font-bold text-slate-800">لوحة إدارة المدرسة</h2>
          {overviewQuery.isSuccess && (
            <p className="text-xs text-slate-500" data-testid="dashboard-context">
              {overviewQuery.data.context.academic_year?.name ?? "لا يوجد عام دراسي نشط"}
              {overviewQuery.data.context.semester
                ? ` · ${overviewQuery.data.context.semester.name}`
                : ""}{" "}
              · بتوقيت {overviewQuery.data.context.timezone} · اليوم{" "}
              {overviewQuery.data.context.today}
            </p>
          )}
        </div>

        <div className="mt-3 flex flex-wrap items-end gap-2">
          <label className="text-sm text-slate-600">
            الفترة{" "}
            <select
              value={preset}
              onChange={(e) => setPreset(e.target.value as DashboardPreset)}
              className="rounded-lg border border-slate-300 px-2 py-1.5"
              data-testid="dashboard-preset"
            >
              {PRESETS.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          {preset === "CUSTOM" && (
            <>
              <label className="text-sm text-slate-600">
                من{" "}
                <input
                  type="date"
                  value={fromDate}
                  onChange={(e) => setFromDate(e.target.value)}
                  className="rounded-lg border border-slate-300 px-2 py-1.5"
                  data-testid="dashboard-from"
                />
              </label>
              <label className="text-sm text-slate-600">
                إلى{" "}
                <input
                  type="date"
                  value={toDate}
                  onChange={(e) => setToDate(e.target.value)}
                  className="rounded-lg border border-slate-300 px-2 py-1.5"
                  data-testid="dashboard-to"
                />
              </label>
            </>
          )}
          <label className="text-sm text-slate-600">
            الصف{" "}
            <select
              value={gradeId}
              onChange={(e) => {
                setGradeId(e.target.value === "" ? "" : Number(e.target.value));
                setSectionId(""); // فصل من صف آخر يرفضه الخادم — نمنع الحالة أصلًا
              }}
              className="rounded-lg border border-slate-300 px-2 py-1.5"
              data-testid="dashboard-grade"
            >
              <option value="">كل الصفوف</option>
              {grades.map(([id, name]) => (
                <option key={id} value={id}>
                  {name}
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm text-slate-600">
            الفصل{" "}
            <select
              value={sectionId}
              onChange={(e) => setSectionId(e.target.value === "" ? "" : Number(e.target.value))}
              className="rounded-lg border border-slate-300 px-2 py-1.5"
              data-testid="dashboard-section"
            >
              <option value="">كل الفصول</option>
              {sectionOptions.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.grade_name} / {s.name}
                </option>
              ))}
            </select>
          </label>
        </div>

        {overviewQuery.isSuccess && (
          <p className="mt-2 text-xs text-slate-500" data-testid="dashboard-range">
            الفترة {overviewQuery.data.context.range.from_date} إلى{" "}
            {overviewQuery.data.context.range.to_date} ({overviewQuery.data.context.range.days}{" "}
            يومًا) · تُقارن بـ {overviewQuery.data.context.previous_range.from_date} إلى{" "}
            {overviewQuery.data.context.previous_range.to_date} (
            {overviewQuery.data.context.previous_range.days} يومًا)
          </p>
        )}
      </section>

      {overviewQuery.isPending && <Spinner label="جارٍ تحميل اللوحة..." />}
      {overviewQuery.isError && (
        <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <ErrorState error={overviewQuery.error} />
        </section>
      )}

      {overviewQuery.isSuccess && <OverviewBody data={overviewQuery.data} />}

      <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <h3 className="mb-3 font-bold text-slate-800">اتجاه الغياب</h3>
        {trendQuery.isPending && <Spinner />}
        {trendQuery.isError && <ErrorState error={trendQuery.error} />}
        {trendQuery.isSuccess && (
          <>
            {trendQuery.data.granularity === "WEEK" && (
              <p className="mb-2 text-xs text-amber-700" data-testid="trend-aggregated">
                الفترة طويلة — النقاط مجمّعة أسبوعيًا.
              </p>
            )}
            <TrendChart
              points={trendQuery.data.points}
              granularity={trendQuery.data.granularity}
            />
          </>
        )}
      </section>

      <AttentionSection
        query={attentionQuery}
      />

      <section className="rounded-xl border border-slate-200 bg-white shadow-sm">
        <h3 className="border-b border-slate-100 p-4 font-bold text-slate-800">
          الفصول — مرتبة بالأعلى غيابًا بدون عذر
        </h3>
        {sectionsQuery.isPending && (
          <div className="p-4">
            <Spinner />
          </div>
        )}
        {sectionsQuery.isError && (
          <div className="p-4">
            <ErrorState error={sectionsQuery.error} />
          </div>
        )}
        {sectionsQuery.isSuccess && <SectionsTable data={sectionsQuery.data} />}
      </section>
    </div>
  );
}

function OverviewBody({ data }: { data: OverviewResponse }) {
  const a = data.attendance;
  return (
    <>
      {a.completeness.is_significant && (
        <p
          className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900"
          data-testid="completeness-warning"
        >
          ⚠️ {a.completeness.incomplete_pct}% من أيام-الطلاب في هذه الفترة لم يكتمل تحضيرها،
          فالأرقام أدناه أقل من الواقع بالضرورة.
        </p>
      )}

      <TodayCard data={data} />

      <section className="grid grid-cols-2 gap-2 sm:grid-cols-4" data-testid="dashboard-kpis">
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
        <Kpi
          testId="kpi-period-late"
          label="تأخر داخل الحصص (مرات)"
          value={a.period_late_occurrences}
        />
        <Kpi testId="kpi-absent-periods" label="حصص غياب" value={a.absent_periods} />
        <Kpi
          testId="kpi-undetermined"
          label="أيام غير مكتملة البيانات"
          value={a.undetermined_days}
        />
        <Kpi testId="kpi-student-days" label="أيام-طالب مشمولة" value={a.student_days} />
      </section>
      <p className="text-xs text-slate-500" data-testid="unit-note">
        الوحدة: أيام-طالب (لا عدد طلاب متفردين) · {a.distinct_students} طالبًا ضمن الفترة ·
        التأخر الصباحي والتأخر داخل الحصص مؤشران منفصلان لا يُجمعان.
      </p>

      <div className="grid gap-2 md:grid-cols-2">
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
            طالبًا
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
              بانتظار رد معلم: {data.counseling.waiting_teacher_responses} · أنشطة متأخرة:{" "}
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

function TodayCard({ data }: { data: OverviewResponse }) {
  const today = data.today_operations;
  return (
    <section
      className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"
      data-testid="today-card"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="font-bold text-slate-800">تشغيل اليوم</h3>
        <span className="text-xs text-slate-500">
          {today.date} · {today.school_time}
        </span>
      </div>
      {!today.has_active_period ? (
        <p className="mt-2 text-sm text-slate-600" data-testid="no-active-period">
          لا توجد حصة جارية الآن.
        </p>
      ) : (
        <div className="mt-2 flex flex-wrap items-center gap-4 text-sm">
          <span className="font-medium text-slate-800" data-testid="active-period">
            {today.period?.name} ({today.period?.start_time}–{today.period?.end_time})
          </span>
          <span className="text-slate-600" data-testid="submission-pct">
            نسبة الاعتماد: {today.submission_completion_pct ?? 0}%
          </span>
          {today.summary && (
            <span
              className={today.summary.overdue_total > 0 ? "text-red-700" : "text-slate-600"}
              data-testid="overdue-total"
            >
              متأخر عن المهلة: {today.summary.overdue_total} من {today.summary.total}
            </span>
          )}
          <Link to="/attendance/monitoring" className="text-xs text-blue-700">
            متابعة التحضير ←
          </Link>
        </div>
      )}
    </section>
  );
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
      className="rounded-xl border border-slate-200 bg-white p-3 text-center shadow-sm"
      data-testid={testId}
    >
      <p className="text-2xl font-bold text-slate-800">{value}</p>
      <p className="text-xs text-slate-500">{label}</p>
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
      className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"
      data-testid={testId}
    >
      <h3 className="mb-2 font-bold text-slate-800">{title}</h3>
      {children}
    </section>
  );
}

const ATTENTION_GROUPS: [string, string][] = [
  ["attendance_overdue", "تحضير متأخر"],
  ["warning_due", "إنذارات مستحقة"],
  ["excuse_pending", "أعذار بانتظار البت"],
  ["referral_unassigned", "إحالات بلا مرشد"],
  ["counseling", "الإرشاد"],
];

function AttentionSection({
  query,
}: {
  query: ReturnType<typeof useQuery<import("@/features/dashboard/api").AttentionResponse>>;
}) {
  return (
    <section
      className="rounded-xl border border-slate-200 bg-white shadow-sm"
      data-testid="attention-section"
    >
      <div className="border-b border-slate-100 p-4">
        <h3 className="font-bold text-slate-800">يحتاج متابعة</h3>
        <p className="mt-1 text-xs text-slate-500">
          قائمة عمل إداري لحظية — ليست تصنيفًا للطلاب ولا تقييمًا لأحد، ولا يترتب عليها أي
          إجراء تلقائي.
        </p>
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
          <div className="flex flex-wrap gap-2 p-4 pb-0 text-xs">
            {ATTENTION_GROUPS.map(([key, label]) => (
              <span
                key={key}
                className="rounded-full bg-slate-100 px-2 py-1 text-slate-700"
                data-testid={`attention-count-${key}`}
              >
                {label}: {query.data.counts[key] ?? 0}
              </span>
            ))}
          </div>
          {query.data.items.length === 0 ? (
            <p className="p-4 text-sm text-slate-600" data-testid="attention-empty">
              لا يوجد ما يحتاج متابعة الآن.
            </p>
          ) : (
            <ul className="mt-2 divide-y divide-slate-100" data-testid="attention-items">
              {query.data.items.map((item) => (
                <AttentionRow key={`${item.kind}-${item.entity_id}`} item={item} />
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  );
}

function AttentionRow({ item }: { item: AttentionItem }) {
  return (
    <li
      className="flex flex-wrap items-center justify-between gap-2 p-3"
      data-testid={`attention-item-${item.kind}-${item.entity_id}`}
    >
      <div className="flex items-center gap-2">
        <span
          className={`inline-block size-2 rounded-full ${
            item.priority === "HIGH" ? "bg-red-500" : "bg-slate-300"
          }`}
          aria-label={item.priority === "HIGH" ? "أولوية عالية" : "أولوية عادية"}
        />
        <span className="text-sm text-slate-800">{item.display_text}</span>
      </div>
      <Link to={item.target_url} className="text-xs text-blue-700">
        فتح ←
      </Link>
    </li>
  );
}

function SectionsTable({ data }: { data: SectionsResponse }) {
  if (data.sections.length === 0) {
    return (
      <p className="p-6 text-sm text-slate-600" data-testid="sections-empty">
        لا توجد بيانات فصول في هذه الفترة.
      </p>
    );
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm" data-testid="sections-table">
        <thead className="bg-slate-50 text-slate-600">
          <tr>
            <th className="p-2 text-start">الفصل</th>
            <th className="p-2 text-start">طلاب</th>
            <th className="p-2 text-start">غياب كامل بدون عذر</th>
            <th className="p-2 text-start">غياب كامل (الكل)</th>
            <th className="p-2 text-start">غياب جزئي</th>
            <th className="p-2 text-start">تأخر صباحي</th>
            <th className="p-2 text-start">تأخر حصص</th>
          </tr>
        </thead>
        <tbody>
          {data.sections.map((row) => (
            <tr
              key={row.section_id}
              className="border-t border-slate-100"
              data-testid={`section-row-${row.section_id}`}
            >
              <td className="p-2 text-slate-800">
                {row.grade_name} / {row.section_name}
              </td>
              <td className="p-2 text-slate-600">{row.students}</td>
              <td className="p-2 font-medium text-slate-800">
                {row.unexcused_full_absence_days}
              </td>
              <td className="p-2 text-slate-600">{row.full_absence_days}</td>
              <td className="p-2 text-slate-600">{row.partial_absence_days}</td>
              <td className="p-2 text-slate-600">{row.morning_late_occurrences}</td>
              <td className="p-2 text-slate-600">{row.period_late_occurrences}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="p-3 text-xs text-slate-500">
        الترتيب وصفي بأعداد أيام-طالب داخل الفترة — لا يقيس أداء معلم ولا يصنف فصلًا
        «الأسوأ»، وأعداد الطلاب المختلفة بين الفصول تجعل المقارنة المباشرة غير عادلة.
      </p>
    </div>
  );
}
