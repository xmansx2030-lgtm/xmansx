import { useMutation } from "@tanstack/react-query";
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

  const saveMutation = useMutation({
    mutationFn: () =>
      patchSettings({
        unprepared_period_alert_minutes: alertMinutes,
        attendance_edit_window_minutes: editWindow,
      }),
    onSuccess: () => void invalidate("settings"),
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
      className="max-w-lg rounded-xl border border-slate-200 bg-white p-6 shadow-sm"
    >
      <h3 className="mb-1 font-bold">متابعة تسجيل الحضور</h3>
      <p className="mb-5 text-sm text-slate-500">
        هذه الإعدادات تحفظ الآن وتفعل عند بناء شاشات الحضور.
      </p>

      <div className="mb-4 flex flex-col gap-1">
        <label htmlFor="alert-minutes" className="text-sm font-medium text-slate-700">
          إظهار تنبيه «لم يتم التحضير» بعد بداية الحصة بـ (دقيقة)
        </label>
        <input
          id="alert-minutes"
          type="number"
          min={1}
          max={120}
          value={alertMinutes}
          onChange={(e) => setAlertMinutes(Number(e.target.value))}
          disabled={!canWrite}
          className="w-28 rounded-lg border border-slate-300 px-3 py-2 text-sm"
        />
      </div>

      <div className="mb-4 flex flex-col gap-1">
        <label htmlFor="edit-window" className="text-sm font-medium text-slate-700">
          السماح للمعلم بتعديل التحضير لمدة (دقيقة)
        </label>
        <input
          id="edit-window"
          type="number"
          min={0}
          max={120}
          value={editWindow}
          onChange={(e) => setEditWindow(Number(e.target.value))}
          disabled={!canWrite}
          className="w-28 rounded-lg border border-slate-300 px-3 py-2 text-sm"
        />
      </div>

      {fieldError && (
        <p role="alert" className="mb-3 text-sm text-red-700">
          {fieldError}
        </p>
      )}
      {saveMutation.error instanceof ApiError && (
        <p role="alert" className="mb-3 text-sm text-red-700">
          {saveMutation.error.message}
        </p>
      )}
      {saveMutation.isSuccess && <p className="mb-3 text-sm text-emerald-700">تم الحفظ.</p>}

      {canWrite && (
        <Button type="submit" disabled={saveMutation.isPending}>
          حفظ الإعدادات
        </Button>
      )}
    </form>
  );
}
