import { useMutation } from "@tanstack/react-query";
import { useState } from "react";

import { ApiError } from "@/api/client";
import { Button } from "@/components/Button";
import { ErrorState } from "@/components/ErrorState";
import { Spinner } from "@/components/Spinner";
import {
  archiveSchedule,
  createSchedule,
  putWeekDays,
  replacePeriods,
  WEEKDAY_LABELS,
  type BellPeriod,
  type BellSchedule,
} from "@/features/settings/api";
import {
  useInvalidateSchoolData,
  useSchedulesQuery,
  useWeekDaysQuery,
} from "@/features/settings/hooks";

type EditablePeriod = Omit<BellPeriod, "id">;

/** تحقق فوري مطابق لقواعد الخادم: ترتيب مكرر، نهاية قبل بداية، تداخل. */
export function validatePeriods(periods: EditablePeriod[]): string | null {
  const sequences = periods.map((p) => p.sequence);
  if (new Set(sequences).size !== sequences.length) {
    return "يوجد تكرار في ترتيب الحصص.";
  }
  for (const p of periods) {
    if (!p.start_time || !p.end_time) return "أكمل أوقات جميع الحصص.";
    if (p.end_time <= p.start_time) {
      return `وقت نهاية «${p.name}» يجب أن يكون بعد بدايتها.`;
    }
  }
  const ordered = [...periods].sort((a, b) => a.start_time.localeCompare(b.start_time));
  for (let i = 1; i < ordered.length; i++) {
    const prev = ordered[i - 1];
    const curr = ordered[i];
    if (prev && curr && curr.start_time < prev.end_time) {
      return `تداخل في الأوقات بين «${prev.name}» و«${curr.name}».`;
    }
  }
  return null;
}

export function BellSchedulesTab({ canWrite }: { canWrite: boolean }) {
  const schedules = useSchedulesQuery();
  const invalidate = useInvalidateSchoolData();
  const [newName, setNewName] = useState("");

  const createMutation = useMutation({
    mutationFn: () => createSchedule({ name: newName.trim() }),
    onSuccess: () => {
      setNewName("");
      void invalidate("bell-schedules");
    },
  });

  if (schedules.isPending) return <Spinner />;
  if (schedules.isError) return <ErrorState error={schedules.error} />;

  return (
    <div className="space-y-6">
      {canWrite && (
        <form
          className="flex flex-wrap items-end gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm"
          onSubmit={(e) => {
            e.preventDefault();
            if (newName.trim()) createMutation.mutate();
          }}
        >
          <div className="flex flex-col gap-1">
            <label htmlFor="new-schedule-name" className="text-sm font-medium text-slate-700">
              اسم الجدول (مثل: الجدول العادي، جدول رمضان)
            </label>
            <input
              id="new-schedule-name"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
            />
          </div>
          <Button type="submit" disabled={createMutation.isPending}>
            إنشاء جدول
          </Button>
        </form>
      )}

      {schedules.data.length === 0 && <p className="text-slate-500">لا توجد جداول حصص بعد.</p>}

      {schedules.data.map((schedule) => (
        <ScheduleEditor
          key={schedule.id}
          schedule={schedule}
          canWrite={canWrite}
          onChanged={() => {
            void invalidate("bell-schedules");
            void invalidate("week-days");
          }}
        />
      ))}
    </div>
  );
}

