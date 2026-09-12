import { useMutation } from "@tanstack/react-query";
import { CalendarClock, Plus, Save, Sparkles, Trash2 } from "lucide-react";
import type { ReactNode } from "react";
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
type GeneratedBreak = {
  enabled: boolean;
  label: string;
  afterPeriod: number;
  duration: number;
};
export type ScheduleGeneratorState = {
  startTime: string;
  periodCount: number;
  periodMinutes: number;
  gapMinutes: number;
  recess: GeneratedBreak;
  prayer: GeneratedBreak;
};

const PERIOD_NAMES = [
  "الأولى",
  "الثانية",
  "الثالثة",
  "الرابعة",
  "الخامسة",
  "السادسة",
  "السابعة",
  "الثامنة",
  "التاسعة",
  "العاشرة",
] as const;

const DEFAULT_GENERATOR: ScheduleGeneratorState = {
  startTime: "07:00",
  periodCount: 7,
  periodMinutes: 45,
  gapMinutes: 5,
  recess: { enabled: true, label: "الفسحة", afterPeriod: 3, duration: 20 },
  prayer: { enabled: true, label: "الصلاة", afterPeriod: 5, duration: 15 },
};

function timeToMinutes(value: string): number | null {
  const match = /^(\d{2}):(\d{2})$/.exec(value);
  if (!match) return null;
  const hours = Number(match[1]);
  const minutes = Number(match[2]);
  if (hours > 23 || minutes > 59) return null;
  return hours * 60 + minutes;
}

