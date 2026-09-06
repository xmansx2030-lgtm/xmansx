import { useQuery } from "@tanstack/react-query";
import { ArrowRight, GraduationCap } from "lucide-react";
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
  getAttendanceChanges,
  getAttendanceDayDetail,
  getAttendanceDays,
  getAttendancePeriodAbsences,
  getAttendancePeriodLates,
  getAttendanceProfile,
  getMorningAttendance,
} from "@/features/students/api";
import { localIsoDate } from "@/utils/dates";

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

type Tab =
  | "summary"
  | "days"
  | "absences"
  | "lates"
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
    <div className="space-y-5">
      <PageHeader
        icon={GraduationCap}
        eyebrow="ملف الطالب الموحد"
        title={student.full_name}
        description={`${student.grade?.name ?? "لا يوجد صف حالي"} / ${student.section?.name ?? "لا يوجد فصل حالي"}`}
        tone="executive"
        badge={STATUS_LABELS[student.status] ?? student.status}
        meta={(
          <>
            <span>رقم الطالب: {student.student_number ?? "غير متوفر"}</span>
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
            العودة إلى الطلاب
          </Link>
        )}
        testId="student-profile-header"
      />

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
          يوجد {attendance.undetermined_days} يومًا لم تكتمل فيها بيانات التحضير.
        </div>
      )}
      {profile.data.morning_attendance.status === "AVAILABLE" ? (
        <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm text-slate-700">
          <strong className="block">التأخر عن الدوام الصباحي</strong>
          <span>{profile.data.morning_attendance.morning_late_occurrences ?? 0} مرات، </span>
          <span>{formatMinutes(profile.data.morning_attendance.morning_late_minutes ?? 0)}</span>
        </div>
      ) : (
        <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm text-slate-600">
          التأخر الصباحي: بيانات الحضور الصباحي غير متاحة.
        </div>
      )}

      <div className="flex flex-wrap gap-2 border-b border-slate-200">
        {tabs.map(([value, label]) => <button key={value} type="button" onClick={() => setTab(value)} className={`border-b-2 px-3 py-2 text-sm ${tab === value ? "border-blue-700 text-blue-700" : "border-transparent text-slate-600"}`}>{label}</button>)}
      </div>

      {tab === "summary" && <p className="text-sm text-slate-500">الفترة: {formatDate(fromDate)} إلى {formatDate(toDate)}</p>}
      {tab === "days" && <DaysTab days={days.data?.results ?? []} count={days.data?.count ?? 0} page={page} onPage={setPage} selectedDay={selectedDay} onSelect={setSelectedDay} detail={dayDetail.data} canManageExcuses={canManageExcuses} onQuickExcuse={(date, period) => { setQuickExcuse({ date, period }); setTab("excuses"); }} />}
      {tab === "absences" && <PeriodTab rows={absences.data?.results ?? []} count={absences.data?.count ?? 0} page={page} onPage={setPage} empty="لا توجد حصص غياب في الفترة." />}
      {tab === "lates" && <PeriodTab rows={lates.data?.results ?? []} count={lates.data?.count ?? 0} page={page} onPage={setPage} empty="لا توجد حالات تأخر عن الحصص في الفترة." showLate />}
      {tab === "morning" && <MorningTab rows={morning.data ?? []} />}
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
      {tab === "changes" && <ChangesTab rows={changes.data?.results ?? []} count={changes.data?.count ?? 0} page={page} onPage={setPage} />}
    </div>
  );
}