function ScheduleEditor({
  schedule,
  canWrite,
  onChanged,
}: {
  schedule: BellSchedule;
  canWrite: boolean;
  onChanged: () => void;
}) {
  const weekDays = useWeekDaysQuery();
  const [periods, setPeriods] = useState<EditablePeriod[]>(() =>
    schedule.periods.map((p) => ({
      sequence: p.sequence,
      name: p.name,
      start_time: p.start_time.slice(0, 5),
      end_time: p.end_time.slice(0, 5),
      is_attendance_period: p.is_attendance_period,
    })),
  );
  const [validationError, setValidationError] = useState<string | null>(null);
  const [copyDays, setCopyDays] = useState<number[]>([]);

  const saveMutation = useMutation({
    mutationFn: () => replacePeriods(schedule.id, periods),
    onSuccess: onChanged,
  });

  const archiveMutation = useMutation({
    mutationFn: () => archiveSchedule(schedule.id),
    onSuccess: onChanged,
  });

  const applyToDaysMutation = useMutation({
    mutationFn: () => {
      const current = weekDays.data?.days ?? [];
      return putWeekDays(
        current.map((d) => ({
          weekday: d.weekday,
          is_school_day: copyDays.includes(d.weekday) ? true : d.is_school_day,
          bell_schedule_id: copyDays.includes(d.weekday) ? schedule.id : d.bell_schedule_id,
        })),
      );
    },
    onSuccess: () => {
      setCopyDays([]);
      onChanged();
    },
  });

  function addPeriod() {
    const last = periods[periods.length - 1];
    const nextSeq = periods.length + 1;
    setPeriods([
      ...periods,
      {
        sequence: nextSeq,
        name: `الحصة ${nextSeq}`,
        start_time: last?.end_time ?? "07:00",
        end_time: "",
        is_attendance_period: true,
      },
    ]);
  }

  function updatePeriod(index: number, patch: Partial<EditablePeriod>) {
    setPeriods((prev) => prev.map((p, i) => (i === index ? { ...p, ...patch } : p)));
  }

  function removePeriod(index: number) {
    setPeriods((prev) =>
      prev.filter((_, i) => i !== index).map((p, i) => ({ ...p, sequence: i + 1 })),
    );
  }

  function save() {
    const error = validatePeriods(periods);
    setValidationError(error);
    if (!error) saveMutation.mutate();
  }

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <h3 className="font-bold">{schedule.name}</h3>
        {canWrite && (
          <Button
            variant="danger"
            onClick={() => archiveMutation.mutate()}
            disabled={archiveMutation.isPending}
          >
            أرشفة الجدول
          </Button>
        )}
      </div>

      {/* جدول الحصص — يتحول لبطاقات ضمنيًا عبر التفاف الأعمدة على الشاشات الصغيرة */}
      <div className="overflow-x-auto">
        <table className="w-full min-w-[540px] text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-start text-slate-500">
              <th className="py-2 text-start">#</th>
              <th className="py-2 text-start">الاسم</th>
              <th className="py-2 text-start">البداية</th>
              <th className="py-2 text-start">النهاية</th>
              <th className="py-2 text-start">حصة تحضير؟</th>
              {canWrite && <th />}
            </tr>
          </thead>
          <tbody>
            {periods.map((period, index) => (
              <tr key={index} className="border-b border-slate-100">
                <td className="py-2">{period.sequence}</td>
                <td className="py-2">
                  <input
                    aria-label={`اسم الفترة ${period.sequence}`}
                    value={period.name}
                    disabled={!canWrite}
                    onChange={(e) => updatePeriod(index, { name: e.target.value })}
                    className="w-32 rounded border border-slate-300 px-2 py-1"
                  />
                </td>
                <td className="py-2">
                  <input
                    aria-label={`بداية الفترة ${period.sequence}`}
                    type="time"
                    dir="ltr"
                    value={period.start_time}
                    disabled={!canWrite}
                    onChange={(e) => updatePeriod(index, { start_time: e.target.value })}
                    className="rounded border border-slate-300 px-2 py-1"
                  />
                </td>
                <td className="py-2">
                  <input
                    aria-label={`نهاية الفترة ${period.sequence}`}
                    type="time"
                    dir="ltr"
                    value={period.end_time}
                    disabled={!canWrite}
                    onChange={(e) => updatePeriod(index, { end_time: e.target.value })}
                    className="rounded border border-slate-300 px-2 py-1"
                  />
                </td>
                <td className="py-2">
                  <input
                    aria-label={`فترة تحضير ${period.sequence}`}
                    type="checkbox"
                    checked={period.is_attendance_period}
                    disabled={!canWrite}
                    onChange={(e) =>
                      updatePeriod(index, { is_attendance_period: e.target.checked })
                    }
                    className="size-4"
                  />
                </td>
                {canWrite && (
                  <td className="py-2">
                    <button
                      type="button"
                      aria-label={`حذف الفترة ${period.sequence}`}
                      onClick={() => removePeriod(index)}
                      className="text-red-600 hover:underline"
                    >
                      حذف
                    </button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {validationError && (
        <p role="alert" className="mt-3 text-sm text-red-700">
          {validationError}
        </p>
      )}
      {saveMutation.error instanceof ApiError && (
        <p role="alert" className="mt-3 text-sm text-red-700">
          {saveMutation.error.message}
        </p>
      )}
      {saveMutation.isSuccess && !validationError && (
        <p className="mt-3 text-sm text-emerald-700">تم حفظ الحصص.</p>
      )}

      {canWrite && (
        <div className="mt-4 flex flex-wrap gap-2">
          <Button variant="secondary" onClick={addPeriod}>
            إضافة حصة
          </Button>
          <Button onClick={save} disabled={saveMutation.isPending}>
            حفظ الحصص
          </Button>
        </div>
      )}

      {canWrite && (
        <div className="mt-5 border-t border-slate-100 pt-4">
          <p className="mb-2 text-sm font-medium text-slate-700">استخدام هذا الجدول في:</p>
          <div className="flex flex-wrap gap-3">
            {WEEKDAY_LABELS.map((label, weekday) => (
              <label key={weekday} className="flex items-center gap-1 text-sm">
                <input
                  type="checkbox"
                  checked={copyDays.includes(weekday)}
                  onChange={(e) =>
                    setCopyDays((prev) =>
                      e.target.checked
                        ? [...prev, weekday]
                        : prev.filter((d) => d !== weekday),
                    )
                  }
                  className="size-4"
                />
                {label}
              </label>
            ))}
          </div>
          <Button
            variant="secondary"
            className="mt-3"
            disabled={copyDays.length === 0 || applyToDaysMutation.isPending}
            onClick={() => applyToDaysMutation.mutate()}
          >
            تطبيق على الأيام المحددة
          </Button>
          {applyToDaysMutation.isSuccess && (
            <p className="mt-2 text-sm text-emerald-700">تم ربط الجدول بالأيام المحددة.</p>
          )}
        </div>
      )}
    </section>
  );
}
