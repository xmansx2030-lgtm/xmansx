import { useQuery } from "@tanstack/react-query";
import { BarChart3, CalendarDays } from "lucide-react";
import { useMemo, useState } from "react";

import { Button } from "@/components/Button";
import { ErrorState } from "@/components/ErrorState";
import { PageHeader } from "@/components/PageHeader";
import { Spinner } from "@/components/Spinner";
import type {
  MatchMode,
  MultiPeriodParams,
  MultiPeriodResponse,
} from "@/features/attendance/api";
import {
  getAttendanceSections,
  getDailyAnalytics,
  postMultiPeriodAnalytics,
} from "@/features/attendance/api";
import { schoolScopedKey, useMe } from "@/features/auth/useMe";
import type { SchoolType } from "@/types/auth";
import { studentCountLabel, studentPluralLabel } from "@/utils/roles";

const POLL_MS = 20_000; // اليوم الحالي فقط — التواريخ الماضية لا تتغير

function todayIso(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

const STATUS_BADGE: Record<string, string> = {
  ABSENT: "غائب",
  PRESENT: "حاضر",
};
const FEMININE_STATUS_BADGE: Record<string, string> = {
  ABSENT: "غائبة",
  PRESENT: "حاضرة",
};

type Tab = "period" | "multi" | "daily";

/** صفحة «الغياب والحضور» (م8) — الحالة كلها من الخادم؛ الواجهة اختيار وعرض فقط. */
export function AnalyticsPage() {
  const me = useMe();
  const activeSchoolId = me.data?.active_school?.id ?? 0;
  const schoolType = me.data?.active_school?.school_type ?? "BOYS";
  const [tab, setTab] = useState<Tab>("period");
  const [date, setDate] = useState(todayIso());
  const isToday = date === todayIso();

  // ‏daily يوفر قائمة حصص اليوم (من سياق اليوم التاريخي) لمحددات التبويبات
  const dailyQuery = useQuery({
    queryKey: schoolScopedKey(activeSchoolId, "attendance", "analytics", "daily", date),
    queryFn: ({ signal }) => getDailyAnalytics({ date }, signal),
    enabled: activeSchoolId > 0,
    refetchInterval: isToday ? POLL_MS : false,
  });
  const sectionsQuery = useQuery({
    queryKey: schoolScopedKey(activeSchoolId, "attendance", "sections"),
    queryFn: ({ signal }) => getAttendanceSections(signal),
    enabled: activeSchoolId > 0,
  });

  const dayPeriods = dailyQuery.data?.day_periods ?? [];
  const grades = useMemo(() => {
    const map = new Map<number, string>();
    for (const s of sectionsQuery.data ?? []) {
      if (s.grade_id != null) map.set(s.grade_id, s.grade_name);
    }
    return [...map.entries()];
  }, [sectionsQuery.data]);

  return (
    <div className="space-y-5">
      <PageHeader icon={BarChart3} eyebrow="التحليل التشغيلي" title="الغياب والحضور" description={`حلّل الحضور حسب الحصة أو عبر عدة حصص، ثم انتقل من المؤشر إلى قائمة ${studentPluralLabel(schoolType)} القابلة للإجراء.`} tone="executive" badge={isToday ? "بيانات اليوم المباشرة" : "سجل تاريخي"} actions={<label className="flex items-center gap-2 rounded-xl bg-white/10 px-3 py-2 text-sm font-bold text-white ring-1 ring-white/15"><CalendarDays aria-hidden size={17} /><span className="sr-only">التاريخ</span><input type="date" value={date} onChange={(e) => setDate(e.target.value)} className="border-white/20 bg-white text-slate-950" data-testid="analytics-date" /></label>} />
      <section className="rounded-2xl border border-slate-200 bg-white px-4 pt-2 shadow-sm">
        <div className="mt-3 flex gap-1 border-b border-slate-100" role="tablist">
          {(
            [
              ["period", "حسب الحصة"],
              ["multi", "عدة حصص"],
              ["daily", "ملخص اليوم"],
            ] as const
          ).map(([key, label]) => (
            <button
              key={key}
              type="button"
              role="tab"
              aria-selected={tab === key}
              onClick={() => setTab(key)}
              className={`rounded-t-lg px-4 py-2 text-sm font-medium ${
                tab === key
                  ? "border-b-2 border-blue-600 text-blue-700"
                  : "text-slate-500 hover:text-slate-800"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </section>

      {dailyQuery.isPending && <Spinner label="جارٍ تحميل جدول اليوم..." />}
      {dailyQuery.isError && (
        <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <ErrorState error={dailyQuery.error} />
        </section>
      )}
      {dailyQuery.isSuccess && !dailyQuery.data.is_school_day && tab !== "daily" && (
        <p
          className="rounded-xl border border-slate-200 bg-white p-4 text-slate-600 shadow-sm"
          data-testid="not-school-day"
        >
          لا يوجد جدول دراسي لهذا اليوم.
        </p>
      )}

      {dailyQuery.isSuccess && dailyQuery.data.is_school_day && tab !== "daily" && (
        <PeriodsReport
          key={`${tab}-${date}`}
          mode={tab}
          date={date}
          isToday={isToday}
          activeSchoolId={activeSchoolId}
          dayPeriods={dayPeriods}
          grades={grades}
          schoolType={schoolType}
        />
      )}

      {tab === "daily" && dailyQuery.isSuccess && (
        <DailyTab
          date={date}
          activeSchoolId={activeSchoolId}
          data={dailyQuery.data}
          grades={grades}
          schoolType={schoolType}
        />
      )}
    </div>
  );
}

interface PeriodsReportProps {
  mode: "period" | "multi";
  date: string;
  isToday: boolean;
  activeSchoolId: number;
  dayPeriods: { sequence: number; name: string }[];
  grades: [number, string][];
  schoolType: SchoolType;
}

/** تبويبا «حسب الحصة» و«عدة حصص» — نفس محرك التقرير، يختلف المحدد فقط. */
function PeriodsReport({
  mode,
  date,
  isToday,
  activeSchoolId,
  dayPeriods,
  grades,
  schoolType,
}: PeriodsReportProps) {
  const [selected, setSelected] = useState<number[]>([]);
  const [match, setMatch] = useState<MatchMode>("ALL_ABSENT");
  const [gradeId, setGradeId] = useState<number | "">("");
  const [page, setPage] = useState(1);
  const [params, setParams] = useState<MultiPeriodParams | null>(null);

  const reportQuery = useQuery({
    queryKey: schoolScopedKey(activeSchoolId, "attendance", "analytics", "report", params),
    queryFn: () => postMultiPeriodAnalytics(params as MultiPeriodParams),
    enabled: params !== null,
    refetchInterval: isToday ? POLL_MS : false,
  });

  const toggle = (sequence: number) => {
    setSelected((prev) =>
      mode === "period"
        ? [sequence]
        : prev.includes(sequence)
          ? prev.filter((s) => s !== sequence)
          : [...prev, sequence].sort((a, b) => a - b),
    );
  };

  const run = (targetPage = 1) => {
    if (selected.length === 0) return;
    setPage(targetPage);
    setParams({
      date,
      period_sequences: selected,
      match: mode === "period" ? "ALL_ABSENT" : match,
      grade_id: gradeId === "" ? null : gradeId,
      page: targetPage,
      page_size: 25,
    });
  };

  return (
    <div className="space-y-4">
      <section className="space-y-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="flex flex-wrap items-center gap-2" data-testid="period-selector">
          <span className="text-sm text-slate-600">
            {mode === "period" ? "الحصة:" : "الحصص:"}
          </span>
          {dayPeriods.map((p) => (
            <button
              key={p.sequence}
              type="button"
              onClick={() => toggle(p.sequence)}
              aria-pressed={selected.includes(p.sequence)}
              className={`rounded-lg px-3 py-1.5 text-sm font-medium ${
                selected.includes(p.sequence)
                  ? "bg-blue-600 text-white"
                  : "bg-slate-100 text-slate-600 hover:bg-slate-200"
              }`}
              data-testid={`period-option-${p.sequence}`}
            >
              {p.name}
            </button>
          ))}
        </div>

        {mode === "multi" && (
          <div className="flex flex-wrap items-center gap-4">
            <Button
              variant="secondary"
              onClick={() => setSelected([1, 2].filter((s) => dayPeriods.some((p) => p.sequence === s)))}
              data-testid="morning-preset"
            >
              غائبو بداية اليوم (الأولى + الثانية)
            </Button>
            <div className="flex gap-3 text-sm" role="radiogroup" aria-label="طريقة المطابقة">
              <label className="flex items-center gap-1">
                <input
                  type="radio"
                  checked={match === "ALL_ABSENT"}
                  onChange={() => setMatch("ALL_ABSENT")}
                  data-testid="match-all"
                />
                غائب في جميع الحصص المحددة
              </label>
              <label className="flex items-center gap-1">
                <input
                  type="radio"
                  checked={match === "ANY_ABSENT"}
                  onChange={() => setMatch("ANY_ABSENT")}
                  data-testid="match-any"
                />
                غائب في أي حصة محددة
              </label>
            </div>
          </div>
        )}

        <div className="flex flex-wrap items-center gap-2">
          <label className="text-sm text-slate-600">
            الصف{" "}
            <select
              value={gradeId}
              onChange={(e) => setGradeId(e.target.value === "" ? "" : Number(e.target.value))}
              className="rounded-lg border border-slate-300 px-2 py-1.5"
              data-testid="analytics-grade-filter"
            >
              <option value="">الكل</option>
              {grades.map(([id, name]) => (
                <option key={id} value={id}>
                  {name}
                </option>
              ))}
            </select>
          </label>
          <Button onClick={() => run(1)} disabled={selected.length === 0} data-testid="run-report">
            عرض
          </Button>
        </div>
      </section>

      {reportQuery.isFetching && !reportQuery.data && <Spinner label="جارٍ إعداد التقرير..." />}
      {reportQuery.isError && (
        <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <ErrorState error={reportQuery.error} />
        </section>
      )}
      {reportQuery.isSuccess && (
        <ReportResults
          data={reportQuery.data}
          page={page}
          onPage={(next) => run(next)}
          schoolType={schoolType}
        />
      )}
    </div>
  );
}

function ReportResults({
  data,
  page,
  onPage,
  schoolType,
}: {
  data: MultiPeriodResponse;
  page: number;
  onPage: (page: number) => void;
  schoolType: SchoolType;
}) {
  const totalPages = Math.max(Math.ceil(data.total_students / data.page_size), 1);
  return (
    <div className="space-y-4">
      <section
        className="flex flex-wrap gap-4 rounded-xl border border-slate-200 bg-white p-4 text-sm shadow-sm"
        data-testid="report-summary"
      >
        <span className="font-bold text-slate-800">
          {data.summary.matching_students} {studentCountLabel(schoolType)}{" "}
          {data.match === "ALL_ABSENT" ? (schoolType === "GIRLS" ? "غائبة في جميع الحصص المحددة" : "غائبًا في جميع الحصص المحددة") : (schoolType === "GIRLS" ? "غائبة في حصة محددة على الأقل" : "غائبًا في حصة محددة على الأقل")}
        </span>
        <span className="text-slate-600">
          فصول مكتملة البيانات: {data.summary.complete_sections}
        </span>
        <span className={data.summary.incomplete_sections > 0 ? "text-amber-700" : "text-slate-600"}>
          فصول غير مكتملة: {data.summary.incomplete_sections}
        </span>
      </section>

      {data.incomplete_sections.length > 0 && (
        <section
          className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900"
          data-testid="incomplete-warning"
        >
          <p className="mb-1 font-medium">
            ⚠️ فصول استبعد {schoolType === "GIRLS" ? "طالباتها" : "طلابها"} من النتيجة لعدم اكتمال تحضير الحصص المحددة:
          </p>
          <ul className="list-inside list-disc">
            {data.incomplete_sections.map((s) => (
              <li key={s.section_id}>
                {s.section_name} — {s.grade_name}: {s.reason}
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="rounded-xl border border-slate-200 bg-white shadow-sm">
        {data.students.length === 0 ? (
          <p className="p-6 text-slate-600" data-testid="no-matching-students">
            لا يوجد {studentPluralLabel(schoolType)} {schoolType === "GIRLS" ? "مطابقات" : "مطابقون"} لهذا الاختيار.
          </p>
        ) : (
          <ul className="divide-y divide-slate-100" data-testid="analytics-students">
            {data.students.map((student) => (
              <li
                key={student.student_id}
                className="flex flex-wrap items-center justify-between gap-2 p-3"
                data-testid={`analytics-student-${student.student_id}`}
              >
                <div>
                  <p className="font-medium text-slate-800">{student.full_name}</p>
                  <p className="text-xs text-slate-500">
                    {student.grade_name} / {student.section_name}
                  </p>
                </div>
                <div className="flex flex-wrap gap-1 text-xs">
                  {student.period_statuses.map((ps) => {
                    const label = data.periods.find((p) => p.sequence === ps.sequence)?.name;
                    return (
                      <span
                        key={ps.sequence}
                        className={`rounded-full px-2 py-1 ${
                          ps.status === "ABSENT"
                            ? "bg-red-100 text-red-800"
                            : "bg-green-100 text-green-800"
                        }`}
                      >
                        {label}: {(schoolType === "GIRLS" ? FEMININE_STATUS_BADGE : STATUS_BADGE)[ps.status]}
                      </span>
                    );
                  })}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-3 text-sm">
          <Button variant="secondary" disabled={page <= 1} onClick={() => onPage(page - 1)}>
            السابق
          </Button>
          <span>
            صفحة {page} من {totalPages}
          </span>
          <Button
            variant="secondary"
            disabled={page >= totalPages}
            onClick={() => onPage(page + 1)}
          >
            التالي
          </Button>
        </div>
      )}
    </div>
  );
}

const DAILY_FILTERS: { value: string; label: string }[] = [
  { value: "FULL", label: "غياب يوم كامل" },
  { value: "PARTIAL", label: "غياب جزئي" },
  { value: "UNDETERMINED", label: "بيانات غير مكتملة" },
  { value: "NONE", label: "بلا غياب" },
];

function DailyTab({
  date,
  activeSchoolId,
  data,
  grades,
  schoolType,
}: {
  date: string;
  activeSchoolId: number;
  data: import("@/features/attendance/api").DailyAnalyticsResponse;
  grades: [number, string][];
  schoolType: SchoolType;
}) {
  const [status, setStatus] = useState("");
  const studentsLabel = studentPluralLabel(schoolType);
  const [gradeId, setGradeId] = useState<number | "">("");
  const listQuery = useQuery({
    queryKey: schoolScopedKey(
      activeSchoolId, "attendance", "analytics", "daily-list", date, status, gradeId,
    ),
    queryFn: ({ signal }) => getDailyAnalytics({ date, status, grade: gradeId }, signal),
    enabled: status !== "",
  });

  const s = data.summary;
  const cards: [string, string, number][] = [
    ["daily-total", `إجمالي ${studentsLabel}`, s.total_students],
    ["daily-full", "غياب يوم كامل", s.full_absent],
    ["daily-partial", "غياب جزئي", s.partial_absent],
    ["daily-incomplete", "بيانات غير مكتملة", s.incomplete_students],
  ];

  return (
    <div className="space-y-4">
      <section className="grid grid-cols-2 gap-2 sm:grid-cols-4" data-testid="daily-kpis">
        {cards.map(([testId, label, value]) => (
          <div
            key={testId}
            data-testid={testId}
            className="rounded-xl border border-slate-200 bg-white p-3 text-center shadow-sm"
          >
            <p className="text-2xl font-bold text-slate-800">{value}</p>
            <p className="text-xs text-slate-500">{label}</p>
          </div>
        ))}
      </section>
      {!data.is_school_day && (
        <p className="rounded-xl border border-slate-200 bg-white p-4 text-slate-600 shadow-sm">
          لا يوجد جدول دراسي لهذا اليوم.
        </p>
      )}

      <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <label className="text-sm text-slate-600">
          عرض {studentsLabel} حسب الحالة{" "}
          <select
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            className="rounded-lg border border-slate-300 px-2 py-1.5"
            data-testid="daily-status-filter"
          >
            <option value="">— اختر —</option>
            {DAILY_FILTERS.map((f) => (
              <option key={f.value} value={f.value}>
                {f.label}
              </option>
            ))}
          </select>
        </label>
        <label className="ms-4 text-sm text-slate-600">
          الصف{" "}
          <select
            value={gradeId}
            onChange={(e) => setGradeId(e.target.value === "" ? "" : Number(e.target.value))}
            className="rounded-lg border border-slate-300 px-2 py-1.5"
            data-testid="daily-grade-filter"
          >
            <option value="">الكل</option>
            {grades.map(([id, name]) => <option key={id} value={id}>{name}</option>)}
          </select>
        </label>
        {listQuery.isFetching && (
          <div className="mt-3">
            <Spinner />
          </div>
        )}
        {listQuery.isSuccess && status !== "" && (
          <ul className="mt-3 divide-y divide-slate-100" data-testid="daily-students">
            {listQuery.data.students.length === 0 && (
              <li className="p-3 text-slate-600">لا يوجد {studentsLabel} في هذه الحالة.</li>
            )}
            {listQuery.data.students.map((student) => (
              <li
                key={student.student_id}
                className="flex flex-wrap items-center justify-between gap-2 p-3"
                data-testid={`daily-student-${student.student_id}`}
              >
                <div>
                  <p className="font-medium text-slate-800">{student.full_name}</p>
                  <p className="text-xs text-slate-500">
                    {student.grade_name} / {student.section_name}
                  </p>
                </div>
                <p className="text-sm text-slate-600">
                  غياب {student.absent_periods} من {student.expected_periods} · معتمد{" "}
                  {student.submitted_periods}/{student.expected_periods}
                </p>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
