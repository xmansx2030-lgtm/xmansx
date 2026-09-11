import { useQuery } from "@tanstack/react-query";
import { BarChart3, Filter, Printer, RotateCcw, Search } from "lucide-react";
import { useDeferredValue, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { Button } from "@/components/Button";
import { Badge } from "@/components/Badge";
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
  getLatenessReport,
  getReferralsReport,
  type AbsenceRow,
  type CommonReportFilters,
  type LatenessRow,
  type ReportPreset,
} from "@/features/reports/api";
import { getStudents, type StudentRow } from "@/features/students/api";
import { roleLabel, studentCountLabel, studentLabel, studentPluralLabel } from "@/utils/roles";

type Tab = "absence" | "lateness" | "referrals";

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

function todayIso(offsetDays = 0) {
  const date = new Date();
  date.setDate(date.getDate() + offsetDays);
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

export function ReportsPage() {
  const me = useMe();
  const schoolId = me.data?.active_school?.id ?? 0;
  const schoolType = me.data?.active_school?.school_type ?? "BOYS";
  const [tab, setTab] = useState<Tab>("absence");
  const [draft, setDraft] = useState<CommonReportFilters>({
    ...INITIAL_FILTERS,
    fromDate: todayIso(-29),
    toDate: todayIso(),
  });
  const [applied, setApplied] = useState(draft);
  const [selectedStudent, setSelectedStudent] = useState<StudentRow | null>(null);

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

  const apply = () => setApplied({ ...draft, student: selectedStudent?.id ?? null, page: 1 });
  const reset = () => {
    const clean = { ...INITIAL_FILTERS, fromDate: todayIso(-29), toDate: todayIso() };
    setDraft(clean);
    setApplied(clean);
    setSelectedStudent(null);
  };

  return (
    <div className="ds-page" data-testid="reports-page">
      <PageHeader
        icon={BarChart3}
        eyebrow="التحليل والتوثيق"
        title="مركز التقارير"
        description={`تقارير الغياب والتأخر والإحالات المخصصة ${schoolType === "GIRLS" ? "لمديرة المدرسة والوكيلة" : "لمدير المدرسة والوكيل"}.`}
        tone="executive"
        badge="نطاق المدرسة الحالية"
        actions={<Button variant="secondary" onClick={() => window.print()}><Printer aria-hidden size={17} /> طباعة التقرير</Button>}
      />

      <Tabs
        value={tab}
        onChange={setTab}
        label="أنواع التقارير"
        items={[
          { value: "absence", label: "الغياب" },
          { value: "lateness", label: "التأخر" },
          { value: "referrals", label: "الإحالات للمرشد" },
        ]}
      />

      <ReportFilters
        schoolId={schoolId}
        draft={draft}
        setDraft={setDraft}
        selectedStudent={selectedStudent}
        setSelectedStudent={setSelectedStudent}
        grades={grades}
        sections={sections}
        onApply={apply}
        onReset={reset}
        schoolType={schoolType}
      />

      {tab === "absence" && <AbsenceReport schoolId={schoolId} filters={applied} onPage={(page) => setApplied((current) => ({ ...current, page }))} schoolType={schoolType} />}
      {tab === "lateness" && <LatenessReport schoolId={schoolId} filters={applied} onPage={(page) => setApplied((current) => ({ ...current, page }))} schoolType={schoolType} />}
      {tab === "referrals" && <ReferralsReport schoolId={schoolId} filters={applied} onPage={(page) => setApplied((current) => ({ ...current, page }))} schoolType={schoolType} />}
    </div>
  );
}

function ReportFilters({ schoolId, draft, setDraft, selectedStudent, setSelectedStudent, grades, sections, onApply, onReset, schoolType }: {
  schoolId: number;
  draft: CommonReportFilters;
  setDraft: React.Dispatch<React.SetStateAction<CommonReportFilters>>;
  selectedStudent: StudentRow | null;
  setSelectedStudent: (student: StudentRow | null) => void;
  grades: [number, string][];
  sections: Awaited<ReturnType<typeof getAttendanceSections>>;
  onApply: () => void;
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
        <label className="text-xs font-bold text-slate-600">الصف<select value={draft.grade ?? ""} onChange={(event) => { setSelectedStudent(null); setDraft((current) => ({ ...current, grade: event.target.value ? Number(event.target.value) : "", section: "" })); }} className="mt-1 h-11 w-full rounded-xl border border-slate-300 bg-white px-3 text-sm"><option value="">كل الصفوف</option>{grades.map(([id, name]) => <option key={id} value={id}>{name}</option>)}</select></label>
        <label className="text-xs font-bold text-slate-600">الفصل<select value={draft.section ?? ""} onChange={(event) => { setSelectedStudent(null); setDraft((current) => ({ ...current, section: event.target.value ? Number(event.target.value) : "" })); }} className="mt-1 h-11 w-full rounded-xl border border-slate-300 bg-white px-3 text-sm"><option value="">كل الفصول</option>{sections.map((section) => <option key={section.id} value={section.id}>{section.grade_name} / {section.name}</option>)}</select></label>
        <div className="relative text-xs font-bold text-slate-600 lg:col-span-2">{studentLabel(schoolType, true)}<div className="relative mt-1"><Search aria-hidden size={16} className="pointer-events-none absolute end-3 top-3.5 text-slate-400" /><input aria-label={`البحث عن ${studentLabel(schoolType, true)}`} value={selectedStudent ? selectedStudent.full_name : search} onChange={(event) => { setSelectedStudent(null); setSearch(event.target.value); }} placeholder={`اكتب حرفين من اسم ${studentLabel(schoolType, true)}`} className="h-11 w-full rounded-xl border border-slate-300 px-3 pe-10 text-sm" /></div>{candidates.isSuccess && candidates.data.results.length > 0 && !selectedStudent && <ul className="absolute z-20 mt-1 max-h-56 w-full overflow-y-auto rounded-xl border border-slate-200 bg-white p-1 shadow-xl">{candidates.data.results.map((student) => <li key={student.id}><button type="button" onClick={() => { setSelectedStudent(student); setSearch(""); }} className="w-full rounded-lg p-2 text-start text-sm hover:bg-slate-100"><b className="block text-slate-900">{student.full_name}</b><span className="text-xs font-normal text-slate-500">{student.grade?.name ?? "—"} / {student.section?.name ?? "—"}</span></button></li>)}</ul>}</div>
      </div>
      <div className="mt-4 flex flex-wrap gap-2"><Button onClick={onApply}><Filter aria-hidden size={16} /> تطبيق الفلاتر</Button><Button variant="secondary" onClick={onReset}><RotateCcw aria-hidden size={16} /> إعادة ضبط</Button>{selectedStudent && <button type="button" onClick={() => setSelectedStudent(null)} className="rounded-xl bg-blue-50 px-3 text-xs font-bold text-blue-800">{selectedStudent.full_name} ×</button>}</div>
    </section>
  );
}

function AbsenceReport({ schoolId, filters, onPage, schoolType }: ReportProps) {
  const [absenceType, setAbsenceType] = useState("ALL");
  const [excuseType, setExcuseType] = useState("ALL");
  const report = useQuery({ queryKey: schoolScopedKey(schoolId, "reports", "absence", filters, absenceType, excuseType), queryFn: ({ signal }) => getAbsenceReport(filters, { absenceType, excuseType }, signal), enabled: schoolId > 0 });
  return <ReportFrame controls={<><Select label="نوع الغياب" value={absenceType} onChange={(value) => { setAbsenceType(value); onPage(1); }} options={[["ALL", "الكل"], ["FULL", "يوم كامل"], ["PARTIAL", "جزئي"]]} /><Select label="حالة العذر" value={excuseType} onChange={(value) => { setExcuseType(value); onPage(1); }} options={[["ALL", "الكل"], ["UNEXCUSED", "دون عذر"], ["EXCUSED", "بعذر فقط"], ["MIXED", "مختلط"]]} /></>} query={report} summary={report.data && <div className="grid grid-cols-2 gap-2 sm:grid-cols-4"><MetricCard label={studentPluralLabel(schoolType)} value={report.data.summary.students} /><MetricCard label="أيام غياب كامل" value={report.data.summary.full_absence_days} tone="red" /><MetricCard label="أيام غياب جزئي" value={report.data.summary.partial_absence_days} tone="amber" /><MetricCard label="حصص دون عذر" value={report.data.summary.unexcused_absent_periods} tone="red" /></div>} table={report.data && <AbsenceTable rows={report.data.results} />} footer={report.data && <Pagination page={report.data.page} totalPages={Math.max(Math.ceil(report.data.count / report.data.page_size), 1)} onChange={onPage} />} />;
}

function LatenessReport({ schoolId, filters, onPage, schoolType }: ReportProps) {
  const [minOccurrences, setMinOccurrences] = useState(0);
  const [minMinutes, setMinMinutes] = useState(0);
  const report = useQuery({ queryKey: schoolScopedKey(schoolId, "reports", "lateness", filters, minOccurrences, minMinutes), queryFn: ({ signal }) => getLatenessReport(filters, { minOccurrences, minMinutes }, signal), enabled: schoolId > 0 });
  return <ReportFrame controls={<><NumberFilter label="الحد الأدنى للمرات" value={minOccurrences} onChange={setMinOccurrences} /><NumberFilter label="الحد الأدنى للدقائق" value={minMinutes} onChange={setMinMinutes} /></>} query={report} summary={report.data && <div className="grid grid-cols-2 gap-2 sm:grid-cols-3"><MetricCard label={studentCountLabel(schoolType)} value={report.data.summary.students} /><MetricCard label="مرات التأخر الصباحي" value={report.data.summary.morning_occurrences} tone="amber" /><MetricCard label="دقائق التأخر الصباحي" value={report.data.summary.morning_minutes} /></div>} table={report.data && <LatenessTable rows={report.data.results} />} footer={report.data && <Pagination page={report.data.page} totalPages={Math.max(Math.ceil(report.data.count / report.data.page_size), 1)} onChange={onPage} />} />;
}

function ReferralsReport({ schoolId, filters, onPage, schoolType }: ReportProps) {
  const [status, setStatus] = useState(""); const [category, setCategory] = useState(""); const [reason, setReason] = useState(""); const [source, setSource] = useState(""); const [counselor, setCounselor] = useState(""); const [priority, setPriority] = useState("");
  const options = useQuery({ queryKey: schoolScopedKey(schoolId, "referral-options"), queryFn: ({ signal }) => getReferralOptions(signal), enabled: schoolId > 0 });
  const counselors = useQuery({ queryKey: schoolScopedKey(schoolId, "referral-counselors"), queryFn: ({ signal }) => getCounselors(signal), enabled: schoolId > 0 });
  const reasons = options.data?.categories.find((item) => item.value === category)?.reasons ?? [];
  const extra = { status, category, reason_code: reason, source_type: source, counselor, priority };
  const report = useQuery({ queryKey: schoolScopedKey(schoolId, "reports", "referrals", filters, extra), queryFn: ({ signal }) => getReferralsReport(filters, extra, signal), enabled: schoolId > 0 });
  return <ReportFrame controls={<><Select label="الحالة" value={status} onChange={setStatus} options={[["", "الكل"], ["OPEN", "المفتوحة"], ["NEW", "جديدة"], ["ACKNOWLEDGED", "تم الاستلام"], ["CLOSED", "مغلقة"], ["CANCELLED", "ملغاة"]]} /><Select label="الأولوية" value={priority} onChange={setPriority} options={[["", "الكل"], ["HIGH", "عاجلة"], ["NORMAL", "عادية"]]} /><Select label="الفئة" value={category} onChange={(value) => { setCategory(value); setReason(""); }} options={[["", "الكل"], ...(options.data?.categories.map((item) => [item.value, item.label] as [string, string]) ?? [])]} /><Select label="السبب" value={reason} onChange={setReason} options={[["", "الكل"], ...reasons.map((item) => [item.value, item.label] as [string, string])]} /><Select label="المُحيل" value={source} onChange={setSource} options={[["", "الكل"], ["TEACHER", roleLabel("TEACHER", schoolType)], ["VICE_PRINCIPAL", roleLabel("VICE_PRINCIPAL", schoolType)], ["SCHOOL_MANAGER", roleLabel("SCHOOL_MANAGER", schoolType)]]} /><Select label="المرشد" value={counselor} onChange={setCounselor} options={[["", "الكل"], ["UNASSIGNED", "غير معيّنة"], ...(counselors.data?.counselors.map((item) => [String(item.id), item.name] as [string, string]) ?? [])]} /></>} query={report} summary={report.data && <div className="grid grid-cols-2 gap-2 sm:grid-cols-4"><MetricCard label="إجمالي الإحالات" value={report.data.summary.total} /><MetricCard label="جديدة" value={report.data.summary.new} tone="blue" /><MetricCard label="غير معيّنة" value={report.data.summary.unassigned} tone="amber" /><MetricCard label="عاجلة" value={report.data.summary.high_priority} tone="red" /></div>} table={report.data && <ReferralsTable rows={report.data.results} />} footer={report.data && <Pagination page={report.data.page} totalPages={Math.max(Math.ceil(report.data.count / report.data.page_size), 1)} onChange={onPage} />} />;
}

interface ReportProps { schoolId: number; filters: CommonReportFilters; onPage: (page: number) => void; schoolType: "BOYS" | "GIRLS"; }

function ReportFrame({ controls, query, summary, table, footer }: { controls: React.ReactNode; query: { isPending: boolean; isError: boolean; error: unknown }; summary?: React.ReactNode; table?: React.ReactNode; footer?: React.ReactNode }) { return <div className="space-y-4"><section className="flex flex-wrap gap-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm print:hidden">{controls}</section>{query.isPending && <Spinner label="جارٍ إعداد التقرير..." />}{query.isError && <ErrorState error={query.error} />}{summary}{table}{footer}</div>; }
function Select({ label, value, onChange, options }: { label: string; value: string; onChange: (value: string) => void; options: [string, string][] }) { return <SelectField label={label} value={value} onChange={(event) => onChange(event.target.value)} className="min-w-40">{options.map(([option, text]) => <option key={option} value={option}>{text}</option>)}</SelectField>; }
function NumberFilter({ label, value, onChange }: { label: string; value: number; onChange: (value: number) => void }) { return <TextField label={label} type="number" min={0} value={value} onChange={(event) => onChange(Math.max(Number(event.target.value), 0))} className="min-w-40" />; }
function TableShell({ children, empty }: { children: React.ReactNode; empty: boolean }) { return <DataTableShell>{empty ? <EmptyState title="لا توجد نتائج" description="غيّر الفلاتر أو الفترة ثم أعد المحاولة." compact /> : <table className="w-full min-w-[760px] text-sm">{children}</table>}</DataTableShell>; }
function AbsenceTable({ rows }: { rows: AbsenceRow[] }) { return <TableShell empty={rows.length === 0}><thead><tr className="border-b bg-slate-50 text-slate-500"><Th>الطالب</Th><Th>الصف/الفصل</Th><Th>كامل</Th><Th>جزئي</Th><Th>حصص غياب</Th><Th>بعذر</Th><Th>دون عذر</Th><Th /></tr></thead><tbody>{rows.map((row) => <tr key={`${row.student_id}-${row.section_name}`} className="border-b last:border-0"><Td strong>{row.full_name}</Td><Td>{row.grade_name} / {row.section_name}</Td><Td>{row.full_absence_days}</Td><Td>{row.partial_absence_days}</Td><Td>{row.absent_periods}</Td><Td>{row.excused_absent_periods}</Td><Td>{row.unexcused_absent_periods}</Td><Td><Link to={`/students/${row.student_id}/attendance`} className="font-bold text-blue-700">التفاصيل</Link></Td></tr>)}</tbody></TableShell>; }
function LatenessTable({ rows }: { rows: LatenessRow[] }) { return <TableShell empty={rows.length === 0}><thead><tr className="border-b bg-slate-50 text-slate-500"><Th>الطالب</Th><Th>الصف/الفصل</Th><Th>مرات التأخر الصباحي</Th><Th>الدقائق المحتسبة</Th><Th /></tr></thead><tbody>{rows.map((row) => <tr key={row.student_id} className="border-b last:border-0"><Td strong>{row.full_name}</Td><Td>{row.grade_name ?? "—"} / {row.section_name ?? "—"}</Td><Td>{row.morning_occurrences}</Td><Td>{row.morning_minutes}</Td><Td><Link to={`/students/${row.student_id}/attendance`} className="font-bold text-blue-700">التفاصيل</Link></Td></tr>)}</tbody></TableShell>; }
function ReferralsTable({ rows }: { rows: ReferralRow[] }) { return <TableShell empty={rows.length === 0}><thead><tr className="border-b bg-slate-50 text-slate-500"><Th>الطالب</Th><Th>الفئة/السبب</Th><Th>المُحيل</Th><Th>المرشد</Th><Th>الأولوية</Th><Th>الحالة</Th><Th>التاريخ</Th></tr></thead><tbody>{rows.map((row) => <tr key={row.id} className="border-b last:border-0"><Td strong>{row.student.full_name}</Td><Td>{row.category_label}<span className="block text-xs text-slate-500">{row.reason_label}</span></Td><Td>{row.created_by_name ?? "—"}</Td><Td>{row.assigned_counselor_name ?? "غير معيّن"}</Td><Td><Badge tone={row.priority === "HIGH" ? "danger" : "neutral"}>{row.priority_label}</Badge></Td><Td><Badge tone={row.status === "CLOSED" ? "success" : row.status === "CANCELLED" ? "danger" : "brand"} dot>{row.status_label}</Badge></Td><Td>{new Date(row.created_at).toLocaleDateString("ar-SA")}</Td></tr>)}</tbody></TableShell>; }
function Th({ children }: { children?: React.ReactNode }) { return <th className="p-3 text-start font-bold">{children}</th>; }
function Td({ children, strong = false }: { children: React.ReactNode; strong?: boolean }) { return <td className={`p-3 ${strong ? "font-black text-slate-900" : "text-slate-700"}`}>{children}</td>; }
