import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { ErrorState } from "@/components/ErrorState";
import { Spinner } from "@/components/Spinner";
import { schoolScopedKey, useMe } from "@/features/auth/useMe";
import { useActiveSchoolId } from "@/features/settings/hooks";
import {
  getAttendanceChanges,
  getAttendanceDayDetail,
  getAttendanceDays,
  getAttendancePeriodAbsences,
  getAttendancePeriodLates,
  getAttendanceProfile,
} from "@/features/students/api";

const DAY_LABELS: Record<string, string> = {
  FULL: "غياب يوم كامل",
  PARTIAL: "غياب جزئي",
  NONE: "لا يوجد غياب",
  UNDETERMINED: "بيانات غير مكتملة",
};
const MARK_LABELS: Record<string, string> = {
  ABSENT: "غائب",
  LATE: "متأخر",
  PRESENT: "حاضر",
  NOT_RECORDED: "لم يتم تسجيل الحضور",
};
const STATUS_LABELS: Record<string, string> = {
  ACTIVE: "نشط",
  GRADUATED: "متخرج",
  TRANSFERRED: "منقول",
  WITHDRAWN: "منسحب",
  INACTIVE: "غير نشط",
  ARCHIVED: "مؤرشف",
};

type Tab = "summary" | "days" | "absences" | "lates" | "changes";

function isoDate(date: Date) {
  return date.toISOString().slice(0, 10);
}

function formatMinutes(minutes: number) {
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  if (hours === 0) return `${rest} دقيقة`;
  if (rest === 0) return `${hours} ساعة`;
  return `${hours} ساعة و${rest} دقيقة`;
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("ar-SA", { dateStyle: "medium" }).format(
    new Date(`${value}T12:00:00`),
  );
}

