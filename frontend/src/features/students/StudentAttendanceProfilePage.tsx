import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, CheckCircle2, CircleAlert, Clock3, GraduationCap, XCircle } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { Button } from "@/components/Button";
import { ErrorState } from "@/components/ErrorState";
import { PageHeader } from "@/components/PageHeader";
import { Spinner } from "@/components/Spinner";
import { schoolScopedKey, useMe } from "@/features/auth/useMe";
import { getExcuses } from "@/features/excuses/api";
import { ExcuseCreateCard } from "@/features/excuses/ExcuseCreateCard";
import { ExcuseDetailCard } from "@/features/excuses/ExcuseDetailCard";
import { StatusBadge } from "@/features/excuses/ExcusesPage";
import { useActiveSchoolId } from "@/features/settings/hooks";
import { StudentCounselingTab } from "@/features/counseling/StudentCounselingTab";
import { StudentActionsTab } from "@/features/documents/StudentActionsTab";
import { StudentDocumentsTab } from "@/features/documents/StudentDocumentsTab";
import { StudentLeavesTab } from "@/features/leaves/StudentLeavesTab";
import { StudentReferralsTab } from "@/features/referrals/StudentReferralsTab";
import { StudentWarningsTab } from "@/features/warnings/StudentWarningsTab";
import {
  correctStudentAttendance,
  getAttendanceChanges,
  getAttendanceDayDetail,
  getAttendanceDays,
  getAttendancePeriodAbsences,
  getAttendanceProfile,
  getMorningAttendance,
} from "@/features/students/api";
import { localIsoDate } from "@/utils/dates";
import { studentLabel, studentPluralLabel } from "@/utils/roles";
import type { SchoolType } from "@/types/auth";

const DAY_LABELS: Record<string, string> = {
  FULL: "غائب يومًا كاملًا",
  PARTIAL: "حاضر — لديه غياب جزئي",
  NONE: "حاضر",
  UNDETERMINED: "لم يعتمد تحضير",
};
const MARK_LABELS: Record<string, string> = {
  ABSENT: "غائب",
  PRESENT: "حاضر",
  NOT_RECORDED: "لم يعتمد تحضير الحصة",
};
const STATUS_LABELS: Record<string, string> = {
  ACTIVE: "نشط",
  GRADUATED: "متخرج",
  TRANSFERRED: "منقول",
  WITHDRAWN: "منسحب",
  INACTIVE: "غير نشط",
  ARCHIVED: "مؤرشف",
};

type Tab =
  | "summary"
  | "days"
  | "absences"
  | "leaves"
  | "morning"
  | "excuses"
  | "warnings"
  | "actions"
  | "documents"
  | "referrals"
  | "counseling"
  | "changes";

const isoDate = localIsoDate;

function formatMinutes(minutes: number) {
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  if (hours === 0) return `${rest} دقيقة`;
  if (rest === 0) return `${hours} ساعة`;
  return `${hours} ساعة و${rest} دقيقة`;
}