function ExcusesTab({
  rows,
  onSelect,
}: {
  rows: Awaited<ReturnType<typeof getExcuses>>["results"];
  onSelect: (excuseId: number) => void;
}) {
  return (
    <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
      <table className="w-full text-sm">
        <thead>
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
        <tbody>
          {rows.map((row) => (
            <tr key={row.id} className="border-b" data-testid={`profile-excuse-${row.id}`}>
              <td className="p-3">
                {row.date_from
                  ? row.date_from === row.date_to
                    ? formatDate(row.date_from)
                    : `${formatDate(row.date_from)} — ${formatDate(row.date_to!)}`
                  : "—"}
              </td>
              <td className="p-3">{row.reason_type_label}</td>
              <td className="p-3">
                <StatusBadge status={row.status} label={row.status_label} />
              </td>
              <td className="p-3">{row.active_coverage_count} حصة</td>
              <td className="p-3">{row.recorded_by_name ?? "—"}</td>
              <td className="p-3">{row.approved_by_name ?? "—"}</td>
              <td className="p-3">{row.attachments_count}</td>
              <td className="p-3">
                <button
                  type="button"
                  className="text-blue-700 underline"
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
          لا توجد أعذار مسجلة لهذا الطالب.
        </p>
      )}
    </div>
  );
}

function MorningTab({ rows }: { rows: Awaited<ReturnType<typeof getMorningAttendance>> }) {
  return <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white"><table className="w-full text-sm"><thead><tr className="border-b text-slate-500"><th className="p-3 text-start">التاريخ</th><th className="p-3 text-start">وقت الدخول</th><th className="p-3 text-start">الحالة</th><th className="p-3 text-start">التأخر المحتسب</th><th className="p-3 text-start">المصدر</th></tr></thead><tbody>{rows.map((row) => <tr key={row.date} className="border-b"><td className="p-3">{formatDate(row.date)}</td><td className="p-3">{new Date(row.arrival_time).toLocaleTimeString("ar-SA", { hour: "2-digit", minute: "2-digit" })}</td><td className="p-3">{row.status === "LATE" ? "متأخر" : "في الوقت"}</td><td className="p-3">{row.counted_late_minutes} دقيقة</td><td className="p-3">{row.source === "BIOMETRIC" ? "جهاز" : "يدوي"}</td></tr>)}{rows.length === 0 && <tr><td colSpan={5} className="p-6 text-center text-slate-500">لا توجد سجلات حضور صباحي في الفترة.</td></tr>}</tbody></table></div>;
}

function Metric({ label, value }: { label: string; value: string }) {
  return <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"><p className="text-xs text-slate-500">{label}</p><strong className="mt-2 block text-xl text-slate-900">{value}</strong></div>;
}

function DaysTab({ days, count, page, onPage, selectedDay, onSelect, detail, canManageExcuses, onQuickExcuse }: {
  days: Awaited<ReturnType<typeof getAttendanceDays>>["results"];
  count: number;
  page: number;
  onPage: (page: number) => void;
  selectedDay: string | null;
  onSelect: (date: string) => void;
  detail?: Awaited<ReturnType<typeof getAttendanceDayDetail>>;
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
            className={`flex w-full items-center justify-between p-4 text-start ${selectedDay === day.date ? "bg-blue-50" : "hover:bg-slate-50"}`}
          >
            <span>
              <strong>{formatDate(day.date)}</strong>
              <span className="mt-1 block text-sm text-slate-600">
                {DAY_LABELS[day.absence_status]}
              </span>
            </span>
            <span className="text-sm text-slate-500">
              {day.absent_periods} غياب
              {day.excused_absent_periods > 0 && ` (${day.excused_absent_periods} بعذر)`}
              {" • "}
              {day.late_periods} تأخر
            </span>
          </button>
        ))}
        {days.length === 0 && (
          <p className="p-6 text-sm text-slate-500">لا توجد بيانات أيام في الفترة.</p>
        )}
        <Pager count={count} page={page} onPage={onPage} />
      </div>
      {detail && (
        <div className="rounded-xl border border-slate-200 bg-white p-4">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="font-bold">تفاصيل {formatDate(detail.date)}</h2>
            {canManageExcuses && detail.absent_periods > 0 && (
              <Button
                variant="secondary"
                onClick={() => onQuickExcuse(detail.date)}
                data-testid="day-add-excuse"
              >
                إضافة عذر لهذا اليوم
              </Button>
            )}
          </div>
          <div className="divide-y">
            {detail.periods.map((period) => (
              <div
                key={period.sequence}
                className="flex items-center justify-between py-3 text-sm"
              >
                <span>
                  الحصة {period.sequence} - {period.name}
                </span>
                <span className="flex items-center gap-2">
                  <span>
                    {MARK_LABELS[period.status]}
                    {period.late_minutes ? ` (${period.late_minutes} دقيقة)` : ""}
                    {period.excused === true && " — بعذر"}
                    {period.excused === false && " — بدون عذر"}
                  </span>
                  {canManageExcuses && period.excused === false && (
                    <button
                      type="button"
                      className="text-blue-700 underline"
                      onClick={() => onQuickExcuse(detail.date, period.sequence)}
                      data-testid={`period-add-excuse-${period.sequence}`}
                    >
                      إضافة عذر
                    </button>
                  )}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
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
