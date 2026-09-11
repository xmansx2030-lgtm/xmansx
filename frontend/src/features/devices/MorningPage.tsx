import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CalendarDays,
  CheckCircle2,
  Clock3,
  ScanFace,
  ShieldCheck,
  Sunrise,
  UserRoundCheck,
  WifiOff,
} from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/Button";
import { ErrorState } from "@/components/ErrorState";
import { PageHeader } from "@/components/PageHeader";
import { Spinner } from "@/components/Spinner";
import {
  correctArrival,
  createManualArrival,
  getMorningLate,
  getMorningSummary,
  getStudentLateHistory,
} from "@/features/devices/api";
import { StudentPicker } from "@/features/devices/StudentPicker";
import { schoolScopedKey, useMe } from "@/features/auth/useMe";
import { studentCountLabel, studentLabel, studentPluralLabel } from "@/utils/roles";

function todayIso(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function currentTime(): string {
  const now = new Date();
  return `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`;
}

function useOnlineStatus() {
  const [online, setOnline] = useState(() => navigator.onLine);
  useEffect(() => {
    const update = () => setOnline(navigator.onLine);
    window.addEventListener("online", update);
    window.addEventListener("offline", update);
    return () => {
      window.removeEventListener("online", update);
      window.removeEventListener("offline", update);
    };
  }, []);
  return online;
}

type Tab = "today" | "late" | "history";

/** التأخر الصباحي: الإدارة والمعلم المكلّف، مع حساب خادمي وسجل تدقيق.
 *  قاعدة صلبة: لا قائمة «غائبين» هنا — غياب البصمة لا يعني غيابًا عن المدرسة. */
export function MorningPage() {
  const me = useMe();
  const queryClient = useQueryClient();
  const schoolId = me.data?.active_school?.id ?? 0;
  const schoolType = me.data?.active_school?.school_type ?? "BOYS";
  const [tab, setTab] = useState<Tab>("today");
  const [date, setDate] = useState(todayIso());
  const isToday = date === todayIso();
  const isDelegatedOperator = (me.data?.capabilities ?? []).includes("MORNING_ATTENDANCE");
  const online = useOnlineStatus();

  const summaryQuery = useQuery({
    queryKey: schoolScopedKey(schoolId, "morning", "summary", date),
    queryFn: ({ signal }) => getMorningSummary(date, signal),
    enabled: schoolId > 0,
    refetchInterval: isToday ? 30_000 : false, // البصمات تتدفق أثناء الصباح
  });

  const refresh = () => Promise.all([
    queryClient.invalidateQueries({
      queryKey: schoolScopedKey(schoolId, "morning"),
    }),
    queryClient.invalidateQueries({
      queryKey: schoolScopedKey(schoolId, "dashboard"),
    }),
  ]);

  return (
    <div className="ds-page" data-testid="morning-attendance-page">
      <PageHeader
        icon={Sunrise}
        eyebrow={isDelegatedOperator ? "تكليف تشغيلي مستقل" : "الاستقبال الصباحي"}
        title="التأخر الصباحي"
        description={`تسجيل وقت الوصول الفعلي ${studentPluralLabel(schoolType) === "الطالبات" ? "للطالبات" : "للطلاب"} وحساب التأخر تلقائيًا ضمن تكليف مستقل لا يغيّر أدوار الموظف أو مهامه الأصلية.`}
        tone="operational"
        badge={isDelegatedOperator ? "تكليف نشط" : isToday ? "تحديث مباشر" : "سجل تاريخي"}
        actions={<label className="flex min-h-11 items-center gap-2 rounded-xl bg-white/10 px-3 py-2 text-sm font-bold text-white ring-1 ring-white/15"><CalendarDays aria-hidden size={17} /><span className="sr-only">التاريخ</span><input type="date" value={date} onChange={(e) => setDate(e.target.value)} className="min-h-11 border-white/20 bg-white text-slate-950" data-testid="morning-date" /></label>}
      />

      {!online && (
        <div role="status" className="flex items-start gap-3 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-950" data-testid="morning-offline-notice">
          <WifiOff aria-hidden size={20} className="mt-0.5 shrink-0" />
          <div><p className="font-black">أنت تعمل دون اتصال</p><p className="mt-1 text-xs leading-5">تظل واجهة PWA متاحة، لكن تسجيل الوصول يحتاج اتصالًا لحظيًا لمنع التكرار بين المكلّفين.</p></div>
        </div>
      )}

      {summaryQuery.isSuccess && (
        <section className="grid overflow-hidden rounded-3xl border border-amber-200 bg-gradient-to-l from-amber-50 via-white to-white shadow-sm md:grid-cols-[minmax(0,1fr)_auto]" data-testid="morning-policy">
          <div className="flex items-start gap-3 p-5">
            <span className="grid size-11 shrink-0 place-items-center rounded-2xl bg-amber-500 text-white shadow-md shadow-amber-900/15"><Clock3 aria-hidden size={21} /></span>
            <div><h2 className="font-black text-slate-900">سياسة الاحتساب المعتمدة</h2><p className="mt-1 text-sm leading-6 text-slate-600">بداية الدوام <b dir="ltr">{summaryQuery.data.school_day_start_time}</b>، وفترة السماح {summaryQuery.data.grace_minutes} دقائق. يبدأ تصنيف الوصول متأخرًا بعد <b dir="ltr">{summaryQuery.data.late_after_time}</b>.</p></div>
          </div>
          <div className="grid grid-cols-3 border-t border-amber-100 bg-white/70 md:border-r md:border-t-0">
            <PolicyValue label="بداية الدوام" value={summaryQuery.data.school_day_start_time} />
            <PolicyValue label="السماح" value={`${summaryQuery.data.grace_minutes} د`} />
            <PolicyValue label="بعدها متأخر" value={summaryQuery.data.late_after_time} />
          </div>
        </section>
      )}

      <section className="overflow-x-auto rounded-2xl border border-slate-200 bg-white px-2 pt-2 shadow-sm">
        <div className="flex min-w-max gap-1 border-b border-slate-100" role="tablist">
          {(
            [
              ["today", "اليوم"],
              ["late", schoolType === "GIRLS" ? "المتأخرات" : "المتأخرون"],
              ["history", `سجل ${studentLabel(schoolType)}`],
            ] as const
          ).map(([key, label]) => (
            <button
              key={key}
              type="button"
              role="tab"
              aria-selected={tab === key}
              onClick={() => setTab(key)}
              className={`min-h-11 rounded-t-xl px-5 py-2 text-sm font-bold transition ${
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

      {tab === "today" && (
        <>
          {summaryQuery.isPending && <Spinner />}
          {summaryQuery.isError && (
            <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
              <ErrorState error={summaryQuery.error} />
            </section>
          )}
          {isDelegatedOperator && <ManualArrivalCard date={date} onDone={refresh} online={online} />}
          {summaryQuery.isSuccess && (
            <section className="grid grid-cols-2 gap-3 sm:grid-cols-5" data-testid="morning-kpis">
              {(
                [
                  ["kpi-arrived", "سجلوا حضورًا", summaryQuery.data.arrived_total],
                  ["kpi-on-time", "في الوقت", summaryQuery.data.on_time],
                  ["kpi-late", "متأخرون", summaryQuery.data.late],
                  ["kpi-unmatched", "أحداث غير مطابقة", summaryQuery.data.unmatched_events],
                  ["kpi-devices-offline", "أجهزة غير متصلة", summaryQuery.data.devices_offline],
                ] as const
              ).map(([testId, label, value]) => (
                <div
                  key={testId}
                  data-testid={testId}
                  className="rounded-2xl border border-slate-200 bg-white p-4 text-center shadow-sm"
                >
                  <p className="text-2xl font-black tabular-nums text-slate-900">{value}</p>
                  <p className="mt-1 text-xs font-bold text-slate-500">{label}</p>
                </div>
              ))}
            </section>
          )}
          <div className="flex items-start gap-3 rounded-2xl border border-teal-100 bg-teal-50/60 p-4 text-xs leading-5 text-teal-950">
            <ShieldCheck aria-hidden size={18} className="mt-0.5 shrink-0 text-teal-700" />
            <p>عدم وجود بصمة لا يعني غياب {studentLabel(schoolType, true)}؛ الغياب الرسمي يبقى من تحضير الحصص «حاضر/غائب» فقط.</p>
          </div>
          {!isDelegatedOperator && <ManualArrivalCard date={date} onDone={refresh} online={online} />}
        </>
      )}

      {tab === "late" && <LateTab date={date} schoolId={schoolId} onChanged={refresh} />}
      {tab === "history" && <HistoryTab schoolId={schoolId} />}
    </div>
  );
}

function PolicyValue({ label, value }: { label: string; value: string }) {
  return <div className="grid min-w-24 place-items-center border-l border-amber-100 p-3 text-center last:border-l-0"><strong className="text-base tabular-nums text-slate-900" dir="auto">{value}</strong><span className="mt-1 text-[10px] font-bold text-slate-500">{label}</span></div>;
}

function ManualArrivalCard({ date, onDone, online }: { date: string; onDone: () => void; online: boolean }) {
  const schoolType = useMe().data?.active_school?.school_type ?? "BOYS";
  const [student, setStudent] = useState<{ id: number; name: string } | null>(null);
  const [time, setTime] = useState(currentTime);
  const [error, setError] = useState<unknown>(null);
  const [saved, setSaved] = useState<string | null>(null);

  return (
    <section className="overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-lg shadow-slate-950/5" data-testid="manual-arrival-card">
      <div className="border-b border-slate-100 bg-gradient-to-l from-slate-950 via-slate-900 to-teal-950 p-5 text-white sm:p-6">
        <div className="flex items-start gap-3"><span className="grid size-11 shrink-0 place-items-center rounded-2xl bg-white/10 text-teal-200 ring-1 ring-white/10"><UserRoundCheck aria-hidden size={21} /></span><div><h3 className="text-lg font-black">تسجيل وصول متأخر</h3><p className="mt-1 text-xs leading-5 text-slate-300">أدخل وقت الوصول الفعلي، والمنصة تحسب الدقائق وتحفظ منفذ العملية تلقائيًا.</p></div></div>
      </div>
      <div className="space-y-5 p-4 sm:p-6">
        <div>
          <p className="mb-2 text-sm font-black text-slate-800">1. اختر {studentLabel(schoolType, true)}</p>
          {student ? (
            <div className="flex items-center justify-between gap-3 rounded-2xl border border-teal-200 bg-teal-50 p-3 text-sm"><span><CheckCircle2 aria-hidden size={17} className="ml-2 inline text-teal-700" /><b>{student.name}</b></span><button type="button" className="min-h-11 rounded-lg px-3 font-bold text-teal-800 hover:bg-white" onClick={() => setStudent(null)}>تغيير</button></div>
          ) : (
            <StudentPicker
              searchEndpoint="/morning/students/search/"
              showMaskedIdentifier={false}
              onSelect={(id, name) => setStudent({ id, name })}
            />
          )}
        </div>
        <label className="block max-w-sm text-sm font-black text-slate-800">2. وقت الوصول الفعلي
          <input type="time" value={time} onChange={(e) => setTime(e.target.value)} className="mt-2 min-h-12 w-full rounded-xl border border-slate-300 bg-slate-50 px-3 text-base font-black tabular-nums" data-testid="manual-arrival-time" />
        </label>
        <Button
          className="min-h-12 w-full text-base sm:w-auto"
          disabled={!student || !time || !online}
          onClick={() => {
            setError(null);
            setSaved(null);
            void createManualArrival({
              student_id: student!.id,
              date,
              arrival_time: time,
            })
              .then((arrival) => {
                setSaved(
                  arrival.status === "LATE"
                    ? `سجل — متأخر ${arrival.counted_late_minutes} دقيقة`
                    : "سجل — في الوقت",
                );
                setStudent(null);
                setTime(currentTime());
                onDone();
              })
              .catch(setError);
          }}
          data-testid="save-manual-arrival"
        >
          <ScanFace aria-hidden size={18} /> تسجيل الوصول واحتساب التأخر
        </Button>
      {saved && (
        <p role="status" className="rounded-2xl border border-emerald-200 bg-emerald-50 p-3 text-sm font-bold text-emerald-800" data-testid="manual-arrival-result">
          {saved}
        </p>
      )}
      {error != null && <ErrorState error={error} />}
      </div>
    </section>
  );
}

function LateTab({
  date,
  schoolId,
  onChanged,
}: {
  date: string;
  schoolId: number;
  onChanged: () => void;
}) {
  const schoolType = useMe().data?.active_school?.school_type ?? "BOYS";
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [correcting, setCorrecting] = useState<number | null>(null);
  const [correctTime, setCorrectTime] = useState("07:00");
  const [correctReason, setCorrectReason] = useState("");
  const [error, setError] = useState<unknown>(null);

  const lateQuery = useQuery({
    queryKey: schoolScopedKey(schoolId, "morning", "late", date, search, page),
    queryFn: ({ signal }) => getMorningLate({ date, search, page }, signal),
    enabled: schoolId > 0,
  });

  return (
    <div className="space-y-3">
      <section className="flex flex-wrap items-center gap-2 rounded-xl border border-slate-200 bg-white p-3 shadow-sm">
        <input
          type="search"
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setPage(1);
          }}
          placeholder={`بحث باسم ${studentLabel(schoolType, true)}`}
          aria-label={`بحث باسم ${studentLabel(schoolType, true)}`}
          className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm"
        />
        {lateQuery.isSuccess && (
          <span className="text-sm text-slate-600" data-testid="late-total">
            {lateQuery.data.total_late} {studentCountLabel(schoolType)} {schoolType === "GIRLS" ? "متأخرة" : "متأخرًا"}
          </span>
        )}
      </section>
      {error != null && <ErrorState error={error} />}
      {lateQuery.isPending && <Spinner />}
      {lateQuery.isError && <ErrorState error={lateQuery.error} />}
      {lateQuery.isSuccess && (
        <section className="rounded-xl border border-slate-200 bg-white shadow-sm">
          {lateQuery.data.students.length === 0 ? (
            <p className="p-6 text-slate-600" data-testid="no-late-students">
              لا يوجد متأخرون في هذا التاريخ.
            </p>
          ) : (
            <ul className="divide-y divide-slate-100" data-testid="late-list">
              {lateQuery.data.students.map((row) => (
                <li
                  key={row.arrival_id}
                  className="grid gap-3 p-4 md:grid-cols-[minmax(0,1fr)_auto_auto] md:items-center"
                  data-testid={`late-row-${row.student_id}`}
                >
                  <div>
                    <p className="font-black text-slate-900">{row.full_name}</p>
                    <p className="text-xs text-slate-500">
                      {row.grade_name} / {row.section_name}
                    </p>
                  </div>
                  <p className="rounded-xl bg-slate-50 px-3 py-2 text-sm font-medium text-slate-600">
                    وصل <span dir="ltr">{row.arrival_time}</span> · متأخر{" "}
                    {row.counted_late_minutes} دقيقة ·{" "}
                    {row.source === "BIOMETRIC" ? "البصمة" : "يدوي"}
                  </p>
                  {correcting === row.arrival_id ? (
                    <span className="grid w-full grid-cols-2 gap-2 rounded-2xl border border-blue-100 bg-blue-50/50 p-3 md:flex md:w-auto">
                      <input
                        type="time"
                        value={correctTime}
                        onChange={(e) => setCorrectTime(e.target.value)}
                        aria-label="وقت الوصول المصحح"
                        className="min-h-11 rounded-xl border border-slate-300 px-2 py-1 text-sm"
                        data-testid="correct-time"
                      />
                      <input
                        value={correctReason}
                        onChange={(e) => setCorrectReason(e.target.value)}
                        placeholder="السبب"
                        aria-label="سبب التصحيح"
                        className="col-span-2 min-h-11 rounded-xl border border-slate-300 px-3 py-1 text-sm md:col-span-1"
                        data-testid="correct-reason"
                      />
                      <Button
                        disabled={!correctReason.trim()}
                        onClick={() => {
                          setError(null);
                          void correctArrival(row.arrival_id, {
                            arrival_time: correctTime,
                            reason: correctReason.trim(),
                          })
                            .then(() => {
                              setCorrecting(null);
                              setCorrectReason("");
                              onChanged();
                            })
                            .catch(setError);
                        }}
                        className="min-h-11"
                        data-testid="save-correction"
                      >
                        حفظ
                      </Button>
                      <Button variant="secondary" className="min-h-11" onClick={() => setCorrecting(null)}>
                        إلغاء
                      </Button>
                    </span>
                  ) : (
                    <Button
                      variant="secondary"
                      className="w-full md:w-auto"
                      onClick={() => {
                        setCorrecting(row.arrival_id);
                        setCorrectTime(row.arrival_time);
                      }}
                      data-testid={`correct-${row.student_id}`}
                    >
                      تصحيح الوقت
                    </Button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
      {lateQuery.isSuccess && lateQuery.data.total_late > lateQuery.data.page_size && (
        <div className="flex items-center justify-center gap-3 text-sm">
          <Button variant="secondary" disabled={page <= 1} onClick={() => setPage(page - 1)}>
            السابق
          </Button>
          <span>صفحة {page}</span>
          <Button
            variant="secondary"
            disabled={page * lateQuery.data.page_size >= lateQuery.data.total_late}
            onClick={() => setPage(page + 1)}
          >
            التالي
          </Button>
        </div>
      )}
    </div>
  );
}

function HistoryTab({ schoolId }: { schoolId: number }) {
  const schoolType = useMe().data?.active_school?.school_type ?? "BOYS";
  const [student, setStudent] = useState<{ id: number; name: string } | null>(null);
  const year = new Date().getFullYear();
  const [from, setFrom] = useState(`${year}-08-01`);
  const [to, setTo] = useState(todayIso());

  const historyQuery = useQuery({
    queryKey: schoolScopedKey(schoolId, "morning", "history", student?.id, from, to),
    queryFn: ({ signal }) => getStudentLateHistory(student!.id, from, to, signal),
    enabled: schoolId > 0 && student !== null,
  });

  const formatMinutes = (total: number) => {
    const hours = Math.floor(total / 60);
    const minutes = total % 60;
    if (hours === 0) return `${minutes} دقيقة`;
    return `${hours} ساعة و${minutes} دقيقة`;
  };

  return (
    <div className="space-y-3">
      <section className="space-y-2 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        {student ? (
          <p className="text-sm">
            {studentLabel(schoolType, true)}: <span className="font-medium">{student.name}</span>{" "}
            <button type="button" className="text-blue-700 underline" onClick={() => setStudent(null)}>
              تغيير
            </button>
          </p>
        ) : (
          <StudentPicker
            searchEndpoint="/morning/students/search/"
            showMaskedIdentifier={false}
            onSelect={(id, name) => setStudent({ id, name })}
          />
        )}
        <div className="flex flex-wrap items-center gap-2 text-sm text-slate-600">
          <label>
            من{" "}
            <input
              type="date"
              value={from}
              onChange={(e) => setFrom(e.target.value)}
              className="min-h-11 rounded-lg border border-slate-300 px-2 py-1.5"
            />
          </label>
          <label>
            إلى{" "}
            <input
              type="date"
              value={to}
              onChange={(e) => setTo(e.target.value)}
              className="min-h-11 rounded-lg border border-slate-300 px-2 py-1.5"
            />
          </label>
        </div>
      </section>
      {historyQuery.isFetching && <Spinner />}
      {historyQuery.isError && (
        <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <ErrorState error={historyQuery.error} />
        </section>
      )}
      {historyQuery.isSuccess && (
        <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <p className="mb-2 text-sm font-bold text-slate-800" data-testid="history-summary">
            مرات التأخر عن الدوام: {historyQuery.data.late_count} · إجمالي الدقائق:{" "}
            {historyQuery.data.total_late_minutes} (
            {formatMinutes(historyQuery.data.total_late_minutes)})
          </p>
          <ul className="divide-y divide-slate-100" data-testid="history-entries">
            {historyQuery.data.entries.length === 0 && (
              <li className="py-2 text-slate-500">لا تأخر في هذه الفترة.</li>
            )}
            {historyQuery.data.entries.map((entry) => (
              <li key={entry.date} className="flex flex-wrap justify-between gap-2 py-2 text-sm">
                <span>{entry.date}</span>
                <span dir="ltr">{entry.arrival_time}</span>
                <span>
                  خام {entry.raw_late_minutes} د · محتسب {entry.counted_late_minutes} د
                </span>
                <span>{entry.source === "BIOMETRIC" ? "البصمة" : "يدوي"}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