function formatOccurrences(count: number) {
  if (count === 1) return "مرة واحدة";
  if (count === 2) return "مرتين";
  return `${count} مرات`;
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
  const schoolType = me.data?.active_school?.school_type ?? "BOYS";
  const studentLabelText = studentLabel(schoolType, true);
  const id = Number(studentId);
  const today = isoDate(new Date());
  const [fromDate, setFromDate] = useState(today);
  const [toDate, setToDate] = useState(today);
  const [preset, setPresetValue] = useState("today");
  const [tab, setTab] = useState<Tab>("summary");
  const [page, setPage] = useState(1);
  const [selectedDay, setSelectedDay] = useState<string | null>(null);
  const [selectedExcuse, setSelectedExcuse] = useState<number | null>(null);
  const [quickExcuse, setQuickExcuse] = useState<{ date?: string; period?: number } | null>(
    null,
  );
  const canSeeChanges = me.data?.roles.some(
    (role) => role === "SCHOOL_MANAGER" || role === "VICE_PRINCIPAL",
  ) ?? false;
  const canManageExcuses = canSeeChanges;
  const canSeeLeaves = canSeeChanges;
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
  const detailDay = selectedDay ?? (tab === "days" ? days.data?.results[0]?.date ?? null : null);
  const dayDetail = useQuery({
    queryKey: schoolScopedKey(schoolId, "student-attendance-day", id, detailDay),
    queryFn: ({ signal }) => getAttendanceDayDetail(id, detailDay!, signal),
    enabled: tab === "days" && detailDay !== null,
  });
  const singleDay = fromDate === toDate ? fromDate : null;
  const singleDayMatchesProfile = singleDay !== null
    && profile.data?.period.from === singleDay
    && profile.data?.period.to === singleDay;
  const singleDayDetail = useQuery({
    queryKey: schoolScopedKey(schoolId, "student-attendance-day", id, singleDay),
    queryFn: ({ signal }) => getAttendanceDayDetail(id, singleDay!, signal),
    enabled:
      tab === "summary"
      && singleDayMatchesProfile
      && schoolId > 0
      && Number.isInteger(id),
  });
  const absences = useQuery({
    queryKey: schoolScopedKey(schoolId, "student-period-absences", id, fromDate, toDate, page),
    queryFn: ({ signal }) => getAttendancePeriodAbsences(id, { ...range, page }, signal),
    enabled: tab === "absences" && schoolId > 0,
  });
  const changes = useQuery({
    queryKey: schoolScopedKey(schoolId, "student-attendance-changes", id, fromDate, toDate, page),
    queryFn: ({ signal }) => getAttendanceChanges(id, { ...range, page }, signal),
    enabled: tab === "changes" && canSeeChanges && schoolId > 0,
  });
  const morning = useQuery({
    queryKey: schoolScopedKey(schoolId, "student-morning-attendance", id, fromDate, toDate),
    queryFn: ({ signal }) => getMorningAttendance(id, range, signal),
    enabled: tab === "morning" && schoolId > 0,
  });
  const excuses = useQuery({
    queryKey: schoolScopedKey(schoolId, "student-excuses", id, page),
    queryFn: ({ signal }) => getExcuses({ student: id, page }, signal),
    enabled: tab === "excuses" && schoolId > 0,
  });

  const setPreset = (preset: string) => {
    setPresetValue(preset);
    setPage(1);
    setSelectedDay(null);
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

  const updateFromDate = (value: string) => {
    setPresetValue("custom");
    setFromDate(value);
    if (value > toDate) setToDate(value);
    setPage(1);
    setSelectedDay(null);
  };

  const updateToDate = (value: string) => {
    setPresetValue("custom");
    setToDate(value);
    if (value < fromDate) setFromDate(value);
    setPage(1);
    setSelectedDay(null);
  };

  const showTab = (value: Tab) => {
    setTab(value);
    setPage(1);
    if (value !== "days") setSelectedDay(null);
  };

  if (profile.isPending) return <Spinner />;
  if (profile.isError) return <ErrorState error={profile.error} />;
  if (!profile.data) return null;

  const { student, attendance } = profile.data;
  const tabs: Array<[Tab, string]> = [
    ["summary", "الملخص"],
    ["days", "سجل الأيام"],
    ["absences", "غياب الحصص"],
    ["morning", "الحضور الصباحي"],
    ...(canSeeLeaves ? [["leaves", "الاستئذانات"] as [Tab, string]] : []),
    ["excuses", "الأعذار"],
    ["warnings", "الإنذارات"],
    ["actions", "الإجراءات"],
    ["documents", "المستندات"],
    ["referrals", "الإحالات"],
    ["counseling", "الإرشاد والمتابعة"],
    ...(canSeeChanges ? [["changes", "سجل التعديلات"] as [Tab, string]] : []),
  ];

  return (
    <div className="ds-page">
      <PageHeader
        icon={GraduationCap}
        eyebrow={`ملف ${studentLabelText} الموحد`}
        title={student.full_name}
        description={`${student.grade?.name ?? "لا يوجد صف حالي"} / ${student.section?.name ?? "لا يوجد فصل حالي"}`}
        tone="executive"
        badge={STATUS_LABELS[student.status] ?? student.status}
        meta={(
          <>
            <span>رقم {studentLabelText}: {student.student_number ?? "غير متوفر"}</span>
            <span className="text-white/30">•</span>
            <span>الهوية: <bdi>{student.national_id_masked}</bdi></span>
          </>
        )}
        actions={(
          <Link
            to="/students"
            className="inline-flex min-h-11 items-center gap-2 rounded-xl bg-white/10 px-4 text-sm font-bold text-white ring-1 ring-white/15 transition hover:bg-white/15 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white"
          >
            <ArrowRight aria-hidden size={17} />
            العودة إلى {studentPluralLabel(schoolType)}
          </Link>
        )}
        testId="student-profile-header"
      />

      <section aria-label="تحديد فترة الملف" className="grid gap-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:grid-cols-3">
        <label className="flex min-w-0 flex-col gap-1 text-sm font-bold text-slate-700">الفترة
          <select onChange={(event) => setPreset(event.target.value)} value={preset} className="min-h-11 w-full rounded-xl border border-slate-300 bg-white px-3 py-2 font-normal">
            <option value="today">اليوم</option>
            <option value="week">آخر 7 أيام</option>
            <option value="month">هذا الشهر</option>
            <option value="custom">فترة مخصصة</option>
          </select>
        </label>
        <label className="flex min-w-0 flex-col gap-1 text-sm font-bold text-slate-700">من
          <input type="date" value={fromDate} onChange={(event) => updateFromDate(event.target.value)} className="min-h-11 w-full rounded-xl border border-slate-300 px-3 py-2 font-normal" />
        </label>
        <label className="flex min-w-0 flex-col gap-1 text-sm font-bold text-slate-700">إلى
          <input type="date" value={toDate} onChange={(event) => updateToDate(event.target.value)} className="min-h-11 w-full rounded-xl border border-slate-300 px-3 py-2 font-normal" />
        </label>
      </section>

      <div className="rounded-2xl border border-emerald-200 bg-emerald-50/70 px-4 py-3 text-sm leading-6 text-emerald-950">
        <strong className="block">قاعدة احتساب الحضور</strong>
        حضور الطالب في أي تحضير معتمد يجعله حاضرًا في ذلك اليوم، حتى لو غاب عن حصة أخرى.
        ولا يُحسب غائبًا يومًا كاملًا إلا إذا غاب عن جميع التحاضير المعتمدة.
      </div>

      {singleDay && singleDayMatchesProfile && tab === "summary" && (
        <SingleDayOverview
          date={singleDay}
          detail={singleDayDetail.data}
          isPending={singleDayDetail.isPending}
          error={singleDayDetail.error}
          canManageExcuses={canManageExcuses}
          onQuickExcuse={(date, period) => {
            setQuickExcuse({ date, period });
            showTab("excuses");
          }}
        />
      )}

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4" aria-label="ملخص الحضور خلال الفترة">
        <Metric label="أيام الحضور" hint="يشمل الغياب الجزئي" value={`${attendance.present_days} يوم`} tone="green" />
        <Metric label="غياب يوم كامل" value={`${attendance.full_absence_days} يوم`} tone="red" />
        <Metric label="غياب جزئي" hint="محسوب ضمن الحضور" value={`${attendance.partial_absence_days} يوم`} tone="amber" />
        <Metric label="إجمالي حصص الغياب" value={`${attendance.absent_periods} حصة`} />
      </div>

      {/* م10 — التصنيف الإداري: إضافة فوق الإجماليات لا بديل عنها (بند 69) */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4" data-testid="excuse-metrics">
        <Metric
          label="غياب كامل بعذر"
          value={`${attendance.excused_full_absence_days} يوم`}
        />
        <Metric
          label="غياب كامل بدون عذر"
          value={`${attendance.unexcused_full_absence_days} يوم`}
        />
        <Metric label="حصص غياب بعذر" value={`${attendance.excused_absent_periods} حصة`} />
        <Metric
          label="حصص غياب بدون عذر"
          value={`${attendance.unexcused_absent_periods} حصة`}
        />
      </div>
      {attendance.mixed_full_absence_days > 0 && (
        <div role="status" className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm text-slate-700">
          يوجد {attendance.mixed_full_absence_days} يوم غياب كامل مختلط (بعضه بعذر وبعضه بدون
          عذر).
        </div>
      )}
      {attendance.undetermined_days > 0 && (
        <div role="status" className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
          يوجد {attendance.undetermined_days} يومًا لم يعتمد فيها أي تحضير؛ لا تُحسب حضورًا ولا غيابًا.
        </div>
      )}
      {profile.data.morning_attendance.status === "AVAILABLE" ? (
        <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm text-slate-700">
          <strong className="block">التأخر عن الدوام الصباحي</strong>
          <span>{formatOccurrences(profile.data.morning_attendance.morning_late_occurrences ?? 0)}، </span>
          <span>{formatMinutes(profile.data.morning_attendance.morning_late_minutes ?? 0)}</span>
        </div>
      ) : (
        <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm text-slate-600">
          التأخر الصباحي: بيانات الحضور الصباحي غير متاحة.
        </div>
      )}

      <div className="flex snap-x snap-mandatory gap-1 overflow-x-auto rounded-2xl border border-slate-200 bg-white p-1.5 shadow-sm" role="group" aria-label={`أقسام ملف ${studentLabelText}`}>
        {tabs.map(([value, label]) => <button key={value} type="button" aria-pressed={tab === value} onClick={() => showTab(value)} className={`min-h-10 shrink-0 snap-start whitespace-nowrap rounded-xl px-3 py-2 text-sm font-bold transition ${tab === value ? "bg-slate-950 text-white shadow-sm" : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"}`}>{label}</button>)}
      </div>

      {tab === "summary" && <p className="text-sm text-slate-500">الفترة: {formatDate(fromDate)} إلى {formatDate(toDate)}</p>}
      {tab === "days" && (days.isPending ? <Spinner label="جارٍ تحميل سجل الأيام..." /> : days.isError ? <ErrorState error={days.error} /> : <DaysTab days={days.data?.results ?? []} count={days.data?.count ?? 0} page={page} onPage={setPage} selectedDay={detailDay} onSelect={setSelectedDay} detail={dayDetail.data} detailPending={dayDetail.isPending} detailError={dayDetail.error} canManageExcuses={canManageExcuses} onQuickExcuse={(date, period) => { setQuickExcuse({ date, period }); showTab("excuses"); }} />)}
      {tab === "absences" && (absences.isPending ? <Spinner label="جارٍ تحميل غياب الحصص..." /> : absences.isError ? <ErrorState error={absences.error} /> : <PeriodTab rows={absences.data?.results ?? []} count={absences.data?.count ?? 0} page={page} onPage={setPage} empty="لا توجد حصص غياب في الفترة." />)}
      {tab === "morning" && (morning.isPending ? <Spinner label="جارٍ تحميل الحضور الصباحي..." /> : morning.isError ? <ErrorState error={morning.error} /> : <MorningTab rows={morning.data ?? []} />)}
      {tab === "leaves" && canSeeLeaves && <StudentLeavesTab studentId={id} />}
      {tab === "warnings" && <StudentWarningsTab studentId={id} />}
      {tab === "actions" && <StudentActionsTab studentId={id} />}
      {tab === "documents" && <StudentDocumentsTab studentId={id} />}
      {tab === "referrals" && (
        <StudentReferralsTab studentId={id} studentName={student.full_name} />
      )}
      {tab === "counseling" && <StudentCounselingTab studentId={id} />}
      {tab === "excuses" && (
        <div className="space-y-4">
          {canManageExcuses && !quickExcuse && (
            <Button onClick={() => setQuickExcuse({})} data-testid="profile-add-excuse">
              إضافة عذر
            </Button>
          )}
          {quickExcuse && canManageExcuses && (
            <ExcuseCreateCard
              fixedStudent={{ id, name: student.full_name }}
              fixedDate={quickExcuse.date}
              fixedPeriod={quickExcuse.period}
              onCreated={(excuseId) => {
                setQuickExcuse(null);
                setSelectedExcuse(excuseId);
                excuses.refetch();
              }}
              onCancel={() => setQuickExcuse(null)}
            />
          )}
          <ExcusesTab
            rows={excuses.data?.results ?? []}
            schoolType={schoolType}
            onSelect={(excuseId) =>
              setSelectedExcuse(selectedExcuse === excuseId ? null : excuseId)
            }
          />
          {selectedExcuse !== null && (
            <ExcuseDetailCard
              excuseId={selectedExcuse}
              canManage={canManageExcuses}
              onChanged={() => {
                excuses.refetch();
                profile.refetch();
              }}
              onClose={() => setSelectedExcuse(null)}
            />
          )}
        </div>
      )}
      {tab === "changes" && (changes.isPending ? <Spinner label="جارٍ تحميل سجل التعديلات..." /> : changes.isError ? <ErrorState error={changes.error} /> : <ChangesTab rows={changes.data?.results ?? []} count={changes.data?.count ?? 0} page={page} onPage={setPage} />)}
    </div>
  );
}

function ExcusesTab({
  rows,
  schoolType,
  onSelect,
}: {
  rows: Awaited<ReturnType<typeof getExcuses>>["results"];
  schoolType: SchoolType;
  onSelect: (excuseId: number) => void;
}) {
  return (
    <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
      <table className="block w-full text-sm md:table">
        <thead className="hidden bg-slate-50 md:table-header-group">
          <tr className="border-b text-slate-500">
            <th className="p-3 text-start">التاريخ/الفترة</th>
            <th className="p-3 text-start">نوع العذر</th>
            <th className="p-3 text-start">الحالة</th>
            <th className="p-3 text-start">الحصص المغطاة</th>
            <th className="p-3 text-start">المسجل</th>
            <th className="p-3 text-start">المعتمد</th>
            <th className="p-3 text-start">المرفقات</th>
            <th className="p-3 text-start"></th>
          </tr>
        </thead>
        <tbody className="grid gap-3 p-3 md:table-row-group md:p-0" data-testid="profile-excuses-list">
          {rows.map((row) => (
            <tr key={row.id} className="grid grid-cols-2 gap-3 rounded-2xl border border-slate-200 p-4 md:table-row md:border-x-0 md:border-t-0 md:p-0" data-testid={`profile-excuse-${row.id}`}>
              <td className="col-span-2 p-0 md:table-cell md:p-3">
                <span className="mb-1 block text-xs font-bold text-slate-500 md:hidden">التاريخ والفترة</span>
                {row.date_from
                  ? row.date_from === row.date_to
                    ? formatDate(row.date_from)
                    : `${formatDate(row.date_from)} — ${formatDate(row.date_to!)}`
                  : "—"}
              </td>
              <td className="p-0 md:table-cell md:p-3"><span className="mb-1 block text-xs font-bold text-slate-500 md:hidden">نوع العذر</span>{row.reason_type_label}</td>
              <td className="p-0 md:table-cell md:p-3">
                <span className="mb-1 block text-xs font-bold text-slate-500 md:hidden">الحالة</span>
                <StatusBadge status={row.status} label={row.status_label} />
              </td>
              <td className="p-0 md:table-cell md:p-3"><span className="mb-1 block text-xs font-bold text-slate-500 md:hidden">الحصص المغطاة</span>{row.active_coverage_count} حصة</td>
              <td className="p-0 md:table-cell md:p-3"><span className="mb-1 block text-xs font-bold text-slate-500 md:hidden">المسجل</span>{row.recorded_by_name ?? "—"}</td>
              <td className="p-0 md:table-cell md:p-3"><span className="mb-1 block text-xs font-bold text-slate-500 md:hidden">المعتمد</span>{row.approved_by_name ?? "—"}</td>
              <td className="p-0 md:table-cell md:p-3"><span className="mb-1 block text-xs font-bold text-slate-500 md:hidden">المرفقات</span>{row.attachments_count}</td>
              <td className="col-span-2 p-0 md:table-cell md:p-3">
                <button
                  type="button"
                  className="inline-flex min-h-10 w-full items-center justify-center rounded-xl bg-blue-50 px-3 font-bold text-blue-700 transition hover:bg-blue-100 md:min-h-0 md:w-auto md:bg-transparent md:p-0 md:underline"
                  onClick={() => onSelect(row.id)}
                  data-testid={`open-profile-excuse-${row.id}`}
                >
                  التفاصيل
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length === 0 && (
        <p className="p-6 text-sm text-slate-500" data-testid="no-student-excuses">
          لا توجد أعذار مسجلة {schoolType === "GIRLS" ? "لهذه الطالبة" : "لهذا الطالب"}.
        </p>
      )}
    </div>
  );
}

function MorningTab({ rows }: { rows: Awaited<ReturnType<typeof getMorningAttendance>> }) {
  return <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm"><table className="block w-full text-sm md:table"><thead className="hidden bg-slate-50 md:table-header-group"><tr className="border-b text-slate-500"><th className="p-3 text-start">التاريخ</th><th className="p-3 text-start">وقت الدخول</th><th className="p-3 text-start">الحالة</th><th className="p-3 text-start">التأخر المحتسب</th><th className="p-3 text-start">المصدر</th></tr></thead><tbody className="grid gap-3 p-3 md:table-row-group md:p-0">{rows.map((row) => <tr key={row.date} className="grid grid-cols-2 gap-3 rounded-2xl border border-slate-200 p-4 md:table-row md:border-x-0 md:border-t-0 md:p-0"><td className="col-span-2 p-0 font-bold md:table-cell md:p-3 md:font-normal"><span className="mb-1 block text-xs font-bold text-slate-500 md:hidden">التاريخ</span>{formatDate(row.date)}</td><td className="p-0 md:table-cell md:p-3"><span className="mb-1 block text-xs font-bold text-slate-500 md:hidden">وقت الدخول</span>{new Date(row.arrival_time).toLocaleTimeString("ar-SA", { hour: "2-digit", minute: "2-digit" })}</td><td className="p-0 md:table-cell md:p-3"><span className="mb-1 block text-xs font-bold text-slate-500 md:hidden">الحالة</span>{row.status === "LATE" ? "متأخر" : "في الوقت"}</td><td className="p-0 md:table-cell md:p-3"><span className="mb-1 block text-xs font-bold text-slate-500 md:hidden">التأخر المحتسب</span>{row.counted_late_minutes} دقيقة</td><td className="p-0 md:table-cell md:p-3"><span className="mb-1 block text-xs font-bold text-slate-500 md:hidden">المصدر</span>{row.source === "BIOMETRIC" ? "جهاز" : "يدوي"}</td></tr>)}{rows.length === 0 && <tr className="block"><td colSpan={5} className="block p-6 text-center text-slate-500">لا توجد سجلات حضور صباحي في الفترة.</td></tr>}</tbody></table></div>;
}

function SingleDayOverview({ date, detail, isPending, error, canManageExcuses, onQuickExcuse }: {
  date: string;
  detail?: Awaited<ReturnType<typeof getAttendanceDayDetail>>;
  isPending: boolean;
  error: unknown;
  canManageExcuses: boolean;
  onQuickExcuse: (date: string, period?: number) => void;
}) {
  return (
    <section aria-labelledby="single-day-attendance-title" className="space-y-3">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <p className="text-xs font-bold text-emerald-700">النتيجة اليومية</p>
          <h2 id="single-day-attendance-title" className="text-lg font-black text-slate-950">
            حالة {formatDate(date)} والحصص المعتمدة
          </h2>
        </div>
        <span className="text-xs text-slate-500">الحصة غير المعتمدة لا تُحسب غيابًا</span>
      </div>
      {isPending ? <Spinner label="جارٍ تحميل تفاصيل اليوم..." /> : error ? <ErrorState error={error} /> : detail ? (
        <AttendanceDayOverview
          detail={detail}
          canManageExcuses={canManageExcuses}
          onQuickExcuse={onQuickExcuse}
        />
      ) : null}
    </section>
  );
}

function AttendanceDayOverview({ detail, canManageExcuses, onQuickExcuse }: {
  detail: Awaited<ReturnType<typeof getAttendanceDayDetail>>;
  canManageExcuses: boolean;
  onQuickExcuse: (date: string, period?: number) => void;
}) {
  const presentation = detail.absence_status === "FULL"
    ? {
        title: "غائب في هذا اليوم",
        description: "سُجل غائبًا في جميع التحاضير المعتمدة.",
        icon: <XCircle aria-hidden size={22} />,
        tone: "border-red-200 bg-red-50 text-red-950",
      }
    : detail.absence_status === "PARTIAL"
      ? {
          title: "حاضر في هذا اليوم — لديه غياب جزئي",
          description: "حضر في تحضير معتمد واحد على الأقل، لذلك يُحسب ضمن الحاضرين.",
          icon: <CircleAlert aria-hidden size={22} />,
          tone: "border-amber-200 bg-amber-50 text-amber-950",
        }
      : detail.absence_status === "NONE"
        ? {
            title: "حاضر في هذا اليوم",
            description: "لم يُسجل عليه غياب في أي تحضير معتمد.",
            icon: <CheckCircle2 aria-hidden size={22} />,
            tone: "border-emerald-200 bg-emerald-50 text-emerald-950",
          }
        : {
            title: "لم يعتمد تحضير لهذا اليوم",
            description: "لا توجد حقيقة حضور أو غياب معتمدة لهذا اليوم.",
            icon: <Clock3 aria-hidden size={22} />,
            tone: "border-slate-200 bg-slate-50 text-slate-800",
          };
  const expected = detail.expected_periods ?? detail.periods.length;
  const submitted = detail.submitted_periods ?? detail.periods.filter((period) => period.status !== "NOT_RECORDED").length;
  const present = detail.present_periods ?? detail.periods.filter((period) => period.status === "PRESENT").length;
  const absent = detail.absent_periods ?? detail.periods.filter((period) => period.status === "ABSENT").length;
  const notSubmitted = Math.max(expected - submitted, 0);

  return (
    <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm" data-testid="daily-attendance-overview">
      <div className={`flex flex-col justify-between gap-3 border-b p-4 sm:flex-row sm:items-center ${presentation.tone}`}>
        <div className="flex items-start gap-3">
          <span className="mt-0.5">{presentation.icon}</span>
          <div>
            <strong className="block text-base">{presentation.title}</strong>
            <span className="mt-0.5 block text-sm opacity-80">{presentation.description}</span>
          </div>
        </div>
        {canManageExcuses && absent > 0 && (
          <Button variant="secondary" onClick={() => onQuickExcuse(detail.date)} data-testid="day-add-excuse">
            إضافة عذر لغياب اليوم
          </Button>
        )}
      </div>

      <div className="grid grid-cols-2 gap-px bg-slate-200 sm:grid-cols-4" aria-label="عدادات تحضير اليوم">
        <DailyCount label="تحاضير معتمدة" value={submitted} />
        <DailyCount label="حضور" value={present} tone="text-emerald-700" />
        <DailyCount label="غياب" value={absent} tone="text-red-700" />
        <DailyCount label="لم يعتمد" value={notSubmitted} tone="text-slate-500" />
      </div>

      <div className="grid gap-3 p-4 sm:grid-cols-2 xl:grid-cols-4">
        {detail.periods.map((period) => {
          const isAbsent = period.status === "ABSENT";
          const isPresent = period.status === "PRESENT";
          const tone = isAbsent
            ? "border-red-200 bg-red-50/70"
            : isPresent
              ? "border-emerald-200 bg-emerald-50/70"
              : "border-slate-200 bg-slate-50";
          const badgeTone = isAbsent
            ? "bg-red-100 text-red-800"
            : isPresent
              ? "bg-emerald-100 text-emerald-800"
              : "bg-slate-200 text-slate-700";
          return (
            <article key={period.sequence} className={`rounded-xl border p-3 ${tone}`} data-testid={`period-status-${period.sequence}`}>
              <div className="flex items-start justify-between gap-2">
                <div>
                  <strong className="block text-sm text-slate-950">{period.name || `الحصة ${period.sequence}`}</strong>
                  {(period.start_time || period.end_time) && (
                    <span dir="ltr" className="mt-1 block text-xs text-slate-500">
                      {period.start_time ?? "—"} – {period.end_time ?? "—"}
                    </span>
                  )}
                </div>
                <span className={`rounded-full px-2 py-1 text-[11px] font-bold ${badgeTone}`}>
                  {MARK_LABELS[period.status]}
                </span>
              </div>
              {isAbsent && (
                <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-red-200 pt-2 text-xs">
                  <span className="font-bold text-red-800">{period.excused ? "بعذر" : "بدون عذر"}</span>
                  {canManageExcuses && period.excused === false && (
                    <button type="button" className="font-bold text-blue-700 underline" onClick={() => onQuickExcuse(detail.date, period.sequence)} data-testid={`period-add-excuse-${period.sequence}`}>
                      إضافة عذر
                    </button>
                  )}
                </div>
              )}
              {canManageExcuses && period.session_id && (isAbsent || isPresent) && (
                <AttendanceCorrectionControl
                  sessionId={period.session_id}
                  date={detail.date}
                  periodName={period.name || `الحصة ${period.sequence}`}
                  currentStatus={period.status as "PRESENT" | "ABSENT"}
                />
              )}
            </article>
          );
        })}
        {detail.periods.length === 0 && (
          <p className="text-sm text-slate-500">لا توجد حصص تحضير مجدولة لهذا اليوم.</p>
        )}
      </div>
    </div>
  );
}

function AttendanceCorrectionControl({ sessionId, date, periodName, currentStatus }: {
  sessionId: number;
  date: string;
  periodName: string;
  currentStatus: "PRESENT" | "ABSENT";
}) {
  const { studentId } = useParams<{ studentId: string }>();
  const schoolId = useActiveSchoolId();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [saved, setSaved] = useState(false);
  const nextStatus = currentStatus === "ABSENT" ? "PRESENT" : "ABSENT";
  const action = nextStatus === "PRESENT" ? "تصحيح إلى حاضر" : "تصحيح إلى غائب";
  const mutation = useMutation({
    mutationFn: () => correctStudentAttendance(Number(studentId), sessionId, nextStatus, reason.trim()),
    onSuccess: () => {
      setOpen(false);
      setReason("");
      setSaved(true);
      void queryClient.invalidateQueries({ queryKey: schoolScopedKey(schoolId) });
    },
  });

  return (
    <div className="mt-3 border-t border-slate-200 pt-3 text-sm">
      {!open ? (
        <button type="button" className="font-bold text-blue-700 underline" onClick={() => { setOpen(true); setSaved(false); mutation.reset(); }}>
          تصحيح الحضور
        </button>
      ) : (
        <form onSubmit={(event) => { event.preventDefault(); mutation.mutate(); }} className="space-y-2">
          <p className="font-bold text-slate-800">{action} — {periodName}، {formatDate(date)}</p>
          <label className="block font-medium text-slate-700">
            سبب التصحيح
            <textarea
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              required
              maxLength={300}
              rows={2}
              className="mt-1 w-full rounded-lg border border-slate-300 bg-white p-2"
              placeholder="مثال: تم تسجيل الغياب بالخطأ"
            />
          </label>
          {currentStatus === "ABSENT" && (
            <p className="text-xs text-slate-600">إذا صدر إنذار سابق بسبب هذا الغياب، راجعه من قسم الإنذارات بعد التصحيح.</p>
          )}
          {mutation.isError && <p role="alert" className="text-red-700">{mutation.error.message}</p>}
          <div className="flex gap-2">
            <Button type="submit" disabled={!reason.trim() || mutation.isPending}>{mutation.isPending ? "جارٍ الحفظ..." : action}</Button>
            <Button type="button" variant="secondary" onClick={() => { setOpen(false); mutation.reset(); }}>إلغاء</Button>
          </div>
        </form>
      )}
      {saved && <p role="status" className="mt-2 font-bold text-emerald-700">تم حفظ التصحيح وتحديث سجل الحضور.</p>}
    </div>
  );
}

function DailyCount({ label, value, tone = "text-slate-900" }: { label: string; value: number; tone?: string }) {
  return <div className="bg-white p-3 text-center"><strong className={`block text-xl ${tone}`}>{value}</strong><span className="text-xs text-slate-500">{label}</span></div>;
}

function Metric({ label, value, hint, tone = "slate", className = "" }: { label: string; value: string; hint?: string; tone?: "slate" | "green" | "amber" | "red"; className?: string }) {
  const tones = {
    slate: "border-slate-200 bg-white",
    green: "border-emerald-200 bg-emerald-50/60",
    amber: "border-amber-200 bg-amber-50/60",
    red: "border-red-200 bg-red-50/60",
  };
  return <div className={`rounded-xl border p-4 shadow-sm ${tones[tone]} ${className}`}><p className="text-xs font-bold text-slate-600">{label}</p><strong className="mt-2 block text-xl text-slate-950">{value}</strong>{hint && <span className="mt-1 block text-[11px] text-slate-500">{hint}</span>}</div>;
}

function DaysTab({ days, count, page, onPage, selectedDay, onSelect, detail, detailPending, detailError, canManageExcuses, onQuickExcuse }: {
  days: Awaited<ReturnType<typeof getAttendanceDays>>["results"];
  count: number;
  page: number;
  onPage: (page: number) => void;
  selectedDay: string | null;
  onSelect: (date: string) => void;
  detail?: Awaited<ReturnType<typeof getAttendanceDayDetail>>;
  detailPending: boolean;
  detailError: unknown;
  canManageExcuses: boolean;
  onQuickExcuse: (date: string, period?: number) => void;
}) {
  return (
    <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      <div className="divide-y rounded-xl border border-slate-200 bg-white">
        {days.map((day) => (
          <button
            key={day.date}
            type="button"
            data-testid={`day-row-${day.date}`}
            onClick={() => onSelect(day.date)}
            className={`flex w-full flex-col items-start justify-between gap-2 p-4 text-start sm:flex-row sm:items-center ${selectedDay === day.date ? "bg-blue-50" : "hover:bg-slate-50"}`}
          >
            <span>
              <strong>{formatDate(day.date)}</strong>
              <span className="mt-1 block text-sm text-slate-600">
                {DAY_LABELS[day.absence_status]}
              </span>
            </span>
            <span className="text-sm leading-6 text-slate-500 sm:text-end">
              {(day.present_periods ?? Math.max((day.submitted_periods ?? 0) - day.absent_periods, 0))} حضور · {day.absent_periods} غياب
              {day.excused_absent_periods > 0 && ` (${day.excused_absent_periods} بعذر)`}
              <span className="block text-xs">من {day.submitted_periods ?? "—"} تحضير معتمد</span>
            </span>
          </button>
        ))}
        {days.length === 0 && (
          <p className="p-6 text-sm text-slate-500">لا توجد بيانات أيام في الفترة.</p>
        )}
        <Pager count={count} page={page} onPage={onPage} />
      </div>
      <div>
        {detailPending && selectedDay && <Spinner label="جارٍ تحميل تفاصيل اليوم..." />}
        {detailError ? <ErrorState error={detailError} /> : null}
        {detail && <AttendanceDayOverview detail={detail} canManageExcuses={canManageExcuses} onQuickExcuse={onQuickExcuse} />}
      </div>
    </div>
  );
}

function PeriodTab({ rows, count, page, onPage, empty }: { rows: Awaited<ReturnType<typeof getAttendancePeriodAbsences>>["results"]; count: number; page: number; onPage: (page: number) => void; empty: string }) {
  return <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm"><table className="block w-full text-sm md:table"><thead className="hidden bg-slate-50 md:table-header-group"><tr className="border-b text-slate-500"><th className="p-3 text-start">التاريخ</th><th className="p-3 text-start">الحصة</th><th className="p-3 text-start">الصف/الفصل</th></tr></thead><tbody className="grid gap-3 p-3 md:table-row-group md:p-0">{rows.map((row) => <tr key={`${row.date}-${row.sequence}`} className="grid grid-cols-2 gap-3 rounded-2xl border border-slate-200 p-4 md:table-row md:border-x-0 md:border-t-0 md:p-0"><td className="col-span-2 p-0 font-bold md:table-cell md:p-3 md:font-normal"><span className="mb-1 block text-xs font-bold text-slate-500 md:hidden">التاريخ</span>{formatDate(row.date)}</td><td className="p-0 md:table-cell md:p-3"><span className="mb-1 block text-xs font-bold text-slate-500 md:hidden">الحصة</span>{row.period.name}</td><td className="p-0 md:table-cell md:p-3"><span className="mb-1 block text-xs font-bold text-slate-500 md:hidden">الصف والفصل</span>{row.section.grade_name} / {row.section.name}</td></tr>)}</tbody></table>{rows.length === 0 && <p className="p-6 text-sm text-slate-500">{empty}</p>}<Pager count={count} page={page} onPage={onPage} /></div>;
}

function ChangesTab({ rows, count, page, onPage }: { rows: Awaited<ReturnType<typeof getAttendanceChanges>>["results"]; count: number; page: number; onPage: (page: number) => void }) {
  return <div className="divide-y rounded-xl border border-slate-200 bg-white">{rows.map((row) => <div key={`${row.date}-${row.sequence}-${row.changed_at}`} className="p-4 text-sm"><strong>{formatDate(row.date)} - {row.period.name}</strong><p className="mt-1 text-slate-700">{row.previous_status_label} ← {row.new_status_label}{row.reason ? ` - السبب: ${row.reason}` : ""}</p><p className="text-slate-500">بواسطة: {row.actor ?? "غير معروف"} • {new Date(row.changed_at).toLocaleTimeString("ar-SA", { hour: "2-digit", minute: "2-digit" })}</p></div>)}{rows.length === 0 && <p className="p-6 text-sm text-slate-500">لا توجد تعديلات في الفترة.</p>}<Pager count={count} page={page} onPage={onPage} /></div>;
}

function Pager({ count, page, onPage }: { count: number; page: number; onPage: (page: number) => void }) {
  const totalPages = Math.max(1, Math.ceil(count / 25));
  return <div className="flex flex-col items-stretch justify-between gap-3 border-t border-slate-100 p-3 text-sm sm:flex-row sm:items-center"><span className="text-center text-slate-500 sm:text-start">صفحة {page} من {totalPages}</span><div className="grid grid-cols-2 gap-2"><button type="button" disabled={page <= 1} onClick={() => onPage(page - 1)} className="min-h-10 rounded-xl border px-3 py-1 disabled:opacity-40">السابق</button><button type="button" disabled={page >= totalPages} onClick={() => onPage(page + 1)} className="min-h-10 rounded-xl border px-3 py-1 disabled:opacity-40">التالي</button></div></div>;
}
