import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, ListChecks, RefreshCw, ShieldCheck } from "lucide-react";
import { useState } from "react";

import { ApiError } from "@/api/client";
import { Button } from "@/components/Button";
import { ErrorState } from "@/components/ErrorState";
import { PageHeader } from "@/components/PageHeader";
import { Spinner } from "@/components/Spinner";
import { schoolScopedKey, useMe } from "@/features/auth/useMe";
import { useActiveSchoolId } from "@/features/settings/hooks";
import {
  analyzeDeviceRoster,
  approveRosterJob,
  getDevices,
  getRosterItems,
  getRosterJob,
  retryRosterJob,
  type RosterItem,
} from "@/features/devices/api";
import { studentLabel, studentPluralLabel } from "@/utils/roles";

const ACTION_LABELS: Record<string, string> = {
  MATCHED: "متطابق",
  CREATE: "إضافة",
  UPDATE: "تحديث",
  DELETE: "إزالة",
  CONFLICT: "تعارض",
};
const ACTION_FILTERS = [
  ["ALL", "الكل"],
  ["CREATE", "إضافة"],
  ["UPDATE", "تحديث"],
  ["DELETE", "إزالة"],
  ["CONFLICT", "تعارض"],
  ["MATCHED", "متطابق"],
] as const;

const JOB_STATUS_LABELS: Record<string, string> = {
  ANALYZING: "جارٍ الفحص",
  READY_FOR_REVIEW: "جاهزة للمراجعة",
  APPROVED: "تم الاعتماد",
  RUNNING: "جارٍ التنفيذ",
  COMPLETED: "اكتملت",
  PARTIALLY_FAILED: "اكتملت جزئيًا",
  FAILED: "فشلت",
};

export function DeviceRosterSyncPage() {
  const schoolId = useActiveSchoolId();
  const me = useMe();
  const schoolType = me.data?.active_school?.school_type ?? "BOYS";
  const queryClient = useQueryClient();
  const [deviceId, setDeviceId] = useState<number | "">("");
  const [jobId, setJobId] = useState<number | null>(null);
  const [action, setAction] = useState("ALL");
  const canWrite = me.data?.roles.includes("SCHOOL_MANAGER") ?? false;

  const devices = useQuery({
    queryKey: schoolScopedKey(schoolId, "attendance-devices"),
    queryFn: ({ signal }) => getDevices(signal),
    enabled: schoolId > 0,
  });
  const job = useQuery({
    queryKey: schoolScopedKey(schoolId, "device-roster-job", jobId),
    queryFn: ({ signal }) => getRosterJob(jobId!, signal),
    enabled: jobId !== null,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "ANALYZING" || status === "APPROVED" || status === "RUNNING" ? 3000 : false;
    },
  });
  const items = useQuery({
    queryKey: schoolScopedKey(schoolId, "device-roster-items", jobId, action),
    queryFn: ({ signal }) => getRosterItems(jobId!, action === "ALL" ? undefined : action, signal),
    enabled: jobId !== null && job.data?.status !== "ANALYZING",
  });
  const analyze = useMutation({
    mutationFn: () => analyzeDeviceRoster(Number(deviceId)),
    onSuccess: (next) => setJobId(next.id),
  });
  const approve = useMutation({
    mutationFn: () => approveRosterJob(jobId!),
    onSuccess: (next) => {
      queryClient.setQueryData(schoolScopedKey(schoolId, "device-roster-job", jobId), next);
    },
  });
  const retry = useMutation({
    mutationFn: () => retryRosterJob(jobId!),
    onSuccess: (next) => {
      queryClient.setQueryData(schoolScopedKey(schoolId, "device-roster-job", jobId), next);
    },
  });

  if (devices.isPending) return <Spinner />;
  if (devices.isError) return <ErrorState error={devices.error} />;

  const error = analyze.error ?? approve.error ?? retry.error;
  const activeDevices = (devices.data ?? []).filter((device) => device.is_active);
  return (
    <div className="space-y-5">
      <PageHeader
        icon={RefreshCw}
        eyebrow="سلامة بيانات الأجهزة"
        title={`مزامنة ${schoolType === "GIRLS" ? "طالبات" : "طلاب"} أجهزة الحضور`}
        description="افحص الفروقات أولًا، راجع الإضافات والتحديثات والإزالات، ثم اعتمد التنفيذ بقرار واضح."
        tone="operational"
        badge={`${activeDevices.length} أجهزة متاحة`}
        meta={<><span className="inline-flex items-center gap-1"><ShieldCheck aria-hidden size={14} /> لا تنفيذ قبل الاعتماد</span><span aria-hidden>•</span><span>المصدر: {studentPluralLabel(schoolType)} {schoolType === "GIRLS" ? "النشطات" : "النشطون"} في العام الحالي</span></>}
      >
        <ol className="grid gap-2 text-xs font-bold text-slate-200 sm:grid-cols-3"><li className="rounded-xl bg-white/5 px-3 py-2">1. اختر الجهاز وافحص</li><li className="rounded-xl bg-white/5 px-3 py-2">2. راجع الفروقات</li><li className="rounded-xl bg-white/5 px-3 py-2">3. اعتمد التنفيذ</li></ol>
      </PageHeader>
      <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
        <div className="mb-4 flex items-center gap-3"><span className="grid size-10 place-items-center rounded-xl bg-blue-50 text-blue-700"><ListChecks aria-hidden size={20} /></span><div><h2 className="font-black text-slate-950">1. اختيار الجهاز والفحص</h2><p className="text-xs text-slate-500">هذه الخطوة تبني معاينة فقط ولا تغيّر مستخدمي الجهاز.</p></div></div>
        <div className="flex flex-wrap items-end gap-3 rounded-2xl bg-slate-50 p-4">
        <label className="flex min-w-64 flex-1 flex-col gap-1 text-sm font-bold text-slate-700">الجهاز
          <select value={deviceId} onChange={(event) => setDeviceId(event.target.value ? Number(event.target.value) : "")} className="rounded-xl border border-slate-300 bg-white px-3 py-2.5 font-normal">
            <option value="">اختر جهازًا</option>
            {activeDevices.map((device) => <option key={device.id} value={device.id}>{device.name}</option>)}
          </select>
        </label>
        <Button disabled={!canWrite || deviceId === "" || analyze.isPending} onClick={() => analyze.mutate()}><RefreshCw aria-hidden size={16} className={analyze.isPending ? "animate-spin" : ""} />{analyze.isPending ? "جارٍ الفحص..." : "فحص ومقارنة"}</Button>
        {!canWrite && <span className="text-sm text-slate-500">المعاينة متاحة للمدير فقط.</span>}
        </div>
      </section>
      {error && <p role="alert" className="rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">{error instanceof ApiError ? error.message : "تعذر تنفيذ العملية."}</p>}
      {job.data && <JobSummary job={job.data} canWrite={canWrite} onApprove={() => approve.mutate()} onRetry={() => retry.mutate()} />}
      {job.data && job.data.status !== "ANALYZING" && (
        <div className="space-y-3">
          <div className="flex flex-wrap gap-2">
              {ACTION_FILTERS.map(([value, label]) => <button key={value} type="button" onClick={() => setAction(value)} className={`rounded-lg border px-3 py-1.5 text-sm ${action === value ? "border-blue-700 bg-blue-50 text-blue-700" : "border-slate-300"}`}>{label}</button>)}
          </div>
          <RosterItems items={items.data ?? []} studentTitle={studentLabel(schoolType, true)} />
        </div>
      )}
    </div>
  );
}