function minutesToTime(value: number): string {
  const normalized = ((value % 1440) + 1440) % 1440;
  const hours = Math.floor(normalized / 60);
  const minutes = normalized % 60;
  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}`;
}

function periodName(periodNumber: number): string {
  return `الحصة ${PERIOD_NAMES[periodNumber - 1] ?? periodNumber}`;
}

export function generatePeriodsFromSettings(settings: ScheduleGeneratorState): EditablePeriod[] {
  const start = timeToMinutes(settings.startTime);
  if (start === null) return [];

  const breaks = [settings.recess, settings.prayer]
    .filter((item) => item.enabled && item.duration > 0)
    .sort((a, b) => a.afterPeriod - b.afterPeriod || a.label.localeCompare(b.label));

  const rows: EditablePeriod[] = [];
  let cursor = start;
  for (let periodNumber = 1; periodNumber <= settings.periodCount; periodNumber++) {
    const classStart = cursor;
    const classEnd = classStart + settings.periodMinutes;
    rows.push({
      sequence: rows.length + 1,
      name: periodName(periodNumber),
      start_time: minutesToTime(classStart),
      end_time: minutesToTime(classEnd),
      is_attendance_period: true,
    });
    cursor = classEnd;

    for (const breakItem of breaks.filter((item) => item.afterPeriod === periodNumber)) {
      rows.push({
        sequence: rows.length + 1,
        name: breakItem.label.trim() || "فاصل",
        start_time: minutesToTime(cursor),
        end_time: minutesToTime(cursor + breakItem.duration),
        is_attendance_period: false,
      });
      cursor += breakItem.duration;
    }

    if (periodNumber < settings.periodCount) {
      cursor += settings.gapMinutes;
    }
  }
  return rows;
}

function validateGeneratorSettings(settings: ScheduleGeneratorState): string | null {
  if (timeToMinutes(settings.startTime) === null) return "حدد وقت بداية صحيح.";
  if (settings.periodCount < 1 || settings.periodCount > 10) return "عدد الحصص يجب أن يكون بين 1 و10.";
  if (settings.periodMinutes < 20 || settings.periodMinutes > 120) {
    return "مدة الحصة يجب أن تكون بين 20 و120 دقيقة.";
  }
  if (settings.gapMinutes < 0 || settings.gapMinutes > 30) {
    return "الفاصل بين الحصص يجب أن يكون بين 0 و30 دقيقة.";
  }
  for (const item of [settings.recess, settings.prayer]) {
    if (!item.enabled) continue;
    if (item.afterPeriod < 1 || item.afterPeriod >= settings.periodCount) {
      return `موضع «${item.label}» يجب أن يكون بعد حصة قائمة وقبل نهاية اليوم.`;
    }
    if (item.duration < 5 || item.duration > 90) {
      return `مدة «${item.label}» يجب أن تكون بين 5 و90 دقيقة.`;
    }
  }
  const generated = generatePeriodsFromSettings(settings);
  const firstGenerated = generated[0];
  const lastGenerated = generated[generated.length - 1];
  if (firstGenerated && lastGenerated && lastGenerated.end_time < firstGenerated.start_time) {
    return "الجدول الناتج يتجاوز منتصف الليل. استخدم أوقاتًا ضمن اليوم الدراسي نفسه.";
  }
  return validatePeriods(generated);
}

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
    const [startHour, startMinute] = p.start_time.split(":").map(Number) as [number, number];
    const [endHour, endMinute] = p.end_time.split(":").map(Number) as [number, number];
    const duration = endHour * 60 + endMinute - (startHour * 60 + startMinute);
    if (duration > 180) {
      return `مدة «${p.name}» غير معتادة (${duration} دقيقة). تحقق من وقتي البداية والنهاية.`;
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
            void invalidate("attendance", "current-period");
            void invalidate("attendance", "monitoring");
            void invalidate("dashboard");
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
  const [generator, setGenerator] = useState<ScheduleGeneratorState>(() => ({
    ...DEFAULT_GENERATOR,
    startTime: schedule.periods[0]?.start_time.slice(0, 5) ?? DEFAULT_GENERATOR.startTime,
  }));

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

  function applyGeneratedSchedule() {
    const error = validateGeneratorSettings(generator);
    setValidationError(error);
    if (error) return;
    setPeriods(generatePeriodsFromSettings(generator));
  }

  function save() {
    const error = validatePeriods(periods);
    setValidationError(error);
    if (!error) saveMutation.mutate();
  }

  return (
    <section
      data-testid="bell-schedule-card"
      className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
    >
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="font-bold">{schedule.name}</h3>
          <p className="mt-1 text-xs text-slate-500">
            {periods.filter((period) => period.is_attendance_period).length} حصص تحضير،{" "}
            {periods.filter((period) => !period.is_attendance_period).length} فواصل
          </p>
        </div>
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

      {canWrite && (
        <div className="mb-5 rounded-xl border border-blue-100 bg-blue-50/60 p-4">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-start gap-3">
              <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-white text-blue-700 shadow-sm">
                <CalendarClock aria-hidden size={20} />
              </span>
              <div>
                <h4 className="font-black text-slate-950">مولّد اليوم الدراسي</h4>
                <p className="mt-1 text-sm text-slate-600">
                  أدخل قواعد اليوم مرة واحدة، ثم دع النظام يبني الحصص والفسحة والصلاة.
                </p>
              </div>
            </div>
            <Button onClick={applyGeneratedSchedule}>
              <Sparkles aria-hidden size={17} />
              توليد الجدول
            </Button>
          </div>

          <div className="grid gap-3 md:grid-cols-4">
            <GeneratorField label="بداية اليوم">
              <input
                aria-label="بداية اليوم الدراسي"
                type="time"
                dir="ltr"
                value={generator.startTime}
                onChange={(e) => setGenerator((prev) => ({ ...prev, startTime: e.target.value }))}
                className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
              />
            </GeneratorField>
            <GeneratorField label="عدد الحصص">
              <input
                aria-label="عدد الحصص"
                type="number"
                min={1}
                max={10}
                value={generator.periodCount}
                onChange={(e) =>
                  setGenerator((prev) => ({ ...prev, periodCount: Number(e.target.value) }))
                }
                className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
              />
            </GeneratorField>
            <GeneratorField label="مدة الحصة">
              <NumberWithUnit
                label="مدة الحصة بالدقائق"
                value={generator.periodMinutes}
                min={20}
                max={120}
                onChange={(value) => setGenerator((prev) => ({ ...prev, periodMinutes: value }))}
              />
            </GeneratorField>
            <GeneratorField label="الفاصل القصير">
              <NumberWithUnit
                label="الفاصل بين الحصص بالدقائق"
                value={generator.gapMinutes}
                min={0}
                max={30}
                onChange={(value) => setGenerator((prev) => ({ ...prev, gapMinutes: value }))}
              />
            </GeneratorField>
          </div>

          <div className="mt-4 grid gap-3 lg:grid-cols-2">
            <BreakControls
              title="الفسحة"
              value={generator.recess}
              periodCount={generator.periodCount}
              onChange={(value) => setGenerator((prev) => ({ ...prev, recess: value }))}
            />
            <BreakControls
              title="الصلاة"
              value={generator.prayer}
              periodCount={generator.periodCount}
              onChange={(value) => setGenerator((prev) => ({ ...prev, prayer: value }))}
            />
          </div>
        </div>
      )}

      {/* جدول الحصص — يتحول لبطاقات ضمنيًا عبر التفاف الأعمدة على الشاشات الصغيرة */}
      <div className="overflow-x-auto">
        <table className="w-full min-w-135 text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-start text-slate-500">
              <th className="py-2 text-start">#</th>
              <th className="py-2 text-start">الاسم</th>
              <th className="py-2 text-start">البداية</th>
              <th className="py-2 text-start">النهاية</th>
              <th className="py-2 text-start">النوع</th>
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
                  <label className="inline-flex items-center gap-2 rounded-full bg-slate-50 px-3 py-1.5 text-xs font-bold text-slate-700 ring-1 ring-slate-200">
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
                    {period.is_attendance_period ? "حصة تحضير" : "فاصل"}
                  </label>
                </td>
                {canWrite && (
                  <td className="py-2">
                    <button
                      type="button"
                      aria-label={`حذف الفترة ${period.sequence}`}
                      onClick={() => removePeriod(index)}
                      className="inline-flex size-9 items-center justify-center rounded-lg text-red-600 hover:bg-red-50 focus-visible:outline-2 focus-visible:outline-red-500"
                    >
                      <Trash2 aria-hidden size={16} />
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
            <Plus aria-hidden size={17} />
            إضافة حصة
          </Button>
          <Button onClick={save} disabled={saveMutation.isPending}>
            <Save aria-hidden size={17} />
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

function GeneratorField({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <label className="block text-sm font-bold text-slate-700">
      {label}
      <span className="mt-1 block">{children}</span>
    </label>
  );
}

function NumberWithUnit({
  label,
  value,
  min,
  max,
  disabled = false,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  disabled?: boolean;
  onChange: (value: number) => void;
}) {
  return (
    <div className="flex overflow-hidden rounded-lg border border-slate-300 bg-white">
      <input
        aria-label={label}
        type="number"
        min={min}
        max={max}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(Number(e.target.value))}
        className="min-w-0 flex-1 border-0 px-3 py-2 text-sm focus:outline-none disabled:bg-slate-100"
      />
      <span className="grid min-w-14 place-items-center border-s border-slate-200 bg-slate-50 px-3 text-xs font-bold text-slate-500">
        دقيقة
      </span>
    </div>
  );
}

function BreakControls({
  title,
  value,
  periodCount,
  onChange,
}: {
  title: string;
  value: GeneratedBreak;
  periodCount: number;
  onChange: (value: GeneratedBreak) => void;
}) {
  const maxAfter = Math.max(1, periodCount - 1);
  return (
    <fieldset className="rounded-xl border border-slate-200 bg-white p-3">
      <legend className="px-1 text-sm font-black text-slate-900">{title}</legend>
      <label className="mb-3 flex items-center justify-between gap-3 text-sm font-bold text-slate-700">
        <span>إدراج ضمن الجدول</span>
        <input
          aria-label={`إدراج ${title}`}
          type="checkbox"
          checked={value.enabled}
          onChange={(e) => onChange({ ...value, enabled: e.target.checked })}
          className="size-5"
        />
      </label>
      <div className="grid gap-3 sm:grid-cols-3">
        <GeneratorField label="الاسم">
          <input
            aria-label={`اسم ${title}`}
            value={value.label}
            disabled={!value.enabled}
            onChange={(e) => onChange({ ...value, label: e.target.value })}
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm disabled:bg-slate-100"
          />
        </GeneratorField>
        <GeneratorField label="بعد الحصة">
          <input
            aria-label={`موضع ${title}`}
            type="number"
            min={1}
            max={maxAfter}
            value={Math.min(value.afterPeriod, maxAfter)}
            disabled={!value.enabled}
            onChange={(e) => onChange({ ...value, afterPeriod: Number(e.target.value) })}
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm disabled:bg-slate-100"
          />
        </GeneratorField>
        <GeneratorField label="المدة">
          <NumberWithUnit
            label={`مدة ${title} بالدقائق`}
            value={value.duration}
            min={5}
            max={90}
            disabled={!value.enabled}
            onChange={(duration) => onChange({ ...value, duration })}
          />
        </GeneratorField>
      </div>
    </fieldset>
  );
}