export function StudentAttendanceProfilePage() {
  const { studentId } = useParams<{ studentId: string }>();
  const schoolId = useActiveSchoolId();
  const me = useMe();
  const id = Number(studentId);
  const today = isoDate(new Date());
  const [fromDate, setFromDate] = useState(today);
  const [toDate, setToDate] = useState(today);
  const [tab, setTab] = useState<Tab>("summary");
  const [page, setPage] = useState(1);
  const [selectedDay, setSelectedDay] = useState<string | null>(null);
  const canSeeChanges = me.data?.roles.some(
    (role) => role === "SCHOOL_MANAGER" || role === "VICE_PRINCIPAL",
  ) ?? false;
  const range = { fromDate, toDate };

  const profile = useQuery({
    queryKey: schoolScopedKey(schoolId, "student-profile-summary", id, fromDate, toDate),
    queryFn: ({ signal }) => getAttendanceProfile(id, range, signal),
    enabled: schoolId > 0 && Number.isInteger(id),
  });
  const days = useQuery({
    queryKey: schoolScopedKey(schoolId, "student-attendance-days", id, fromDate, toDate, page),
    queryFn: ({ signal }) => getAttendanceDays(id, { ...range, page }, signal),
    enabled: tab === "days" && schoolId > 0 && Number.isInteger(id),
  });
  const dayDetail = useQuery({
    queryKey: schoolScopedKey(schoolId, "student-attendance-day", id, selectedDay),
    queryFn: ({ signal }) => getAttendanceDayDetail(id, selectedDay!, signal),
    enabled: tab === "days" && selectedDay !== null,
  });
  const absences = useQuery({
    queryKey: schoolScopedKey(schoolId, "student-period-absences", id, fromDate, toDate, page),
    queryFn: ({ signal }) => getAttendancePeriodAbsences(id, { ...range, page }, signal),
    enabled: tab === "absences" && schoolId > 0,
  });
  const lates = useQuery({
    queryKey: schoolScopedKey(schoolId, "student-period-lates", id, fromDate, toDate, page),
    queryFn: ({ signal }) => getAttendancePeriodLates(id, { ...range, page }, signal),
    enabled: tab === "lates" && schoolId > 0,
  });
  const changes = useQuery({
    queryKey: schoolScopedKey(schoolId, "student-attendance-changes", id, fromDate, toDate, page),
    queryFn: ({ signal }) => getAttendanceChanges(id, { ...range, page }, signal),
    enabled: tab === "changes" && canSeeChanges && schoolId > 0,
  });

  const setPreset = (preset: string) => {
    const end = new Date();
    const start = new Date(end);
    if (preset === "today") {
      setFromDate(isoDate(end));
      setToDate(isoDate(end));
    } else if (preset === "week") {
      start.setDate(end.getDate() - 6);
      setFromDate(isoDate(start));
      setToDate(isoDate(end));
    } else if (preset === "month") {
      start.setDate(1);
      setFromDate(isoDate(start));
      setToDate(isoDate(end));
    }
  };

  if (profile.isPending) return <Spinner />;
  if (profile.isError) return <ErrorState error={profile.error} />;
  if (!profile.data) return null;

  const { student, attendance } = profile.data;
  const tabs: Array<[Tab, string]> = [
    ["summary", "الملخص"],
    ["days", "سجل الأيام"],
    ["absences", "غياب الحصص"],
    ["lates", "تأخر الحصص"],
    ...(canSeeChanges ? [["changes", "سجل التعديلات"] as [Tab, string]] : []),
  ];

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <Link to="/students" className="text-sm text-blue-700 underline">العودة إلى الطلاب</Link>
          <h1 className="mt-2 text-2xl font-bold">{student.full_name}</h1>
          <p className="text-sm text-slate-600">
            {student.grade?.name ?? "لا يوجد صف حالي"} / {student.section?.name ?? "لا يوجد فصل حالي"}
            <span className="mx-2">•</span>{STATUS_LABELS[student.status] ?? student.status}
            <span className="mx-2">•</span><span dir="ltr">{student.national_id_masked}</span>
          </p>
        </div>
        <div className="text-sm text-slate-600">رقم الطالب: {student.student_number ?? "غير متوفر"}</div>
      </div>

      <div className="flex flex-wrap items-end gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <label className="flex flex-col gap-1 text-sm">الفترة
          <select onChange={(event) => setPreset(event.target.value)} defaultValue="today" className="rounded-lg border border-slate-300 px-3 py-2">
            <option value="today">اليوم</option>
            <option value="week">آخر 7 أيام</option>
            <option value="month">هذا الشهر</option>
            <option value="custom">فترة مخصصة</option>
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm">من
          <input type="date" value={fromDate} onChange={(event) => setFromDate(event.target.value)} className="rounded-lg border border-slate-300 px-3 py-2" />
        </label>
        <label className="flex flex-col gap-1 text-sm">إلى
          <input type="date" value={toDate} onChange={(event) => setToDate(event.target.value)} className="rounded-lg border border-slate-300 px-3 py-2" />
        </label>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <Metric label="غياب كامل" value={`${attendance.full_absence_days} يوم`} />
        <Metric label="غياب جزئي" value={`${attendance.partial_absence_days} يوم`} />
        <Metric label="حصص غياب" value={`${attendance.absent_periods} حصة`} />
        <Metric label="تأخر عن الحصص" value={`${attendance.period_late_occurrences} مرة`} />
        <Metric label="إجمالي التأخر" value={formatMinutes(attendance.period_late_minutes)} />
      </div>
      {attendance.undetermined_days > 0 && (
        <div role="status" className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
          يوجد {attendance.undetermined_days} يومًا لم تكتمل فيها بيانات التحضير.
        </div>
      )}
      <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm text-slate-600">
        التأخر الصباحي: بيانات الحضور الصباحي ستتوفر بعد تفعيل أجهزة الحضور.
      </div>

      <div className="flex flex-wrap gap-2 border-b border-slate-200">
        {tabs.map(([value, label]) => <button key={value} type="button" onClick={() => setTab(value)} className={`border-b-2 px-3 py-2 text-sm ${tab === value ? "border-blue-700 text-blue-700" : "border-transparent text-slate-600"}`}>{label}</button>)}
      </div>

      {tab === "summary" && <p className="text-sm text-slate-500">الفترة: {formatDate(fromDate)} إلى {formatDate(toDate)}</p>}
      {tab === "days" && <DaysTab days={days.data?.results ?? []} count={days.data?.count ?? 0} page={page} onPage={setPage} selectedDay={selectedDay} onSelect={setSelectedDay} detail={dayDetail.data} />}
      {tab === "absences" && <PeriodTab rows={absences.data?.results ?? []} count={absences.data?.count ?? 0} page={page} onPage={setPage} empty="لا توجد حصص غياب في الفترة." />}
      {tab === "lates" && <PeriodTab rows={lates.data?.results ?? []} count={lates.data?.count ?? 0} page={page} onPage={setPage} empty="لا توجد حالات تأخر عن الحصص في الفترة." showLate />}
      {tab === "changes" && <ChangesTab rows={changes.data?.results ?? []} count={changes.data?.count ?? 0} page={page} onPage={setPage} />}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"><p className="text-xs text-slate-500">{label}</p><strong className="mt-2 block text-xl text-slate-900">{value}</strong></div>;
}

