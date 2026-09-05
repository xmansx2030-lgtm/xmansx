import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarDays, ScanFace } from "lucide-react";
import { useState } from "react";

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

function todayIso(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

type Tab = "today" | "late" | "history";

/** الحضور الصباحي (وكيل + مدير): ملخص اليوم، المتأخرون، سجل طالب، وصول يدوي وتصحيح.
 *  قاعدة صلبة: لا قائمة «غائبين» هنا — غياب البصمة لا يعني غيابًا عن المدرسة. */
export function MorningPage() {
  const me = useMe();
  const queryClient = useQueryClient();
  const schoolId = me.data?.active_school?.id ?? 0;
  const [tab, setTab] = useState<Tab>("today");
  const [date, setDate] = useState(todayIso());
  const isToday = date === todayIso();

  const summaryQuery = useQuery({
    queryKey: schoolScopedKey(schoolId, "morning", "summary", date),
    queryFn: ({ signal }) => getMorningSummary(date, signal),
    enabled: schoolId > 0,
    refetchInterval: isToday ? 30_000 : false, // البصمات تتدفق أثناء الصباح
  });

  const refresh = () =>
    queryClient.invalidateQueries({
      predicate: (q) => JSON.stringify(q.queryKey).includes('"morning"'),
    });

  return (
    <div className="space-y-5">
      <PageHeader icon={ScanFace} eyebrow="الاستقبال الصباحي" title="الحضور الصباحي" description="مراقبة وصول الطلاب من أجهزة الحضور، ومعالجة الحالات اليدوية دون الخلط بينها وبين الغياب الرسمي." tone="operational" badge={isToday ? "تحديث مباشر" : "سجل تاريخي"} actions={<label className="flex items-center gap-2 rounded-xl bg-white/10 px-3 py-2 text-sm font-bold text-white ring-1 ring-white/15"><CalendarDays aria-hidden size={17} /><span className="sr-only">التاريخ</span><input type="date" value={date} onChange={(e) => setDate(e.target.value)} className="border-white/20 bg-white text-slate-950" data-testid="morning-date" /></label>} />
      <section className="rounded-2xl border border-slate-200 bg-white px-4 pt-2 shadow-sm">
        <div className="mt-3 flex gap-1 border-b border-slate-100" role="tablist">
          {(
            [
              ["today", "اليوم"],
              ["late", "المتأخرون"],
              ["history", "سجل طالب"],
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

      {tab === "today" && (
        <>
          {summaryQuery.isPending && <Spinner />}
          {summaryQuery.isError && (
            <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
              <ErrorState error={summaryQuery.error} />
            </section>
          )}
          {summaryQuery.isSuccess && (
            <section className="grid grid-cols-2 gap-2 sm:grid-cols-5" data-testid="morning-kpis">
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
                  className="rounded-xl border border-slate-200 bg-white p-3 text-center shadow-sm"
                >
                  <p className="text-2xl font-bold text-slate-800">{value}</p>
                  <p className="text-xs text-slate-500">{label}</p>
                </div>
              ))}
            </section>
          )}
          <p className="rounded-xl border border-slate-200 bg-white p-3 text-xs text-slate-500 shadow-sm">
            عدم وجود بصمة لا يعني غياب الطالب (جهاز معطل/بوابة أخرى/مزامنة متأخرة) —
            الغياب الرسمي من تحضير الحصص فقط.
          </p>
          <ManualArrivalCard date={date} onDone={refresh} />
        </>
      )}

      {tab === "late" && <LateTab date={date} schoolId={schoolId} onChanged={refresh} />}
      {tab === "history" && <HistoryTab schoolId={schoolId} />}
    </div>
  );
}

function ManualArrivalCard({ date, onDone }: { date: string; onDone: () => void }) {
  const [student, setStudent] = useState<{ id: number; name: string } | null>(null);
  const [time, setTime] = useState("07:10");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [saved, setSaved] = useState<string | null>(null);

  return (
    <section className="space-y-2 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <h3 className="font-bold text-slate-800">تسجيل وصول يدوي</h3>
      <p className="text-xs text-slate-500">
        لطالب دخل من بوابة أخرى أو تعطل الجهاز — التأخر يحسب خادميًا من إعدادات الدوام.
      </p>
      {student ? (
        <p className="text-sm">
          الطالب: <span className="font-medium">{student.name}</span>{" "}
          <button type="button" className="text-blue-700 underline" onClick={() => setStudent(null)}>
            تغيير
          </button>
        </p>
      ) : (
        <StudentPicker onSelect={(id, name) => setStudent({ id, name })} />
      )}
      <div className="flex flex-wrap items-center gap-2">
        <label className="text-sm text-slate-600">
          وقت الوصول{" "}
          <input
            type="time"
            value={time}
            onChange={(e) => setTime(e.target.value)}
            className="rounded-lg border border-slate-300 px-2 py-1.5"
            data-testid="manual-arrival-time"
          />
        </label>
        <input
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="السبب (إلزامي)"
          aria-label="سبب التسجيل اليدوي"
          className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm"
        />
        <Button
          disabled={!student || !reason.trim()}
          onClick={() => {
            setError(null);
            setSaved(null);
            void createManualArrival({
              student_id: student!.id,
              date,
              arrival_time: time,
              reason: reason.trim(),
            })
              .then((arrival) => {
                setSaved(
                  arrival.status === "LATE"
                    ? `سجل — متأخر ${arrival.counted_late_minutes} دقيقة`
                    : "سجل — في الوقت",
                );
                setStudent(null);
                setReason("");
                onDone();
              })
              .catch(setError);
          }}
          data-testid="save-manual-arrival"
        >
          تسجيل الوصول
        </Button>
      </div>
      {saved && (
        <p className="text-sm text-green-700" data-testid="manual-arrival-result">
          {saved}
        </p>
      )}
      {error != null && <ErrorState error={error} />}
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
          placeholder="بحث باسم الطالب"
          aria-label="بحث باسم الطالب"
          className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm"
        />
        {lateQuery.isSuccess && (
          <span className="text-sm text-slate-600" data-testid="late-total">
            {lateQuery.data.total_late} طالبًا متأخرًا
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
                  className="flex flex-wrap items-center justify-between gap-2 p-3"
                  data-testid={`late-row-${row.student_id}`}
                >
                  <div>
                    <p className="font-medium text-slate-800">{row.full_name}</p>
                    <p className="text-xs text-slate-500">
                      {row.grade_name} / {row.section_name}
                    </p>
                  </div>
                  <p className="text-sm text-slate-600">
                    وصل <span dir="ltr">{row.arrival_time}</span> · متأخر{" "}
                    {row.counted_late_minutes} دقيقة ·{" "}
                    {row.source === "BIOMETRIC" ? "البصمة" : "يدوي"}
                  </p>
                  {correcting === row.arrival_id ? (
                    <span className="flex items-center gap-2">
                      <input
                        type="time"
                        value={correctTime}
                        onChange={(e) => setCorrectTime(e.target.value)}
                        aria-label="وقت الوصول المصحح"
                        className="rounded-lg border border-slate-300 px-2 py-1 text-sm"
                        data-testid="correct-time"
                      />
                      <input
                        value={correctReason}
                        onChange={(e) => setCorrectReason(e.target.value)}
                        placeholder="السبب"
                        aria-label="سبب التصحيح"
                        className="rounded-lg border border-slate-300 px-2 py-1 text-sm"
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
                        data-testid="save-correction"
                      >
                        حفظ
                      </Button>
                      <Button variant="secondary" onClick={() => setCorrecting(null)}>
                        إلغاء
                      </Button>
                    </span>
                  ) : (
                    <Button
                      variant="secondary"
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
            الطالب: <span className="font-medium">{student.name}</span>{" "}
            <button type="button" className="text-blue-700 underline" onClick={() => setStudent(null)}>
              تغيير
            </button>
          </p>
        ) : (
          <StudentPicker onSelect={(id, name) => setStudent({ id, name })} />
        )}
        <div className="flex flex-wrap items-center gap-2 text-sm text-slate-600">
          <label>
            من{" "}
            <input
              type="date"
              value={from}
              onChange={(e) => setFrom(e.target.value)}
              className="rounded-lg border border-slate-300 px-2 py-1.5"
            />
          </label>
          <label>
            إلى{" "}
            <input
              type="date"
              value={to}
              onChange={(e) => setTo(e.target.value)}
              className="rounded-lg border border-slate-300 px-2 py-1.5"
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
