import { useMutation } from "@tanstack/react-query";
import { BellRing, Clock3, RotateCcw, Sunrise } from "lucide-react";
import { useState, type FormEvent } from "react";

import { ApiError } from "@/api/client";
import { Button } from "@/components/Button";
import { ErrorState } from "@/components/ErrorState";
import { Spinner } from "@/components/Spinner";
import { patchSettings } from "@/features/settings/api";
import { useInvalidateSchoolData, useSettingsQuery } from "@/features/settings/hooks";
import type { SchoolType } from "@/types/auth";

export function AttendanceSettingsTab({ canWrite }: { canWrite: boolean }) {
  const settings = useSettingsQuery();

  if (settings.isPending) return <Spinner />;
  if (settings.isError) return <ErrorState error={settings.error} />;

  return (
    <AttendanceSettingsForm
      key={settings.data.school.id}
      initialAlert={settings.data.unprepared_period_alert_minutes}
      initialWindow={settings.data.attendance_edit_window_minutes}
      initialStartTime={settings.data.school_day_start_time}
      initialGrace={settings.data.morning_late_grace_minutes}
      schoolType={settings.data.school.school_type}
      canWrite={canWrite}
    />
  );
}

function AttendanceSettingsForm({
  initialAlert,
  initialWindow,
  initialStartTime,
  initialGrace,
  schoolType,
  canWrite,
}: {
  initialAlert: number;
  initialWindow: number;
  initialStartTime: string;
  initialGrace: number;
  schoolType: SchoolType;
  canWrite: boolean;
}) {
  const invalidate = useInvalidateSchoolData();
  const [alertMinutes, setAlertMinutes] = useState(initialAlert);
  const [editWindow, setEditWindow] = useState(initialWindow);
  const [startTime, setStartTime] = useState(initialStartTime);
  const [graceMinutes, setGraceMinutes] = useState(initialGrace);
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [savedValues, setSavedValues] = useState({
    alert: initialAlert,
    window: initialWindow,
    startTime: initialStartTime,
    grace: initialGrace,
  });
  const isDirty =
    alertMinutes !== savedValues.alert ||
    editWindow !== savedValues.window ||
    startTime !== savedValues.startTime ||
    graceMinutes !== savedValues.grace;
  const lateAfterTime = addMinutes(startTime, graceMinutes);

  const saveMutation = useMutation({
    mutationFn: () =>
      patchSettings({
        unprepared_period_alert_minutes: alertMinutes,
        attendance_edit_window_minutes: editWindow,
        school_day_start_time: startTime,
        morning_late_grace_minutes: graceMinutes,
      }),
    onSuccess: () => {
      setSavedValues({
        alert: alertMinutes,
        window: editWindow,
        startTime,
        grace: graceMinutes,
      });
      void invalidate("settings");
      void invalidate("morning");
    },
  });

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setFieldError(null);
    if (!/^([01]\d|2[0-3]):[0-5]\d$/.test(startTime)) {
      setFieldError("حدد وقتًا صحيحًا لبداية الدوام الصباحي.");
      return;
    }
    if (!Number.isInteger(graceMinutes) || graceMinutes < 0 || graceMinutes > 120) {
      setFieldError("فترة السماح الصباحية يجب أن تكون بين 0 و120 دقيقة.");
      return;
    }
    if (alertMinutes < 1 || alertMinutes > 120) {
      setFieldError("تنبيه عدم التحضير يجب أن يكون بين 1 و120 دقيقة.");
      return;
    }
    if (editWindow < 0 || editWindow > 120) {
      setFieldError("مهلة التعديل يجب أن تكون بين 0 و120 دقيقة.");
      return;
    }
    saveMutation.mutate();
  }

  return (
    <form
      onSubmit={handleSubmit}
      noValidate
      className="max-w-4xl rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6"
    >
      <h3 className="font-bold">سياسات الحضور والتأخر</h3>
      <p className="mb-5 mt-1 text-sm text-slate-500">اضبط احتساب الوصول الصباحي، وتنبيهات تحضير الحصص، ومهلة التعديل.</p>

      <section className="mb-6 rounded-2xl border border-amber-200 bg-amber-50/60 p-4 sm:p-5" aria-labelledby="morning-policy-heading">
        <div className="mb-4 flex items-start gap-3">
          <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-amber-100 text-amber-700"><Sunrise aria-hidden size={20} /></span>
          <div>
            <h4 id="morning-policy-heading" className="font-black text-slate-900">احتساب التأخر الصباحي</h4>
            <p className="mt-1 text-xs leading-5 text-slate-600">هذه القيم هي نفسها الظاهرة في شاشة متابعة الحضور الصباحي، ويُطبّق التغيير على الوصول المسجل بعد الحفظ.</p>
          </div>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <label htmlFor="school-day-start-time" className="text-sm font-bold text-slate-800">
            وقت بداية الدوام
            <input
              id="school-day-start-time"
              type="time"
              value={startTime}
              onChange={(event) => setStartTime(event.target.value)}
              disabled={!canWrite}
              className="mt-2 block min-h-11 w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-base font-black tabular-nums"
              dir="ltr"
            />
          </label>
          <label htmlFor="morning-grace-minutes" className="text-sm font-bold text-slate-800">
            فترة السماح بعد بداية الدوام
            <span className="mt-2 flex items-center gap-2">
              <input
                id="morning-grace-minutes"
                aria-label="فترة السماح بعد بداية الدوام"
                type="number"
                min={0}
                max={120}
                step={1}
                value={graceMinutes}
                onChange={(event) => setGraceMinutes(Number(event.target.value))}
                disabled={!canWrite}
                className="min-h-11 w-28 rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm"
              />
              <span className="font-medium text-slate-600">دقيقة</span>
            </span>
          </label>
        </div>

        {lateAfterTime && (
          <p className="mt-4 rounded-xl border border-amber-200 bg-white px-4 py-3 text-sm text-slate-700" data-testid="morning-policy-preview">
            الوصول حتى <strong dir="ltr">{lateAfterTime}</strong> في الوقت، ويُصنّف الوصول بعده متأخرًا.
          </p>
        )}
      </section>

      <div className="mb-3">
        <h4 className="font-black text-slate-900">تحضير الحصص</h4>
        <p className="mt-1 text-xs text-slate-500">حدد متى يظهر تنبيه عدم التحضير والمدة المتاحة {schoolType === "GIRLS" ? "للمعلمة" : "للمعلم"} للتعديل.</p>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <section className="rounded-2xl border border-slate-200 bg-slate-50/70 p-4">
          <div className="mb-3 flex items-center gap-2"><BellRing aria-hidden size={18} className="text-amber-600" /><label htmlFor="alert-minutes" className="text-sm font-bold text-slate-800">إظهار تنبيه عدم التحضير بعد</label></div>
          <p className="mb-3 text-xs leading-5 text-slate-500">يظهر للإدارة إذا لم {schoolType === "GIRLS" ? "تسجل المعلمة" : "يسجل المعلم"} الحضور بعد بداية الحصة.</p>
          <div className="flex items-center gap-2"><input id="alert-minutes" type="number" min={1} max={120} value={alertMinutes} onChange={(e) => setAlertMinutes(Number(e.target.value))} disabled={!canWrite} className="w-24 border border-slate-300 px-3 py-2 text-sm" /><span className="text-sm font-medium text-slate-600">دقيقة</span></div>
          {canWrite && <div className="mt-3 flex flex-wrap gap-1.5">{[10, 15, 20, 30].map((value) => <button key={value} type="button" onClick={() => setAlertMinutes(value)} className={`rounded-lg px-2.5 py-1 text-xs font-bold ${alertMinutes === value ? "bg-blue-600 text-white" : "bg-white text-slate-600 ring-1 ring-slate-200 hover:ring-blue-300"}`}>{value} د</button>)}</div>}
        </section>

        <section className="rounded-2xl border border-slate-200 bg-slate-50/70 p-4">
          <div className="mb-3 flex items-center gap-2"><Clock3 aria-hidden size={18} className="text-blue-700" /><label htmlFor="edit-window" className="text-sm font-bold text-slate-800">مهلة تعديل التحضير</label></div>
          <p className="mb-3 text-xs leading-5 text-slate-500">الفترة التي {schoolType === "GIRLS" ? "تستطيع خلالها المعلمة" : "يستطيع خلالها المعلم"} تصحيح سجل الحضور بعد اعتماده.</p>
          <div className="flex items-center gap-2"><input id="edit-window" type="number" min={0} max={120} value={editWindow} onChange={(e) => setEditWindow(Number(e.target.value))} disabled={!canWrite} className="w-24 border border-slate-300 px-3 py-2 text-sm" /><span className="text-sm font-medium text-slate-600">دقيقة</span></div>
          {canWrite && <div className="mt-3 flex flex-wrap gap-1.5">{[0, 10, 15, 30].map((value) => <button key={value} type="button" onClick={() => setEditWindow(value)} className={`rounded-lg px-2.5 py-1 text-xs font-bold ${editWindow === value ? "bg-blue-600 text-white" : "bg-white text-slate-600 ring-1 ring-slate-200 hover:ring-blue-300"}`}>{value === 0 ? "بدون تعديل" : `${value} د`}</button>)}</div>}
        </section>
      </div>

      {fieldError && (
        <p role="alert" className="mt-4 rounded-xl border border-red-100 bg-red-50 p-3 text-sm text-red-700">
          {fieldError}
        </p>
      )}
      {saveMutation.error instanceof ApiError && (
        <p role="alert" className="mt-4 rounded-xl border border-red-100 bg-red-50 p-3 text-sm text-red-700">
          {saveMutation.error.message}
        </p>
      )}
      {saveMutation.isSuccess && <p role="status" className="mt-4 rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-sm font-medium text-emerald-700">تم حفظ سياسات الحضور.</p>}

      {canWrite && (
        <div className="mt-5 flex flex-wrap gap-2 border-t border-slate-100 pt-4"><Button type="submit" disabled={saveMutation.isPending || !isDirty}>حفظ الإعدادات</Button>{isDirty && <Button type="button" variant="secondary" onClick={() => { setAlertMinutes(savedValues.alert); setEditWindow(savedValues.window); setStartTime(savedValues.startTime); setGraceMinutes(savedValues.grace); setFieldError(null); }}><RotateCcw aria-hidden size={16} /> تراجع</Button>}</div>
      )}
    </form>
  );
}

function addMinutes(time: string, minutes: number): string | null {
  const match = /^([01]\d|2[0-3]):([0-5]\d)$/.exec(time);
  if (!match || !Number.isInteger(minutes) || minutes < 0 || minutes > 120) return null;
  const totalMinutes = (Number(match[1]) * 60 + Number(match[2]) + minutes) % (24 * 60);
  return `${String(Math.floor(totalMinutes / 60)).padStart(2, "0")}:${String(totalMinutes % 60).padStart(2, "0")}`;
}
