import { useMutation } from "@tanstack/react-query";
import { CalendarCheck2, RotateCcw } from "lucide-react";
import { useState } from "react";

import { ApiError } from "@/api/client";
import { Button } from "@/components/Button";
import { ErrorState } from "@/components/ErrorState";
import { Spinner } from "@/components/Spinner";
import {
  putWeekDays,
  WEEKDAY_LABELS,
  type BellSchedule,
  type WeekDay,
} from "@/features/settings/api";
import {
  useInvalidateSchoolData,
  useSchedulesQuery,
  useWeekDaysQuery,
} from "@/features/settings/hooks";

export function WeekDaysTab({ canWrite }: { canWrite: boolean }) {
  const weekDays = useWeekDaysQuery();
  const schedules = useSchedulesQuery();

  if (weekDays.isPending || schedules.isPending) return <Spinner />;
  if (weekDays.isError) return <ErrorState error={weekDays.error} />;

  return (
    <WeekDaysForm
      initialDays={weekDays.data.days}
      schedules={schedules.data ?? []}
      canWrite={canWrite}
    />
  );
}

function WeekDaysForm({
  initialDays,
  schedules,
  canWrite,
}: {
  initialDays: WeekDay[];
  schedules: BellSchedule[];
  canWrite: boolean;
}) {
  const invalidate = useInvalidateSchoolData();
  const [rows, setRows] = useState<WeekDay[]>(initialDays);
  const [savedRows, setSavedRows] = useState<WeekDay[]>(initialDays);
  const isDirty = JSON.stringify(rows) !== JSON.stringify(savedRows);
  const activeDays = rows.filter((row) => row.is_school_day).length;

  const saveMutation = useMutation({
    mutationFn: () =>
      putWeekDays(
        rows.map((r) => ({
          weekday: r.weekday,
          is_school_day: r.is_school_day,
          bell_schedule_id: r.is_school_day ? r.bell_schedule_id : null,
        })),
      ),
    onSuccess: () => {
      setSavedRows(rows);
      void invalidate("week-days");
    },
  });

  function updateRow(weekday: number, patch: Partial<WeekDay>) {
    setRows((prev) => prev.map((r) => (r.weekday === weekday ? { ...r, ...patch } : r)));
  }

  return (
    <section className="max-w-3xl rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
      <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-3"><span className="grid size-10 shrink-0 place-items-center rounded-xl bg-blue-50 text-blue-700"><CalendarCheck2 aria-hidden size={20} /></span><div><h3 className="font-bold">أسبوع المدرسة</h3><p className="mt-1 text-sm text-slate-500">
        حدد أيام الدراسة وجدول الحصص المطبق في كل يوم — نفس الجدول يمكن أن يخدم عدة أيام.
        </p></div></div>
        <span className="rounded-full bg-slate-100 px-3 py-1.5 text-xs font-bold text-slate-600">{activeDays} أيام دراسية</span>
      </div>

      {schedules.length === 0 && <p className="mb-4 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">لم تُنشئ جدول حصص بعد. يمكنك تحديد أيام الدراسة الآن ثم ربط الجداول بعد إنشائها.</p>}

      <ul className="mb-5 grid gap-2 sm:grid-cols-2">
        {rows.map((row) => (
          <li key={row.weekday} className={`rounded-xl border p-3 transition ${row.is_school_day ? "border-blue-200 bg-blue-50/50" : "border-slate-200 bg-slate-50/70"}`}>
            <label className="flex items-center gap-2 text-sm font-bold">
              <input
                type="checkbox"
                checked={row.is_school_day}
                disabled={!canWrite}
                onChange={(e) => updateRow(row.weekday, { is_school_day: e.target.checked })}
                className="size-4"
              />
              {WEEKDAY_LABELS[row.weekday]}
            </label>
            {row.is_school_day && (
              <select
                aria-label={`جدول ${WEEKDAY_LABELS[row.weekday]}`}
                value={row.bell_schedule_id ?? ""}
                disabled={!canWrite}
                onChange={(e) =>
                  updateRow(row.weekday, {
                    bell_schedule_id: e.target.value ? Number(e.target.value) : null,
                  })
                }
                className="mt-3 w-full border border-slate-300 px-3 py-1.5 text-sm"
              >
                <option value="">— بدون جدول —</option>
                {schedules.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </select>
            )}
          </li>
        ))}
      </ul>

      {saveMutation.error instanceof ApiError && (
        <p role="alert" className="mb-3 rounded-xl border border-red-100 bg-red-50 p-3 text-sm text-red-700">
          {saveMutation.error.message}
        </p>
      )}
      {saveMutation.isSuccess && <p role="status" className="mb-3 rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-sm font-medium text-emerald-700">تم حفظ أيام الدراسة.</p>}

      {canWrite && (
        <div className="flex flex-wrap gap-2 border-t border-slate-100 pt-4">
          <Button onClick={() => saveMutation.mutate()} disabled={saveMutation.isPending || !isDirty}>حفظ أيام الدراسة</Button>
          {isDirty && <Button variant="secondary" onClick={() => setRows(savedRows)}><RotateCcw aria-hidden size={16} /> تراجع</Button>}
        </div>
      )}
    </section>
  );
}
