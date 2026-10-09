import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Alert } from "@/components/Alert";
import { ErrorState } from "@/components/ErrorState";
import { updateSchoolFeature, type SchoolDetail } from "@/features/platform/api";
import { SCHOOL_FEATURES, type SchoolFeature } from "@/features/platform/schoolFeatures";

export function SchoolFeaturesPanel({ detail, canManage }: { detail: SchoolDetail; canManage: boolean }) {
  const client = useQueryClient();
  const action = useMutation({
    mutationFn: ({ feature, enabled }: { feature: SchoolFeature; enabled: boolean }) => updateSchoolFeature(detail.id, feature, enabled),
    onSuccess: async (result) => {
      client.setQueryData<SchoolDetail>(["platform", "school", result.school_id], (current) => current ? { ...current, feature_access: result.features } : current);
      await client.invalidateQueries({ queryKey: ["platform", "school", result.school_id] });
    },
  });
  return <section aria-label="تفعيل ميزات المدرسة" className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
    <h3 className="font-black text-slate-900">ميزات المدرسة</h3>
    <p className="mt-2 text-xs leading-6 text-slate-500">تحكم مستقل لهذه المدرسة. الميزة غير المفعّلة تظهر للمدرسة معطّلة مع تنبيه يلزم اشتراك. يبقى قرار التفعيل محفوظًا عند تغيير الباقة أو تجديد الاشتراك.</p>
    <div className="mt-4 space-y-3">
      {SCHOOL_FEATURES.map((feature) => {
        const enabled = detail.feature_access?.[feature.key] ?? true;
        const Icon = feature.icon;
        return <div key={feature.key} className={`flex items-start gap-3 rounded-xl border p-3 ${enabled ? "border-teal-100 bg-teal-50/50" : "border-slate-200 bg-slate-50"}`}>
          <span className={`grid size-10 shrink-0 place-items-center rounded-xl ${enabled ? "bg-teal-100 text-teal-800" : "bg-slate-200 text-slate-400"}`}><Icon aria-hidden size={19} /></span>
          <div className="min-w-0 flex-1"><p className="text-sm font-bold text-slate-900">{feature.label}</p><p className="mt-1 text-xs leading-5 text-slate-500">{feature.description}</p><span className={`mt-2 inline-block text-xs font-bold ${enabled ? "text-teal-700" : "text-slate-500"}`}>{enabled ? "مفعّلة" : "غير مفعّلة — يلزم اشتراك"}</span></div>
          <button type="button" role="switch" aria-label={`تفعيل ${feature.label}`} aria-checked={enabled} disabled={!canManage || action.isPending} onClick={() => action.mutate({ feature: feature.key, enabled: !enabled })} className={`relative mt-1 inline-flex h-7 w-12 shrink-0 items-center rounded-full p-1 transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-700 disabled:cursor-not-allowed disabled:opacity-50 ${enabled ? "bg-teal-700" : "bg-slate-300"}`}>
            <span className={`size-5 rounded-full bg-white shadow-sm transition-transform ${enabled ? "-translate-x-5" : "translate-x-0"}`} />
          </button>
        </div>;
      })}
    </div>
    {!canManage && <p className="mt-3 text-xs leading-6 text-slate-500">تعديل التفعيل متاح لمن لديه صلاحية إدارة الاشتراكات في المنصة.</p>}
    {action.isPending && <p role="status" className="mt-3 text-sm text-teal-800">جارٍ حفظ حالة الميزة…</p>}
    {action.isError && <div className="mt-3"><ErrorState error={action.error} /></div>}
    {action.isSuccess && <div className="mt-3"><Alert tone="success" title="تم حفظ حالة الميزة" live /></div>}
  </section>;
}