function JobSummary({ job, canWrite, onApprove, onRetry }: { job: Awaited<ReturnType<typeof getRosterJob>>; canWrite: boolean; onApprove: () => void; onRetry: () => void }) {
  return <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6"><div className="flex flex-wrap items-center justify-between gap-3"><div className="flex items-center gap-3"><span className="grid size-10 place-items-center rounded-xl bg-emerald-50 text-emerald-700"><CheckCircle2 aria-hidden size={20} /></span><div><h2 className="font-black text-slate-950">2. معاينة {job.device_name}</h2><p className="text-sm font-bold text-slate-500">الحالة: {JOB_STATUS_LABELS[job.status] ?? job.status}</p></div></div><div className="flex gap-2">{canWrite && job.status === "READY_FOR_REVIEW" && <Button onClick={onApprove}>اعتماد المزامنة</Button>}{canWrite && job.status === "PARTIALLY_FAILED" && <Button variant="secondary" onClick={onRetry}>إعادة محاولة الفاشل</Button>}</div></div>{job.status === "ANALYZING" && <p role="status" className="mt-4 flex items-start gap-2 rounded-xl border border-blue-100 bg-blue-50 p-3 text-sm leading-6 text-blue-900"><RefreshCw aria-hidden size={17} className="mt-0.5 shrink-0 animate-spin" />تم إرسال طلب الفحص، وينتظر النظام اتصال جسر المدرسة وقراءة مستخدمي الجهاز. قد يستغرق ذلك حتى نبضة الاتصال التالية.</p>}<div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-5"><Count label="متطابق" value={job.matched_count} /><Count label="إضافة" value={job.create_count} /><Count label="تحديث" value={job.update_count} /><Count label="إزالة" value={job.delete_count} /><Count label="تعارض" value={job.conflict_count} /></div>{job.delete_count > 0 && <p className="mt-3 flex items-start gap-2 rounded-xl bg-amber-50 p-3 text-sm text-amber-900"><AlertTriangle aria-hidden size={17} className="mt-0.5 shrink-0" />ستتم إزالة المستخدمين من الجهاز فقط، ولن تُحذف بياناتهم التاريخية من المنصة.</p>}{job.conflict_count > 0 && <p className="mt-3 flex items-start gap-2 rounded-xl bg-red-50 p-3 text-sm text-red-900"><AlertTriangle aria-hidden size={17} className="mt-0.5 shrink-0" />التعارضات لا تنفذ تلقائيًا وتحتاج مراجعة يدوية.</p>}</section>;
}

function Count({ label, value }: { label: string; value: number }) {
  return <div className="rounded-2xl bg-slate-50 p-3"><span className="block text-xs font-bold text-slate-500">{label}</span><strong className="text-xl text-slate-950">{value}</strong></div>;
}

function RosterItems({ items, studentTitle }: { items: RosterItem[]; studentTitle: string }) {
  return <div className="overflow-x-auto rounded-2xl border border-slate-200 bg-white shadow-sm"><table className="w-full text-sm"><thead><tr className="border-b bg-slate-50 text-slate-500"><th className="p-3 text-start">{studentTitle}</th><th className="p-3 text-start">معرف الجهاز</th><th className="p-3 text-start">الإجراء</th><th className="p-3 text-start">السبب</th></tr></thead><tbody>{items.map((item) => <tr key={item.id} className="border-b"><td className="p-3">{item.student_name ?? "مستخدم غير معروف"}</td><td className="p-3" dir="ltr">{item.external_user_id}</td><td className="p-3">{ACTION_LABELS[item.action]}</td><td className="p-3 text-slate-600">{item.reason || "لا يوجد"}</td></tr>)}{items.length === 0 && <tr><td colSpan={4} className="p-8 text-center text-slate-500">لا توجد فروقات ضمن هذا التصنيف.</td></tr>}</tbody></table></div>;
}