function DaysTab({ days, count, page, onPage, selectedDay, onSelect, detail }: {
  days: Awaited<ReturnType<typeof getAttendanceDays>>["results"];
  count: number;
  page: number;
  onPage: (page: number) => void;
  selectedDay: string | null;
  onSelect: (date: string) => void;
  detail?: Awaited<ReturnType<typeof getAttendanceDayDetail>>;
}) {
  return <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]"><div className="divide-y rounded-xl border border-slate-200 bg-white">{days.map((day) => <button key={day.date} type="button" onClick={() => onSelect(day.date)} className={`flex w-full items-center justify-between p-4 text-start ${selectedDay === day.date ? "bg-blue-50" : "hover:bg-slate-50"}`}><span><strong>{formatDate(day.date)}</strong><span className="mt-1 block text-sm text-slate-600">{DAY_LABELS[day.absence_status]}</span></span><span className="text-sm text-slate-500">{day.absent_periods} غياب • {day.late_periods} تأخر</span></button>)}{days.length === 0 && <p className="p-6 text-sm text-slate-500">لا توجد بيانات أيام في الفترة.</p>}<Pager count={count} page={page} onPage={onPage} /></div>{detail && <div className="rounded-xl border border-slate-200 bg-white p-4"><h2 className="mb-3 font-bold">تفاصيل {formatDate(detail.date)}</h2><div className="divide-y">{detail.periods.map((period) => <div key={period.sequence} className="flex items-center justify-between py-3 text-sm"><span>الحصة {period.sequence} - {period.name}</span><span>{MARK_LABELS[period.status]}{period.late_minutes ? ` (${period.late_minutes} دقيقة)` : ""}</span></div>)}</div></div>}</div>;
}

function PeriodTab({ rows, count, page, onPage, empty, showLate = false }: { rows: Awaited<ReturnType<typeof getAttendancePeriodAbsences>>["results"]; count: number; page: number; onPage: (page: number) => void; empty: string; showLate?: boolean }) {
  return <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white"><table className="w-full text-sm"><thead><tr className="border-b text-slate-500"><th className="p-3 text-start">التاريخ</th><th className="p-3 text-start">الحصة</th><th className="p-3 text-start">الصف/الفصل</th>{showLate && <th className="p-3 text-start">الوصول / الدقائق</th>}</tr></thead><tbody>{rows.map((row) => <tr key={`${row.date}-${row.sequence}`} className="border-b"><td className="p-3">{formatDate(row.date)}</td><td className="p-3">{row.period.name}</td><td className="p-3">{row.section.grade_name} / {row.section.name}</td>{showLate && <td className="p-3">{row.arrival_time ?? "-"} / {row.late_minutes ?? 0} دقيقة</td>}</tr>)}</tbody></table>{rows.length === 0 && <p className="p-6 text-sm text-slate-500">{empty}</p>}<Pager count={count} page={page} onPage={onPage} /></div>;
}

function ChangesTab({ rows, count, page, onPage }: { rows: Awaited<ReturnType<typeof getAttendanceChanges>>["results"]; count: number; page: number; onPage: (page: number) => void }) {
  return <div className="divide-y rounded-xl border border-slate-200 bg-white">{rows.map((row) => <div key={`${row.date}-${row.sequence}-${row.changed_at}`} className="p-4 text-sm"><strong>{formatDate(row.date)} - {row.period.name}</strong><p className="mt-1 text-slate-700">{row.previous_status_label} ← {row.new_status_label}{row.reason ? ` - السبب: ${row.reason}` : ""}</p><p className="text-slate-500">بواسطة: {row.actor ?? "غير معروف"} • {new Date(row.changed_at).toLocaleTimeString("ar-SA", { hour: "2-digit", minute: "2-digit" })}</p></div>)}{rows.length === 0 && <p className="p-6 text-sm text-slate-500">لا توجد تعديلات في الفترة.</p>}<Pager count={count} page={page} onPage={onPage} /></div>;
}

function Pager({ count, page, onPage }: { count: number; page: number; onPage: (page: number) => void }) {
  const totalPages = Math.max(1, Math.ceil(count / 25));
  return <div className="flex items-center justify-between border-t border-slate-100 p-3 text-sm"><span className="text-slate-500">صفحة {page} من {totalPages}</span><div className="flex gap-2"><button type="button" disabled={page <= 1} onClick={() => onPage(page - 1)} className="rounded border px-3 py-1 disabled:opacity-40">السابق</button><button type="button" disabled={page >= totalPages} onClick={() => onPage(page + 1)} className="rounded border px-3 py-1 disabled:opacity-40">التالي</button></div></div>;
}
