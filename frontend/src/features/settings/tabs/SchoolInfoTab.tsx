import { useMutation } from "@tanstack/react-query";
import { useRef, useState, type FormEvent } from "react";

import { ApiError } from "@/api/client";
import { Button } from "@/components/Button";
import { ErrorState } from "@/components/ErrorState";
import { Spinner } from "@/components/Spinner";
import { TextField } from "@/components/TextField";
import {
  patchSettings,
  STAGE_LABELS,
  uploadLogo,
  type SchoolSettingsPayload,
} from "@/features/settings/api";
import { useInvalidateSchoolData, useSettingsQuery } from "@/features/settings/hooks";

interface TabProps {
  canWrite: boolean;
}

export function SchoolInfoTab({ canWrite }: TabProps) {
  const settings = useSettingsQuery();

  if (settings.isPending) return <Spinner />;
  if (settings.isError) return <ErrorState error={settings.error} />;

  return (
    <SchoolInfoForm
      key={settings.data.school.id}
      initial={settings.data}
      canWrite={canWrite}
    />
  );
}

function SchoolInfoForm({
  initial,
  canWrite,
}: {
  initial: SchoolSettingsPayload;
  canWrite: boolean;
}) {
  const invalidate = useInvalidateSchoolData();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [form, setForm] = useState(() => ({
    name: initial.school.name,
    ministry_school_number: initial.ministry_school_number,
    education_stage: initial.education_stage as string,
    city: initial.city,
    official_principal_name: initial.official_principal_name,
  }));

  const saveMutation = useMutation({
    mutationFn: () => patchSettings(form),
    onSuccess: () => void invalidate("settings"),
  });

  const logoMutation = useMutation({
    mutationFn: (file: File) => uploadLogo(file),
    onSuccess: () => void invalidate("settings"),
  });

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    saveMutation.mutate();
  }

  const staff = initial.staff;

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <form
        onSubmit={handleSubmit}
        className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm"
      >
        <h3 className="mb-4 font-bold">بيانات المدرسة</h3>

        <TextField
          label="اسم المدرسة"
          value={form.name}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
          disabled={!canWrite}
          className="mb-3"
        />
        <TextField
          label="الرقم الوزاري (اختياري)"
          value={form.ministry_school_number}
          onChange={(e) => setForm({ ...form, ministry_school_number: e.target.value })}
          disabled={!canWrite}
          className="mb-3"
        />
        <div className="mb-3 flex flex-col gap-1">
          <label htmlFor="stage-select" className="text-sm font-medium text-slate-700">
            المرحلة التعليمية
          </label>
          <select
            id="stage-select"
            value={form.education_stage}
            onChange={(e) => setForm({ ...form, education_stage: e.target.value })}
            disabled={!canWrite}
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
          >
            {Object.entries(STAGE_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </div>
        <TextField
          label="المدينة"
          value={form.city}
          onChange={(e) => setForm({ ...form, city: e.target.value })}
          disabled={!canWrite}
          className="mb-3"
        />
        <TextField
          label="اسم المدير الرسمي (للطباعة — اختياري)"
          value={form.official_principal_name}
          onChange={(e) => setForm({ ...form, official_principal_name: e.target.value })}
          disabled={!canWrite}
          className="mb-4"
        />

        {saveMutation.error instanceof ApiError && (
          <p role="alert" className="mb-3 text-sm text-red-700">
            {saveMutation.error.message}
          </p>
        )}
        {saveMutation.isSuccess && (
          <p className="mb-3 text-sm text-emerald-700">تم حفظ البيانات.</p>
        )}

        {canWrite && (
          <Button type="submit" disabled={saveMutation.isPending}>
            {saveMutation.isPending ? "جارٍ الحفظ..." : "حفظ البيانات"}
          </Button>
        )}
      </form>

      <div className="space-y-6">
        <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
          <h3 className="mb-4 font-bold">شعار المدرسة</h3>
          {initial.logo_url ? (
            <img
              src={initial.logo_url}
              alt="شعار المدرسة"
              className="mb-3 h-24 w-24 rounded-lg border border-slate-200 object-contain"
            />
          ) : (
            <p className="mb-3 text-sm text-slate-500">لا يوجد شعار.</p>
          )}
          {canWrite && (
            <>
              <input
                ref={fileInputRef}
                type="file"
                accept="image/png,image/jpeg,image/webp"
                className="hidden"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) logoMutation.mutate(file);
                }}
              />
              <Button
                variant="secondary"
                onClick={() => fileInputRef.current?.click()}
                disabled={logoMutation.isPending}
              >
                {logoMutation.isPending ? "جارٍ الرفع..." : "رفع شعار (PNG/JPG/WEBP)"}
              </Button>
              {logoMutation.isError && (
                <p role="alert" className="mt-2 text-sm text-red-700">
                  {logoMutation.error.message}
                </p>
              )}
            </>
          )}
        </section>

        <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
          <h3 className="mb-4 font-bold">الطاقم الإداري (من العضويات — للعرض فقط)</h3>
          <dl className="space-y-2 text-sm">
            <div>
              <dt className="font-medium text-slate-500">مدير المدرسة</dt>
              <dd>{staff.managers.join("، ") || "—"}</dd>
            </div>
            <div>
              <dt className="font-medium text-slate-500">الوكلاء</dt>
              <dd>{staff.vice_principals.join("، ") || "—"}</dd>
            </div>
            <div>
              <dt className="font-medium text-slate-500">المرشدون الطلابيون</dt>
              <dd>{staff.counselors.join("، ") || "—"}</dd>
            </div>
          </dl>
        </section>
      </div>
    </div>
  );
}
