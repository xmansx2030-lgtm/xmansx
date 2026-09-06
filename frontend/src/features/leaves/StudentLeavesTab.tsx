import { useQuery } from "@tanstack/react-query";
import { CalendarDays, Clock3, DoorOpen } from "lucide-react";

import { ErrorState } from "@/components/ErrorState";
import { Spinner } from "@/components/Spinner";
import { schoolScopedKey } from "@/features/auth/useMe";
import { getStudentLeaves } from "@/features/leaves/api";
import { useActiveSchoolId, useActiveSchoolType } from "@/features/settings/hooks";

export function StudentLeavesTab({ studentId }: { studentId: number }) {
  const schoolId = useActiveSchoolId();
  const schoolType = useActiveSchoolType();
  const leaves = useQuery({
    queryKey: schoolScopedKey(schoolId, "student-leaves", "student", studentId),
    queryFn: ({ signal }) => getStudentLeaves({ student: studentId }, signal),
    enabled: schoolId > 0,
  });
  if (leaves.isPending) return <Spinner />;
  if (leaves.isError) return <ErrorState error={leaves.error} />;
  if (leaves.data.results.length === 0) return <div className="rounded-2xl border border-slate-200 bg-white p-8 text-center"><DoorOpen aria-hidden size={28} className="mx-auto text-slate-300" /><p className="mt-3 font-bold text-slate-700">لا توجد استئذانات مسجلة {schoolType === "GIRLS" ? "لهذه الطالبة" : "لهذا الطالب"}.</p></div>;
  return <div className="space-y-3" data-testid="student-leaves-tab">{leaves.data.results.map((leave) => <article key={leave.id} className={`rounded-2xl border p-4 shadow-sm ${leave.status === "ACTIVE" ? "border-blue-100 bg-white" : "border-slate-200 bg-slate-50"}`}><div className="flex flex-wrap items-start justify-between gap-3"><div><div className="flex flex-wrap items-center gap-2"><strong className="text-slate-900">{leave.weekday_label}</strong><span className={`rounded-full px-2 py-0.5 text-xs font-bold ${leave.status === "ACTIVE" ? "bg-emerald-50 text-emerald-700" : "bg-slate-200 text-slate-600"}`}>{leave.status_label}</span></div><p className="mt-2 text-sm leading-6 text-slate-800">{leave.reason}</p></div><div className="text-end text-xs text-slate-500"><p className="inline-flex items-center gap-1"><CalendarDays aria-hidden size={14} />{leave.leave_date}</p><p className="mt-1 flex items-center justify-end gap-1 font-bold text-blue-800"><Clock3 aria-hidden size={14} />وقت الخروج {leave.leave_time}</p></div></div><p className="mt-3 border-t border-slate-100 pt-3 text-xs text-slate-500">سجله: {leave.recorded_by_name ?? "—"}{leave.cancellation_reason ? ` · سبب الإلغاء: ${leave.cancellation_reason}` : ""}</p></article>)}</div>;
}
