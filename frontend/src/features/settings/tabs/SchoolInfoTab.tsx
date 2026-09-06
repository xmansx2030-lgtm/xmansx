import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Building2, ImagePlus, RotateCcw, UsersRound } from "lucide-react";
import { useRef, useState, type FormEvent } from "react";

import { ApiError } from "@/api/client";
import { Button } from "@/components/Button";
import { ErrorState } from "@/components/ErrorState";
import { Spinner } from "@/components/Spinner";
import { TextField } from "@/components/TextField";
import { ME_QUERY_KEY } from "@/features/auth/useMe";
import {
  patchSettings,
  STAGE_LABELS,
  uploadLogo,
  type SchoolSettingsPayload,
} from "@/features/settings/api";
import { useInvalidateSchoolData, useSettingsQuery } from "@/features/settings/hooks";
import { roleLabel, rolePluralLabel } from "@/utils/roles";

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
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const initialForm = {
    name: initial.school.name,
    school_type: initial.school.school_type,
    ministry_school_number: initial.ministry_school_number,
    education_stage: initial.education_stage as string,
    city: initial.city,
    official_principal_name: initial.official_principal_name,
  };
  const [form, setForm] = useState(initialForm);
  const [savedForm, setSavedForm] = useState(initialForm);
  const isDirty = JSON.stringify(form) !== JSON.stringify(savedForm);

  const saveMutation = useMutation({
    mutationFn: () => patchSettings(form),
    onSuccess: () => {
      setSavedForm(form);
      void invalidate("settings");
      void queryClient.invalidateQueries({ queryKey: ME_QUERY_KEY });
    },
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
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1.2fr)_minmax(18rem,0.8fr)]">
      <form
        onSubmit={handleSubmit}
        className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6"
      >
        <div className="mb-5 flex items-start gap-3">
          <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-blue-50 text-blue-700"><Building2 aria-hidden size={20} /></span>
          <div><h3 className="font-bold">البيانات الرسمية</h3><p className="mt-1 text-sm text-slate-500">تظهر هذه البيانات في المنصة والتقارير المطبوعة.</p></div>
        </div>

        <TextField
          label="اسم المدرسة"
          value={form.name}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
          disabled={!canWrite}
          className="mb-3"
        />
        <div className="mb-3 flex flex-col gap-1">
          <label htmlFor="school-type-select" className="text-sm font-bold text-slate-700">
            نوع المدرسة
          </label>
          <select
            id="school-type-select"
            value={form.school_type}
            onChange={(e) => setForm({ ...form, school_type: e.target.value as "BOYS" | "GIRLS" })}
            disabled={!canWrite}
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
          >
            <option value="BOYS">بنين</option>
            <option value="GIRLS">بنات</option>
          </select>
          <p className="text-xs text-slate-500">يحدد صيغة مسميات الأدوار في واجهات المدرسة وتقاريرها.</p>
        </div>
        <TextField
          label="الرقم الوزاري (اختياري)"
          value={form.ministry_school_number}
          onChange={(e) => setForm({ ...form, ministry_school_number: e.target.value })}
          disabled={!canWrite}
          className="mb-3"
        />
        <div className="mb-3 flex flex-col gap-1">
          <label htmlFor="stage-select" className="text-sm font-bold text-slate-700">
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
          label={`اسم ${roleLabel("SCHOOL_MANAGER", form.school_type)} الرسمي (للطباعة — اختياري)`}
          value={form.official_principal_name}
          onChange={(e) => setForm({ ...form, official_principal_name: e.target.value })}
          disabled={!canWrite}
          className="mb-4"
        />

        {saveMutation.error instanceof ApiError && (
          <p role="alert" className="mb-3 rounded-xl border border-red-100 bg-red-50 p-3 text-sm text-red-700">
            {saveMutation.error.message}
          </p>
        )}
        {saveMutation.isSuccess && (
          <p role="status" className="mb-3 rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-sm font-medium text-emerald-700">تم حفظ بيانات المدرسة بنجاح.</p>
        )}

        {canWrite && (
          <div className="flex flex-wrap gap-2 border-t border-slate-100 pt-4">
            <Button type="submit" disabled={saveMutation.isPending || !isDirty}>{saveMutation.isPending ? "جارٍ الحفظ..." : "حفظ البيانات"}</Button>
            {isDirty && <Button type="button" variant="secondary" onClick={() => setForm(savedForm)}><RotateCcw aria-hidden size={16} /> التراجع عن التغييرات</Button>}
          </div>
        )}
      </form>

      <div className="space-y-6">
        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
          <div className="mb-4 flex items-center gap-3"><span className="grid size-10 place-items-center rounded-xl bg-blue-50 text-blue-700"><ImagePlus aria-hidden size={20} /></span><div><h3 className="font-bold">شعار المدرسة</h3><p className="text-xs text-slate-500">يستخدم في المستندات والتقارير.</p></div></div>
          {initial.logo_url ? (
            <img
              src={initial.logo_url}
              alt="شعار المدرسة"
              className="mb-4 h-28 w-28 rounded-2xl border border-slate-200 bg-slate-50 object-contain p-2"
            />
          ) : (
            <div className="mb-4 grid min-h-28 place-items-center rounded-2xl border border-dashed border-slate-300 bg-slate-50 text-center text-sm text-slate-500">لا يوجد شعار مرفوع</div>
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
                <ImagePlus aria-hidden size={17} /> {logoMutation.isPending ? "جارٍ الرفع..." : initial.logo_url ? "تغيير الشعار" : "رفع الشعار"}
              </Button>
              {logoMutation.isError && (
                <p role="alert" className="mt-2 text-sm text-red-700">
                  {logoMutation.error.message}
                </p>
              )}
              <p className="mt-2 text-xs text-slate-400">PNG أو JPG أو WEBP، ويفضل شعار مربع بخلفية شفافة.</p>
            </>
          )}
        </section>

        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
          <div className="mb-4 flex items-center gap-3"><span className="grid size-10 place-items-center rounded-xl bg-slate-100 text-slate-600"><UsersRound aria-hidden size={20} /></span><div><h3 className="font-bold">الطاقم الإداري</h3><p className="text-xs text-slate-500">للعرض فقط، ويُدار من صفحة الموظفين.</p></div></div>
          <dl className="space-y-2 text-sm">
            <div className="rounded-xl bg-slate-50 p-3">
              <dt className="font-medium text-slate-500">{roleLabel("SCHOOL_MANAGER", form.school_type)}</dt>
              <dd>{staff.managers.join("، ") || "—"}</dd>
            </div>
            <div className="rounded-xl bg-slate-50 p-3">
              <dt className="font-medium text-slate-500">{rolePluralLabel("VICE_PRINCIPAL", form.school_type)}</dt>
              <dd>{staff.vice_principals.join("، ") || "—"}</dd>
            </div>
            <div className="rounded-xl bg-slate-50 p-3">
              <dt className="font-medium text-slate-500">{rolePluralLabel("COUNSELOR", form.school_type)}</dt>
              <dd>{staff.counselors.join("، ") || "—"}</dd>
            </div>
          </dl>
        </section>
      </div>
    </div>
  );
}
