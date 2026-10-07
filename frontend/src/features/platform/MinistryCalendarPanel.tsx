import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { apiRequest } from "@/api/client";
import { Button } from "@/components/Button";
import { ErrorState } from "@/components/ErrorState";
import { Spinner } from "@/components/Spinner";
import type { MinistryCalendarStatus } from "@/features/settings/api";
import { MinistryCalendarCard } from "@/features/settings/tabs/MinistryCalendarCard";

export function MinistryCalendarPanel({ canManage }: { canManage: boolean }) {
  const client = useQueryClient();
  const source = useQuery({ queryKey: ["platform", "ministry-calendar"], queryFn: ({ signal }) => apiRequest<MinistryCalendarStatus>("/platform/ministry-calendar/", { signal }) });
  const sync = useMutation({
    mutationFn: () => apiRequest<{ source: MinistryCalendarStatus }>("/platform/ministry-calendar/", { method: "POST" }),
    onSuccess: (result) => client.setQueryData(["platform", "ministry-calendar"], result.source),
  });
  if (source.isPending) return <Spinner />;
  if (source.isError) return <ErrorState error={source.error} />;
  return <div className="space-y-4">
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-white p-5">
      <div><h2 className="text-xl font-black text-slate-950">مزامنة التقويم الرسمي</h2><p className="mt-2 text-sm text-slate-600">تُحدّث بيانات الوزارة كل ست ساعات، وتُراجع مواعيد التفعيل كل خمس دقائق. حدّد نطاق كل مدرسة من بياناتها.</p></div>
      {canManage && <Button onClick={() => sync.mutate()} disabled={sync.isPending}>{sync.isPending ? "جارٍ التحقق من الوزارة..." : "مزامنة من الوزارة الآن"}</Button>}
    </div>
    {sync.isError && <ErrorState error={sync.error} />}
    <MinistryCalendarCard data={source.data} />
    <div className="rounded-2xl border border-slate-200 bg-white p-5"><h3 className="font-black text-slate-900">الأعوام الموجودة في المصدر</h3><div className="mt-3 grid gap-3 sm:grid-cols-2">{source.data.calendars.map((calendar) => <div key={calendar.name} className="rounded-xl border border-slate-100 bg-slate-50 p-3"><strong>{calendar.name}</strong><p className="mt-1 text-sm text-slate-600">{calendar.status === "READY" ? "المواعيد مكتملة وفق المصدر والقاعدة المعتمدة" : calendar.status === "INCOMPLETE" ? "بانتظار اكتمال النشر من الوزارة" : "لا يطابق نظام الفصلين المعتمد"}</p></div>)}</div></div>
  </div>;
}

export function SchoolCalendarScopePanel({ schoolId, canManage }: { schoolId: number; canManage: boolean }) {
  const client = useQueryClient();
  const scope = useQuery({ queryKey: ["platform", "calendar-scope", schoolId], queryFn: ({ signal }) => apiRequest<MinistryCalendarStatus>(`/platform/schools/${schoolId}/calendar-scope/`, { signal }) });
  const save = useMutation({
    mutationFn: (data: { profile: MinistryCalendarStatus["profile"]; scope_note: string }) => apiRequest<MinistryCalendarStatus>(`/platform/schools/${schoolId}/calendar-scope/`, { method: "PATCH", body: data }),
    onSuccess: (result) => client.setQueryData(["platform", "calendar-scope", schoolId], result),
  });
  if (scope.isPending) return <Spinner />;
  if (scope.isError) return <ErrorState error={scope.error} />;
  return <div className="rounded-2xl border border-teal-200 bg-teal-50 p-4">
    <h3 className="font-black text-teal-950">نطاق التقويم الدراسي</h3>
    <p className="mt-2 text-xs leading-5 text-teal-900">التقويم الوطني للمدارس الحكومية المطابقة له فقط. تحقّق من التقاويم المحلية لمكة والمدينة وجدة والطائف، ومن تقويم المدارس الأهلية والدولية قبل الربط.</p>
    <ScopeForm key={`${scope.data.profile}:${scope.data.scope_note}`} data={scope.data} canManage={canManage} pending={save.isPending} onSave={save.mutate} />
    {save.isError && <ErrorState error={save.error} />}
    {save.isSuccess && <p role="status" className="mt-3 text-sm font-bold text-teal-800">تم حفظ نطاق المدرسة.</p>}
  </div>;
}

function ScopeForm({ data, canManage, pending, onSave }: { data: MinistryCalendarStatus; canManage: boolean; pending: boolean; onSave: (value: { profile: MinistryCalendarStatus["profile"]; scope_note: string }) => void }) {
  const [profile, setProfile] = useState(data.profile);
  const [note, setNote] = useState(data.scope_note);
  return <form className="mt-3 space-y-3" onSubmit={(event) => { event.preventDefault(); onSave({ profile, scope_note: note }); }}>
    <label className="block text-xs font-bold text-teal-950">التقويم المطبق
      <select value={profile} onChange={(event) => setProfile(event.target.value as MinistryCalendarStatus["profile"])} disabled={!canManage || pending} className="mt-1 min-h-11 w-full rounded-xl border border-teal-200 bg-white px-3 text-sm"><option value="UNCONFIRMED">لم يُحدد نطاق المدرسة</option><option value="NATIONAL">التقويم الوطني — مزامنة وتفعيل تلقائي</option><option value="EXCEPTION">تقويم خاص أو محلي معتمد</option></select>
    </label>
    <label className="block text-xs font-bold text-teal-950">توثيق مطابقة نطاق المدرسة
      <textarea value={note} onChange={(event) => setNote(event.target.value)} disabled={!canManage || pending} required={profile !== "UNCONFIRMED"} minLength={profile !== "UNCONFIRMED" ? 10 : undefined} maxLength={500} className="mt-1 min-h-20 w-full rounded-xl border border-teal-200 bg-white p-3 text-sm" />
    </label>
    {canManage && <Button type="submit" disabled={pending}>{pending ? "جارٍ الحفظ..." : "حفظ نطاق التقويم"}</Button>}
    {data.outcome && <MinistryCalendarCard data={data} />}
  </form>;
}
