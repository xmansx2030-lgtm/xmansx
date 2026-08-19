import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { ApiError } from "@/api/client";
import { Button } from "@/components/Button";
import { ErrorState } from "@/components/ErrorState";
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

export function DeviceRosterSyncPage() {
  const schoolId = useActiveSchoolId();
  const me = useMe();
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
  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold">مزامنة طلاب أجهزة الحضور</h1>
        <p className="mt-1 text-sm text-slate-600">المصدر: الطلاب النشطون ذوو القيد الفعال في العام الدراسي الحالي.</p>
      </div>
      <div className="flex flex-wrap items-end gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <label className="flex flex-col gap-1 text-sm">الجهاز
          <select value={deviceId} onChange={(event) => setDeviceId(event.target.value ? Number(event.target.value) : "")} className="rounded-lg border border-slate-300 px-3 py-2">
            <option value="">اختر جهازًا</option>
            {(devices.data ?? []).filter((device) => device.is_active).map((device) => <option key={device.id} value={device.id}>{device.name}</option>)}
          </select>
        </label>
        <Button disabled={!canWrite || deviceId === "" || analyze.isPending} onClick={() => analyze.mutate()}>فحص ومقارنة</Button>
        {!canWrite && <span className="text-sm text-slate-500">المعاينة متاحة للمدير فقط.</span>}
      </div>
      {error && <p role="alert" className="text-sm text-red-700">{error instanceof ApiError ? error.message : "تعذر تنفيذ العملية."}</p>}
      {job.data && <JobSummary job={job.data} canWrite={canWrite} onApprove={() => approve.mutate()} onRetry={() => retry.mutate()} />}
      {job.data && job.data.status !== "ANALYZING" && (
        <div className="space-y-3">
          <div className="flex flex-wrap gap-2">
              {ACTION_FILTERS.map(([value, label]) => <button key={value} type="button" onClick={() => setAction(value)} className={`rounded-lg border px-3 py-1.5 text-sm ${action === value ? "border-blue-700 bg-blue-50 text-blue-700" : "border-slate-300"}`}>{label}</button>)}
          </div>
          <RosterItems items={items.data ?? []} />
        </div>
      )}
    </div>
  );
}

function JobSummary({ job, canWrite, onApprove, onRetry }: { job: Awaited<ReturnType<typeof getRosterJob>>; canWrite: boolean; onApprove: () => void; onRetry: () => void }) {
  return <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"><div className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="font-bold">{job.device_name}</h2><p className="text-sm text-slate-500">الحالة: {job.status}</p></div><div className="flex gap-2">{canWrite && job.status === "READY_FOR_REVIEW" && <Button onClick={onApprove}>اعتماد المزامنة</Button>}{canWrite && job.status === "PARTIALLY_FAILED" && <Button variant="secondary" onClick={onRetry}>إعادة محاولة الفاشل</Button>}</div></div><div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-5"><Count label="متطابق" value={job.matched_count} /><Count label="إضافة" value={job.create_count} /><Count label="تحديث" value={job.update_count} /><Count label="إزالة" value={job.delete_count} /><Count label="تعارض" value={job.conflict_count} /></div>{job.delete_count > 0 && <p className="mt-3 rounded-lg bg-amber-50 p-3 text-sm text-amber-900">ستتم إزالة المستخدمين من الجهاز فقط، ولن تُحذف بياناتهم التاريخية من المنصة.</p>}{job.conflict_count > 0 && <p className="mt-3 rounded-lg bg-red-50 p-3 text-sm text-red-900">التعارضات لا تنفذ تلقائيًا وتحتاج مراجعة يدوية.</p>}</div>;
}

function Count({ label, value }: { label: string; value: number }) {
  return <div className="rounded-lg bg-slate-50 p-3"><span className="block text-xs text-slate-500">{label}</span><strong className="text-xl">{value}</strong></div>;
}

function RosterItems({ items }: { items: RosterItem[] }) {
  return <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white"><table className="w-full text-sm"><thead><tr className="border-b text-slate-500"><th className="p-3 text-start">الطالب</th><th className="p-3 text-start">معرف الجهاز</th><th className="p-3 text-start">الإجراء</th><th className="p-3 text-start">السبب</th></tr></thead><tbody>{items.map((item) => <tr key={item.id} className="border-b"><td className="p-3">{item.student_name ?? "مستخدم غير معروف"}</td><td className="p-3" dir="ltr">{item.external_user_id}</td><td className="p-3">{ACTION_LABELS[item.action]}</td><td className="p-3 text-slate-600">{item.reason || "-"}</td></tr>)}{items.length === 0 && <tr><td colSpan={4} className="p-6 text-center text-slate-500">لا توجد عناصر.</td></tr>}</tbody></table></div>;
}
