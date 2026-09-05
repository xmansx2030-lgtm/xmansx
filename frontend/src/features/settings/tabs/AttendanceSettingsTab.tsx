import { useMutation } from "@tanstack/react-query";
import { BellRing, Clock3, RotateCcw } from "lucide-react";
import { useState, type FormEvent } from "react";

import { ApiError } from "@/api/client";
import { Button } from "@/components/Button";
import { ErrorState } from "@/components/ErrorState";
import { Spinner } from "@/components/Spinner";
import { patchSettings } from "@/features/settings/api";
import { useInvalidateSchoolData, useSettingsQuery } from "@/features/settings/hooks";

export function AttendanceSettingsTab({ canWrite }: { canWrite: boolean }) {
  const settings = useSettingsQuery();

  if (settings.isPending) return <Spinner />;
  if (settings.isError) return <ErrorState error={settings.error} />;

  return (
    <AttendanceSettingsForm
      key={settings.data.school.id}
      initialAlert={settings.data.unprepared_period_alert_minutes}
      initialWindow={settings.data.attendance_edit_window_minutes}
      canWrite={canWrite}
    />
  );
}

function AttendanceSettingsForm({
  initialAlert,
  initialWindow,
  canWrite,
}: {
  initialAlert: number;
  initialWindow: number;
  canWrite: boolean;
}) {
  const invalidate = useInvalidateSchoolData();
  const [alertMinutes, setAlertMinutes] = useState(initialAlert);
  const [editWindow, setEditWindow] = useState(initialWindow);
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [savedValues, setSavedValues] = useState({ alert: initialAlert, window: initialWindow });
  const isDirty = alertMinutes !== savedValues.alert || editWindow !== savedValues.window;

  const saveMutation = useMutation({
    mutationFn: () =>
      patchSettings({
        unprepared_period_alert_minutes: alertMinutes,
        attendance_edit_window_minutes: editWindow,
      }),
    onSuccess: () => {
      setSavedValues({ alert: alertMinutes, window: editWindow });
      void invalidate("settings");
    },
  });

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setFieldError(null);
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
      className="max-w-3xl rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6"
    >
      <h3 className="font-bold">سياسة تسجيل الحضور</h3>
      <p className="mb-5 mt-1 text-sm text-slate-500">حدد متى يظهر تنبيه عدم التحضير والمدة المتاحة للمعلم للتعديل.</p>

      <div className="grid gap-4 md:grid-cols-2">
        <section className="rounded-2xl border border-slate-200 bg-slate-50/70 p-4">
          <div className="mb-3 flex items-center gap-2"><BellRing aria-hidden size={18} className="text-amber-600" /><label htmlFor="alert-minutes" className="text-sm font-bold text-slate-800">إظهار تنبيه عدم التحضير بعد</label></div>
          <p className="mb-3 text-xs leading-5 text-slate-500">يظهر للإدارة إذا لم يسجل المعلم الحضور بعد بداية الحصة.</p>
          <div className="flex items-center gap-2"><input id="alert-minutes" type="number" min={1} max={120} value={alertMinutes} onChange={(e) => setAlertMinutes(Number(e.target.value))} disabled={!canWrite} className="w-24 border border-slate-300 px-3 py-2 text-sm" /><span className="text-sm font-medium text-slate-600">دقيقة</span></div>
          {canWrite && <div className="mt-3 flex flex-wrap gap-1.5">{[10, 15, 20, 30].map((value) => <button key={value} type="button" onClick={() => setAlertMinutes(value)} className={`rounded-lg px-2.5 py-1 text-xs font-bold ${alertMinutes === value ? "bg-blue-600 text-white" : "bg-white text-slate-600 ring-1 ring-slate-200 hover:ring-blue-300"}`}>{value} د</button>)}</div>}
        </section>

        <section className="rounded-2xl border border-slate-200 bg-slate-50/70 p-4">
          <div className="mb-3 flex items-center gap-2"><Clock3 aria-hidden size={18} className="text-blue-700" /><label htmlFor="edit-window" className="text-sm font-bold text-slate-800">مهلة تعديل التحضير</label></div>
          <p className="mb-3 text-xs leading-5 text-slate-500">الفترة التي يستطيع خلالها المعلم تصحيح سجل الحضور بعد اعتماده.</p>
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
      {saveMutation.isSuccess && <p role="status" className="mt-4 rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-sm font-medium text-emerald-700">تم حفظ سياسة التحضير.</p>}

      {canWrite && (
        <div className="mt-5 flex flex-wrap gap-2 border-t border-slate-100 pt-4"><Button type="submit" disabled={saveMutation.isPending || !isDirty}>حفظ الإعدادات</Button>{isDirty && <Button type="button" variant="secondary" onClick={() => { setAlertMinutes(savedValues.alert); setEditWindow(savedValues.window); setFieldError(null); }}><RotateCcw aria-hidden size={16} /> تراجع</Button>}</div>
      )}
    </form>
  );
}
