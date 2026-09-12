import { useQuery } from "@tanstack/react-query";
import {
  BarChart3,
  Download,
  Eye,
  FileSpreadsheet,
  Filter,
  Printer,
  RotateCcw,
  Search,
  Trash2,
} from "lucide-react";
import { useDeferredValue, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { SelectField } from "@/components/FormField";
import { MetricCard } from "@/components/MetricCard";
import { PageHeader } from "@/components/PageHeader";
import { Pagination } from "@/components/Pagination";
import { Spinner } from "@/components/Spinner";
import { TableShell as DataTableShell } from "@/components/TableShell";
import { Tabs } from "@/components/Tabs";
import { TextField } from "@/components/TextField";
import { getAttendanceSections } from "@/features/attendance/api";
import { schoolScopedKey, useMe } from "@/features/auth/useMe";
import {
  getCounselors,
  getReferralOptions,
  type ReferralRow,
} from "@/features/referrals/api";
import {
  getAbsenceReport,
  downloadAbsenceReportExcel,
  downloadLatenessReportExcel,
  downloadReferralsReportExcel,
  getLatenessReport,
  getReferralsReport,
  type AbsenceRow,
  type CommonReportFilters,
  type LatenessRow,
  type ReferralReportSummary,
  type ReportPreset,
  type ReportResponse,
} from "@/features/reports/api";
import { getStudents, type StudentRow } from "@/features/students/api";
import { roleLabel, studentCountLabel, studentLabel, studentPluralLabel } from "@/utils/roles";

type Tab = "absence" | "lateness" | "referrals";

type CsvColumn<TRow> = {
  header: string;
  value: (row: TRow) => string | number | null | undefined;
};

const PRESETS: [ReportPreset, string][] = [
  ["TODAY", "اليوم"],
  ["THIS_WEEK", "هذا الأسبوع"],
  ["LAST_7_DAYS", "آخر ٧ أيام"],
  ["LAST_30_DAYS", "آخر ٣٠ يومًا"],
  ["THIS_MONTH", "هذا الشهر"],
  ["CURRENT_SEMESTER", "الفصل الدراسي الحالي"],
  ["CUSTOM", "فترة مخصصة"],
];

const INITIAL_FILTERS: CommonReportFilters = { preset: "LAST_30_DAYS", page: 1 };

const REPORT_TITLES: Record<Tab, string> = {
  absence: "تقرير الغياب",
  lateness: "تقرير التأخر الصباحي",
  referrals: "تقرير الإحالات للمرشد",
};

function todayIso(offsetDays = 0) {
  const date = new Date();
  date.setDate(date.getDate() + offsetDays);
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

function formatDate(value?: string) {
  if (!value) return "—";
  return new Date(`${value}T00:00:00`).toLocaleDateString("ar-SA");
}

function formatDateTime(value: Date) {
  return value.toLocaleString("ar-SA", {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function formatRange(context?: ReportResponse<unknown, unknown>["context"]) {
  if (!context) return "لم يتم تحميل الفترة بعد";
  return `${formatDate(context.range.from_date)} - ${formatDate(context.range.to_date)}`;
}

function formatScope(context?: ReportResponse<unknown, unknown>["context"]) {
  if (!context) return "نطاق المدرسة الحالية";
  if (context.scope.section_id) return "فصل محدد حسب الفلتر";
  if (context.scope.grade_id) return "صف محدد حسب الفلتر";
  return "كل المدرسة";
}

function csvCell(value: string | number | null | undefined) {
  const text = value == null ? "" : String(value);
  return `"${text.replaceAll('"', '""')}"`;
}

function downloadCsv<TRow>(filename: string, rows: TRow[], columns: CsvColumn<TRow>[]) {
  const lines = [
    columns.map((column) => csvCell(column.header)).join(","),
    ...rows.map((row) => columns.map((column) => csvCell(column.value(row))).join(",")),
  ];
  const blob = new Blob([`\uFEFF${lines.join("\n")}`], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function fileDate(context?: ReportResponse<unknown, unknown>["context"]) {
  return context?.range.to_date ?? todayIso();
}

export function ReportsPage() {
  const me = useMe();
  const schoolId = me.data?.active_school?.id ?? 0;
  const schoolName = me.data?.active_school?.name ?? "المدرسة الحالية";
  const schoolType = me.data?.active_school?.school_type ?? "BOYS";
  const [tab, setTab] = useState<Tab>("absence");
  const [draft, setDraft] = useState<CommonReportFilters>({
    ...INITIAL_FILTERS,
    fromDate: todayIso(-29),
    toDate: todayIso(),
  });
  const [selectedStudent, setSelectedStudent] = useState<StudentRow | null>(null);
  const [clearedReports, setClearedReports] = useState<Record<Tab, boolean>>({
    absence: false,
    lateness: false,
    referrals: false,
  });

  const sectionsQuery = useQuery({
    queryKey: schoolScopedKey(schoolId, "attendance", "sections"),
    queryFn: ({ signal }) => getAttendanceSections(signal),
    enabled: schoolId > 0,
  });
  const grades = useMemo(() => {
    const values = new Map<number, string>();
    for (const section of sectionsQuery.data ?? []) {
      if (section.grade_id != null) values.set(section.grade_id, section.grade_name);
    }
    return [...values.entries()];
  }, [sectionsQuery.data]);
  const sections = (sectionsQuery.data ?? []).filter(
    (section) => !draft.grade || section.grade_id === draft.grade,
  );

  const updateFilters = (next: React.SetStateAction<CommonReportFilters>) => {
    setDraft((current) => {
      const resolved = typeof next === "function" ? next(current) : next;
      return { ...resolved, page: 1 };
    });
    setClearedReports((current) => ({ ...current, [tab]: false }));
  };
  const reset = () => {
    const clean = { ...INITIAL_FILTERS, fromDate: todayIso(-29), toDate: todayIso() };
    setDraft(clean);
    setSelectedStudent(null);
    setClearedReports({ absence: false, lateness: false, referrals: false });
  };
  const clearCurrentReport = () => setClearedReports((current) => ({ ...current, [tab]: true }));
  const restoreCurrentReport = () => setClearedReports((current) => ({ ...current, [tab]: false }));

  return (
    <div className="ds-page" data-testid="reports-page">
      <PageHeader
        icon={BarChart3}
        eyebrow="التحليل والتوثيق"
        title="مركز التقارير"
        description={`تقارير الغياب والتأخر والإحالات المخصصة ${schoolType === "GIRLS" ? "لمديرة المدرسة والوكيلة" : "لمدير المدرسة والوكيل"}.`}
        tone="executive"
        badge="نطاق المدرسة الحالية"
        actions={<Button variant="secondary" onClick={() => window.print()}><Printer aria-hidden size={17} /> طباعة التقرير النشط</Button>}
      />

      <Tabs
        value={tab}
        onChange={(nextTab) => setTab(nextTab)}
        label="أنواع التقارير"
        className="print:hidden"
        items={[
          { value: "absence", label: "الغياب" },
          { value: "lateness", label: "التأخر" },
          { value: "referrals", label: "الإحالات للمرشد" },
        ]}
      />

      <ReportFilters
        schoolId={schoolId}
        draft={draft}
        setDraft={updateFilters}
        selectedStudent={selectedStudent}
        setSelectedStudent={(student) => {
          setSelectedStudent(student);
          setDraft((current) => ({ ...current, student: student?.id ?? null, page: 1 }));
          setClearedReports((current) => ({ ...current, [tab]: false }));
        }}
        grades={grades}
        sections={sections}
        onReset={reset}
        schoolType={schoolType}
      />

      {tab === "absence" && (
        <AbsenceReport
          schoolId={schoolId}
          filters={draft}
          onPage={(page) => setDraft((current) => ({ ...current, page }))}
          schoolType={schoolType}
          schoolName={schoolName}
          isCleared={clearedReports.absence}
          onClear={clearCurrentReport}
          onRestore={restoreCurrentReport}
        />
      )}
      {tab === "lateness" && (
        <LatenessReport
          schoolId={schoolId}
          filters={draft}
          onPage={(page) => setDraft((current) => ({ ...current, page }))}
          schoolType={schoolType}
          schoolName={schoolName}
          isCleared={clearedReports.lateness}
          onClear={clearCurrentReport}
          onRestore={restoreCurrentReport}
        />
      )}
      {tab === "referrals" && (
        <ReferralsReport
          schoolId={schoolId}
          filters={draft}
          onPage={(page) => setDraft((current) => ({ ...current, page }))}
          schoolType={schoolType}
          schoolName={schoolName}
          isCleared={clearedReports.referrals}
          onClear={clearCurrentReport}
          onRestore={restoreCurrentReport}
        />
      )}
    </div>
  );
}

function ReportFilters({ schoolId, draft, setDraft, selectedStudent, setSelectedStudent, grades, sections, onReset, schoolType }: {
  schoolId: number;
  draft: CommonReportFilters;
  setDraft: React.Dispatch<React.SetStateAction<CommonReportFilters>>;
  selectedStudent: StudentRow | null;
  setSelectedStudent: (student: StudentRow | null) => void;
  grades: [number, string][];
  sections: Awaited<ReturnType<typeof getAttendanceSections>>;
  onReset: () => void;
  schoolType: "BOYS" | "GIRLS";
}) {
  const [search, setSearch] = useState("");
  const deferredSearch = useDeferredValue(search.trim());
  const candidates = useQuery({
    queryKey: schoolScopedKey(schoolId, "reports", "students", deferredSearch, draft.grade, draft.section),
    queryFn: ({ signal }) => getStudents({ search: deferredSearch, grade: draft.grade, section: draft.section, status: "ACTIVE" }, signal),
    enabled: schoolId > 0 && deferredSearch.length >= 2 && !selectedStudent,
  });
  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm print:hidden">
      <div className="mb-4 flex items-center gap-2"><Filter aria-hidden size={18} className="text-slate-500" /><h2 className="font-black text-slate-900">فلاتر التقرير</h2></div>
      <div className="grid min-w-0 gap-3 sm:grid-cols-2 lg:grid-cols-4 [&>*]:min-w-0">
        <label className="text-xs font-bold text-slate-600">الفترة<select value={draft.preset} onChange={(event) => setDraft((current) => ({ ...current, preset: event.target.value as ReportPreset }))} className="mt-1 h-11 w-full rounded-xl border border-slate-300 bg-white px-3 text-sm">{PRESETS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        {draft.preset === "CUSTOM" && <><label className="text-xs font-bold text-slate-600">من<input type="date" value={draft.fromDate} onChange={(event) => setDraft((current) => ({ ...current, fromDate: event.target.value }))} className="mt-1 h-11 w-full rounded-xl border border-slate-300 px-3 text-sm" /></label><label className="text-xs font-bold text-slate-600">إلى<input type="date" value={draft.toDate} onChange={(event) => setDraft((current) => ({ ...current, toDate: event.target.value }))} className="mt-1 h-11 w-full rounded-xl border border-slate-300 px-3 text-sm" /></label></>}
        <label className="text-xs font-bold text-slate-600">الصف<select value={draft.grade ?? ""} onChange={(event) => { setSelectedStudent(null); setDraft((current) => ({ ...current, grade: event.target.value ? Number(event.target.value) : "", section: "", student: null })); }} className="mt-1 h-11 w-full rounded-xl border border-slate-300 bg-white px-3 text-sm"><option value="">كل الصفوف</option>{grades.map(([id, name]) => <option key={id} value={id}>{name}</option>)}</select></label>
        <label className="text-xs font-bold text-slate-600">الفصل<select value={draft.section ?? ""} onChange={(event) => { setSelectedStudent(null); setDraft((current) => ({ ...current, section: event.target.value ? Number(event.target.value) : "", student: null })); }} className="mt-1 h-11 w-full rounded-xl border border-slate-300 bg-white px-3 text-sm"><option value="">كل الفصول</option>{sections.map((section) => <option key={section.id} value={section.id}>{section.grade_name} / {section.name}</option>)}</select></label>
        <div className="relative text-xs font-bold text-slate-600 lg:col-span-2">{studentLabel(schoolType, true)}<div className="relative mt-1"><Search aria-hidden size={16} className="pointer-events-none absolute end-3 top-3.5 text-slate-400" /><input aria-label={`البحث عن ${studentLabel(schoolType, true)}`} value={selectedStudent ? selectedStudent.full_name : search} onChange={(event) => { setSelectedStudent(null); setSearch(event.target.value); }} placeholder={`اكتب حرفين من اسم ${studentLabel(schoolType, true)}`} className="h-11 w-full rounded-xl border border-slate-300 px-3 pe-10 text-sm" /></div>{candidates.isSuccess && candidates.data.results.length > 0 && !selectedStudent && <ul className="absolute z-20 mt-1 max-h-56 w-full overflow-y-auto rounded-xl border border-slate-200 bg-white p-1 shadow-xl">{candidates.data.results.map((student) => <li key={student.id}><button type="button" onClick={() => { setSelectedStudent(student); setSearch(""); }} className="w-full rounded-lg p-2 text-start text-sm hover:bg-slate-100"><b className="block text-slate-900">{student.full_name}</b><span className="text-xs font-normal text-slate-500">{student.grade?.name ?? "—"} / {student.section?.name ?? "—"}</span></button></li>)}</ul>}</div>
      </div>
      <div className="mt-4 flex flex-wrap gap-2"><Button onClick={() => setDraft((current) => ({ ...current, page: 1 }))}><Filter aria-hidden size={16} /> تحديث النتائج</Button><Button variant="secondary" onClick={onReset}><RotateCcw aria-hidden size={16} /> إعادة ضبط</Button>{selectedStudent && <button type="button" onClick={() => setSelectedStudent(null)} className="rounded-xl bg-blue-50 px-3 text-xs font-bold text-blue-800">{selectedStudent.full_name} ×</button>}</div>
    </section>
  );
}

function AbsenceReport({ schoolId, filters, onPage, schoolType, schoolName, isCleared, onClear, onRestore }: ReportProps) {
  const [absenceType, setAbsenceType] = useState("ALL");
  const [excuseType, setExcuseType] = useState("ALL");
  const [excelLoading, setExcelLoading] = useState(false);
  const report = useQuery({
    queryKey: schoolScopedKey(schoolId, "reports", "absence", filters, absenceType, excuseType),
    queryFn: ({ signal }) => getAbsenceReport(filters, { absenceType, excuseType }, signal),
    enabled: schoolId > 0 && !isCleared,
  });
  return (
    <ReportFrame
      title={REPORT_TITLES.absence}
      description="نتائج الغياب مجمعة حسب الطالب مع فصل الغياب الكامل والجزئي والأعذار."
      fileSlug="absence-report"
      schoolName={schoolName}
      query={report}
      rows={report.data?.results ?? []}
      columns={absenceColumns}
      controls={<><Select label="نوع الغياب" value={absenceType} onChange={(value) => { setAbsenceType(value); onPage(1); }} options={[["ALL", "الكل"], ["FULL", "يوم كامل"], ["PARTIAL", "جزئي"]]} /><Select label="حالة العذر" value={excuseType} onChange={(value) => { setExcuseType(value); onPage(1); }} options={[["ALL", "الكل"], ["UNEXCUSED", "دون عذر"], ["EXCUSED", "بعذر فقط"], ["MIXED", "مختلط"]]} /></>}
      summary={report.data && <div className="grid grid-cols-2 gap-2 sm:grid-cols-4"><MetricCard label={studentPluralLabel(schoolType)} value={report.data.summary.students} /><MetricCard label="أيام غياب كامل" value={report.data.summary.full_absence_days} tone="red" /><MetricCard label="أيام غياب جزئي" value={report.data.summary.partial_absence_days} tone="amber" /><MetricCard label="حصص دون عذر" value={report.data.summary.unexcused_absent_periods} tone="red" /></div>}
      table={report.data && <AbsenceTable rows={report.data.results} />}
      footer={report.data && <Pagination page={report.data.page} totalPages={Math.max(Math.ceil(report.data.count / report.data.page_size), 1)} onChange={onPage} />}
      excelLoading={excelLoading}
      onExportExcel={async () => {
        setExcelLoading(true);
        try {
          await downloadAbsenceReportExcel(filters, { absenceType, excuseType });
        } catch (error) {
          window.alert(error instanceof Error ? error.message : "تعذر تصدير ملف Excel.");
        } finally {
          setExcelLoading(false);
        }
      }}
      isCleared={isCleared}
      onClear={onClear}
      onRestore={onRestore}
    />
  );
}

function LatenessReport({ schoolId, filters, onPage, schoolType, schoolName, isCleared, onClear, onRestore }: ReportProps) {
  const [minOccurrences, setMinOccurrences] = useState(0);
  const [minMinutes, setMinMinutes] = useState(0);
  const [excelLoading, setExcelLoading] = useState(false);
  const report = useQuery({
    queryKey: schoolScopedKey(schoolId, "reports", "lateness", filters, minOccurrences, minMinutes),
    queryFn: ({ signal }) => getLatenessReport(filters, { minOccurrences, minMinutes }, signal),
    enabled: schoolId > 0 && !isCleared,
  });
  return (
    <ReportFrame
      title={REPORT_TITLES.lateness}
      description="نتائج التأخر الصباحي من سجلات الحضور الصباحي فقط."
      fileSlug="lateness-report"
      schoolName={schoolName}
      query={report}
      rows={report.data?.results ?? []}
      columns={latenessColumns}
      controls={<><NumberFilter label="الحد الأدنى للمرات" value={minOccurrences} onChange={setMinOccurrences} /><NumberFilter label="الحد الأدنى للدقائق" value={minMinutes} onChange={setMinMinutes} /></>}
      summary={report.data && <div className="grid grid-cols-2 gap-2 sm:grid-cols-3"><MetricCard label={studentCountLabel(schoolType)} value={report.data.summary.students} /><MetricCard label="مرات التأخر الصباحي" value={report.data.summary.morning_occurrences} tone="amber" /><MetricCard label="دقائق التأخر الصباحي" value={report.data.summary.morning_minutes} /></div>}
      table={report.data && <LatenessTable rows={report.data.results} />}
      footer={report.data && <Pagination page={report.data.page} totalPages={Math.max(Math.ceil(report.data.count / report.data.page_size), 1)} onChange={onPage} />}
      excelLoading={excelLoading}
      onExportExcel={async () => {
        setExcelLoading(true);
        try {
          await downloadLatenessReportExcel(filters, { minOccurrences, minMinutes });
        } catch (error) {
          window.alert(error instanceof Error ? error.message : "تعذر تصدير ملف Excel.");
        } finally {
          setExcelLoading(false);
        }
      }}
      isCleared={isCleared}
      onClear={onClear}
      onRestore={onRestore}
    />
  );
}

function ReferralsReport({ schoolId, filters, onPage, schoolType, schoolName, isCleared, onClear, onRestore }: ReportProps) {
  const [status, setStatus] = useState("");
  const [category, setCategory] = useState("");
  const [reason, setReason] = useState("");
  const [source, setSource] = useState("");
  const [counselor, setCounselor] = useState("");
  const [priority, setPriority] = useState("");
  const [excelLoading, setExcelLoading] = useState(false);
  const options = useQuery({ queryKey: schoolScopedKey(schoolId, "referral-options"), queryFn: ({ signal }) => getReferralOptions(signal), enabled: schoolId > 0 });
  const counselors = useQuery({ queryKey: schoolScopedKey(schoolId, "referral-counselors"), queryFn: ({ signal }) => getCounselors(signal), enabled: schoolId > 0 });
  const reasons = options.data?.categories.find((item) => item.value === category)?.reasons ?? [];
  const extra = { status, category, reason_code: reason, source_type: source, counselor, priority };
  const report = useQuery({
    queryKey: schoolScopedKey(schoolId, "reports", "referrals", filters, extra),
    queryFn: ({ signal }) => getReferralsReport(filters, extra, signal),
    enabled: schoolId > 0 && !isCleared,
  });
  return (
    <ReportFrame<ReferralRow, ReferralReportSummary>
      title={REPORT_TITLES.referrals}
      description="الإحالات المعروضة للمدير والوكيل حسب نطاق الرؤية والصلاحيات الحالية."
      fileSlug="referrals-report"
      schoolName={schoolName}
      query={report}
      rows={report.data?.results ?? []}
      columns={referralColumns}
      controls={<><Select label="الحالة" value={status} onChange={setStatus} options={[["", "الكل"], ["OPEN", "المفتوحة"], ["PENDING_VICE", "بانتظار الوكيل"], ["UNDER_VICE_REVIEW", "قيد معالجة الوكيل"], ["REFERRED", "محوّلة للمرشد"], ["ACKNOWLEDGED", "قيد متابعة المرشد"], ["CLOSED", "مغلقة"], ["CANCELLED", "ملغاة"]]} /><Select label="الأولوية" value={priority} onChange={setPriority} options={[["", "الكل"], ["HIGH", "عاجلة"], ["NORMAL", "عادية"]]} /><Select label="الفئة" value={category} onChange={(value) => { setCategory(value); setReason(""); }} options={[["", "الكل"], ...(options.data?.categories.map((item) => [item.value, item.label] as [string, string]) ?? [])]} /><Select label="السبب" value={reason} onChange={setReason} options={[["", "الكل"], ...reasons.map((item) => [item.value, item.label] as [string, string])]} /><Select label="المُحيل" value={source} onChange={setSource} options={[["", "الكل"], ["TEACHER", roleLabel("TEACHER", schoolType)], ["VICE_PRINCIPAL", roleLabel("VICE_PRINCIPAL", schoolType)], ["SCHOOL_MANAGER", roleLabel("SCHOOL_MANAGER", schoolType)]]} /><Select label="المرشد" value={counselor} onChange={setCounselor} options={[["", "الكل"], ["UNASSIGNED", "غير معيّنة"], ...(counselors.data?.counselors.map((item) => [String(item.id), item.name] as [string, string]) ?? [])]} /></>}
      summary={report.data && <div className="grid grid-cols-2 gap-2 sm:grid-cols-4"><MetricCard label="إجمالي الإحالات" value={report.data.summary.total} /><MetricCard label="بانتظار الوكيل" value={report.data.summary.new} tone="amber" /><MetricCard label="تحتاج تعيين وكيل" value={report.data.summary.unassigned} tone="red" /><MetricCard label="محوّلة للمرشد" value={report.data.summary.referred} tone="blue" /></div>}
      table={report.data && <ReferralsTable rows={report.data.results} />}
      footer={report.data && <Pagination page={report.data.page} totalPages={Math.max(Math.ceil(report.data.count / report.data.page_size), 1)} onChange={onPage} />}
      excelLoading={excelLoading}
      onExportExcel={async () => {
        setExcelLoading(true);
        try {
          await downloadReferralsReportExcel(filters, extra);
        } catch (error) {
          window.alert(error instanceof Error ? error.message : "تعذر تصدير ملف Excel.");
        } finally {
          setExcelLoading(false);
        }
      }}
      isCleared={isCleared}
      onClear={onClear}
      onRestore={onRestore}
    />
  );
}

interface ReportProps {
  schoolId: number;
  filters: CommonReportFilters;
  onPage: (page: number) => void;
  schoolType: "BOYS" | "GIRLS";
  schoolName: string;
  isCleared: boolean;
  onClear: () => void;
  onRestore: () => void;
}

function ReportFrame<TRow, TSummary = unknown>({
  title,
  description,
  fileSlug,
  schoolName,
  controls,
  query,
  rows,
  columns,
  summary,
  table,
  footer,
  excelLoading,
  onExportExcel,
  isCleared,
  onClear,
  onRestore,
}: {
  title: string;
  description: string;
  fileSlug: string;
  schoolName: string;
  controls: React.ReactNode;
  query: {
    isPending: boolean;
    isError: boolean;
    error: unknown;
    data?: ReportResponse<TSummary, TRow>;
  };
  rows: TRow[];
  columns: CsvColumn<TRow>[];
  summary?: React.ReactNode;
  table?: React.ReactNode;
  footer?: React.ReactNode;
  excelLoading: boolean;
  onExportExcel: () => Promise<void>;
  isCleared: boolean;
  onClear: () => void;
  onRestore: () => void;
}) {
  const count = query.data?.count ?? rows.length;
  const canUseResults = rows.length > 0 && !isCleared;
  return (
    <div className="space-y-4">
      <section className="flex flex-wrap gap-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm print:hidden">{controls}</section>

      {isCleared ? (
        <section className="rounded-2xl border border-dashed border-slate-300 bg-white p-5 text-center shadow-sm print:hidden">
          <h2 className="text-lg font-black text-slate-900">تم مسح النتائج المعروضة</h2>
          <p className="mx-auto mt-2 max-w-2xl text-sm leading-6 text-slate-500">
            هذا الإجراء يخفي نتائج التقرير من الشاشة فقط ولا يحذف سجلات الطلاب أو الحضور أو الإحالات.
          </p>
          <Button className="mt-4" variant="secondary" onClick={onRestore}><Eye aria-hidden size={16} /> إظهار النتائج مرة أخرى</Button>
        </section>
      ) : (
        <section className="report-print-root rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5" data-testid="report-results">
          <header className="report-print-heading flex flex-col justify-between gap-4 border-b border-slate-100 pb-4 lg:flex-row lg:items-start">
            <div className="min-w-0">
              <p className="text-xs font-bold text-slate-500">تقرير مدرسي رسمي</p>
              <h2 className="mt-1 text-xl font-black text-slate-950">{title}</h2>
              <p className="mt-1 text-sm leading-6 text-slate-500">{description}</p>
            </div>
            <dl className="grid gap-1 text-xs text-slate-600 sm:grid-cols-2 lg:min-w-[24rem]">
              <div><dt className="font-bold text-slate-500">المدرسة</dt><dd className="font-semibold text-slate-900">{schoolName}</dd></div>
              <div><dt className="font-bold text-slate-500">الفترة</dt><dd className="font-semibold text-slate-900">{formatRange(query.data?.context)}</dd></div>
              <div><dt className="font-bold text-slate-500">النطاق</dt><dd className="font-semibold text-slate-900">{formatScope(query.data?.context)}</dd></div>
              <div><dt className="font-bold text-slate-500">وقت الإعداد</dt><dd className="font-semibold text-slate-900">{formatDateTime(new Date())}</dd></div>
            </dl>
          </header>

          <div className="report-screen-only mt-4 flex flex-col justify-between gap-3 rounded-xl bg-slate-50 p-3 sm:flex-row sm:items-center">
            <p className="text-sm font-bold text-slate-700">
              {count > 0 ? `عدد النتائج المطابقة: ${count}` : "لا توجد نتائج مطابقة للفلاتر الحالية"}
            </p>
            <div className="flex flex-wrap gap-2">
              <Button
                variant="secondary"
                size="sm"
                disabled={!query.data || excelLoading}
                loading={excelLoading}
                loadingLabel="جارٍ تصدير Excel..."
                onClick={onExportExcel}
              >
                <FileSpreadsheet aria-hidden size={15} /> تصدير Excel
              </Button>
              <Button
                variant="secondary"
                size="sm"
                disabled={!canUseResults}
                onClick={() => downloadCsv(`${fileSlug}-${fileDate(query.data?.context)}.csv`, rows, columns)}
              >
                <Download aria-hidden size={15} /> تصدير المعروض CSV
              </Button>
              <Button variant="secondary" size="sm" disabled={!query.data} onClick={() => window.print()}><Printer aria-hidden size={15} /> طباعة واضحة</Button>
              <Button variant="danger" size="sm" disabled={!query.data} onClick={onClear}><Trash2 aria-hidden size={15} /> مسح النتائج المعروضة</Button>
            </div>
          </div>

          {query.isPending && <Spinner label="جارٍ إعداد التقرير..." />}
          {query.isError && <ErrorState error={query.error} />}
          {summary && <div className="mt-4">{summary}</div>}
          {table && <div className="mt-4">{table}</div>}
          {footer && <div className="report-screen-only mt-4">{footer}</div>}
        </section>
      )}
    </div>
  );
}

function Select({ label, value, onChange, options }: { label: string; value: string; onChange: (value: string) => void; options: [string, string][] }) { return <SelectField label={label} value={value} onChange={(event) => onChange(event.target.value)} className="min-w-40">{options.map(([option, text]) => <option key={option} value={option}>{text}</option>)}</SelectField>; }
function NumberFilter({ label, value, onChange }: { label: string; value: number; onChange: (value: number) => void }) { return <TextField label={label} type="number" min={0} value={value} onChange={(event) => onChange(Math.max(Number(event.target.value), 0))} className="min-w-40" />; }
function TableShell({ children, empty }: { children: React.ReactNode; empty: boolean }) { return <DataTableShell>{empty ? <EmptyState title="لا توجد نتائج" description="غيّر الفلاتر أو الفترة ثم أعد المحاولة." compact /> : <table className="w-full min-w-[760px] text-sm">{children}</table>}</DataTableShell>; }
function AbsenceTable({ rows }: { rows: AbsenceRow[] }) { return <TableShell empty={rows.length === 0}><thead><tr className="border-b bg-slate-50 text-slate-500"><Th>الطالب</Th><Th>الصف/الفصل</Th><Th>كامل</Th><Th>جزئي</Th><Th>حصص غياب</Th><Th>بعذر</Th><Th>دون عذر</Th><Th /></tr></thead><tbody>{rows.map((row) => <tr key={`${row.student_id}-${row.section_name}`} className="border-b last:border-0"><Td strong>{row.full_name}</Td><Td>{row.grade_name} / {row.section_name}</Td><Td>{row.full_absence_days}</Td><Td>{row.partial_absence_days}</Td><Td>{row.absent_periods}</Td><Td>{row.excused_absent_periods}</Td><Td>{row.unexcused_absent_periods}</Td><Td><Link to={`/students/${row.student_id}/attendance`} className="font-bold text-blue-700">التفاصيل</Link></Td></tr>)}</tbody></TableShell>; }
function LatenessTable({ rows }: { rows: LatenessRow[] }) { return <TableShell empty={rows.length === 0}><thead><tr className="border-b bg-slate-50 text-slate-500"><Th>الطالب</Th><Th>الصف/الفصل</Th><Th>مرات التأخر الصباحي</Th><Th>الدقائق المحتسبة</Th><Th /></tr></thead><tbody>{rows.map((row) => <tr key={row.student_id} className="border-b last:border-0"><Td strong>{row.full_name}</Td><Td>{row.grade_name ?? "—"} / {row.section_name ?? "—"}</Td><Td>{row.morning_occurrences}</Td><Td>{row.morning_minutes}</Td><Td><Link to={`/students/${row.student_id}/attendance`} className="font-bold text-blue-700">التفاصيل</Link></Td></tr>)}</tbody></TableShell>; }
function ReferralsTable({ rows }: { rows: ReferralRow[] }) { return <TableShell empty={rows.length === 0}><thead><tr className="border-b bg-slate-50 text-slate-500"><Th>الطالب</Th><Th>الفئة/السبب</Th><Th>المُحيل</Th><Th>الوكيل المسؤول</Th><Th>المرشد</Th><Th>الأولوية</Th><Th>الحالة</Th><Th>التاريخ</Th></tr></thead><tbody>{rows.map((row) => <tr key={row.id} className="border-b last:border-0"><Td strong>{row.student.full_name}</Td><Td>{row.category_label}<span className="block text-xs text-slate-500">{row.reason_label}</span></Td><Td>{row.created_by_name ?? "—"}</Td><Td>{row.assigned_vice_principal_name ?? "غير معيّن"}</Td><Td>{row.assigned_counselor_name ?? "لم تُحوّل"}</Td><Td><Badge tone={row.priority === "HIGH" ? "danger" : "neutral"}>{row.priority_label}</Badge></Td><Td><Badge tone={row.status === "CLOSED" ? "success" : row.status === "CANCELLED" ? "danger" : "brand"} dot>{row.status_label}</Badge></Td><Td>{new Date(row.created_at).toLocaleDateString("ar-SA")}</Td></tr>)}</tbody></TableShell>; }
function Th({ children }: { children?: React.ReactNode }) { return <th className="p-3 text-start font-bold">{children}</th>; }
function Td({ children, strong = false }: { children: React.ReactNode; strong?: boolean }) { return <td className={`p-3 ${strong ? "font-black text-slate-900" : "text-slate-700"}`}>{children}</td>; }

const absenceColumns: CsvColumn<AbsenceRow>[] = [
  { header: "الطالب", value: (row) => row.full_name },
  { header: "الصف", value: (row) => row.grade_name },
  { header: "الفصل", value: (row) => row.section_name },
  { header: "أيام غياب كامل", value: (row) => row.full_absence_days },
  { header: "أيام غياب جزئي", value: (row) => row.partial_absence_days },
  { header: "حصص غياب", value: (row) => row.absent_periods },
  { header: "حصص بعذر", value: (row) => row.excused_absent_periods },
  { header: "حصص دون عذر", value: (row) => row.unexcused_absent_periods },
];

const latenessColumns: CsvColumn<LatenessRow>[] = [
  { header: "الطالب", value: (row) => row.full_name },
  { header: "الصف", value: (row) => row.grade_name },
  { header: "الفصل", value: (row) => row.section_name },
  { header: "مرات التأخر الصباحي", value: (row) => row.morning_occurrences },
  { header: "الدقائق المحتسبة", value: (row) => row.morning_minutes },
];

const referralColumns: CsvColumn<ReferralRow>[] = [
  { header: "الطالب", value: (row) => row.student.full_name },
  { header: "الصف", value: (row) => row.student.grade_name },
  { header: "الفصل", value: (row) => row.student.section_name },
  { header: "الفئة", value: (row) => row.category_label },
  { header: "السبب", value: (row) => row.reason_label },
  { header: "المحيل", value: (row) => row.created_by_name },
  { header: "الوكيل المسؤول", value: (row) => row.assigned_vice_principal_name ?? "غير معيّن" },
  { header: "المرشد", value: (row) => row.assigned_counselor_name ?? "غير معيّن" },
  { header: "الأولوية", value: (row) => row.priority_label },
  { header: "الحالة", value: (row) => row.status_label },
  { header: "التاريخ", value: (row) => new Date(row.created_at).toLocaleDateString("ar-SA") },
];
