import { useMutation } from "@tanstack/react-query";
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

  const saveMutation = useMutation({
    mutationFn: () =>
      putWeekDays(
        rows.map((r) => ({
          weekday: r.weekday,
          is_school_day: r.is_school_day,
          bell_schedule_id: r.is_school_day ? r.bell_schedule_id : null,
        })),
      ),
    onSuccess: () => void invalidate("week-days"),
  });

  function updateRow(weekday: number, patch: Partial<WeekDay>) {
    setRows((prev) => prev.map((r) => (r.weekday === weekday ? { ...r, ...patch } : r)));
  }

  return (
    <section className="max-w-2xl rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
      <h3 className="mb-1 font-bold">أيام الدراسة</h3>
      <p className="mb-4 text-sm text-slate-500">
        حدد أيام الدراسة وجدول الحصص المطبق في كل يوم — نفس الجدول يمكن أن يخدم عدة أيام.
      </p>

      <ul className="mb-4 divide-y divide-slate-100">
        {rows.map((row) => (
          <li key={row.weekday} className="flex flex-wrap items-center gap-3 py-3">
            <label className="flex w-28 items-center gap-2 text-sm font-medium">
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
                className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm"
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
        <p role="alert" className="mb-3 text-sm text-red-700">
          {saveMutation.error.message}
        </p>
      )}
      {saveMutation.isSuccess && <p className="mb-3 text-sm text-emerald-700">تم الحفظ.</p>}

      {canWrite && (
        <Button onClick={() => saveMutation.mutate()} disabled={saveMutation.isPending}>
          حفظ أيام الدراسة
        </Button>
      )}
    </section>
  );
}
