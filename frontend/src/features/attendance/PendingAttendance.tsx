import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { adaptivePollingInterval, POLLING } from "@/app/polling";

import { getPendingSessions } from "./api";
import { sectionLabel } from "./sectionLabel";
import { schoolScopedKey, useMe } from "@/features/auth/useMe";

export function PendingAttendance({ sectionId }: { sectionId?: number }) {
  const me = useMe();
  const schoolId = me.data?.active_school?.id ?? 0;
  const pending = useQuery({
    queryKey: schoolScopedKey(schoolId, "attendance", "pending-sessions", me.data?.id),
    queryFn: ({ signal }) => getPendingSessions(signal),
    enabled: schoolId > 0 && (me.data?.roles.includes("TEACHER") ?? false),
    staleTime: 15_000,
    refetchInterval: adaptivePollingInterval(POLLING.teacherPeriod),
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: "always",
  });
  const sessions = (pending.data ?? []).filter((row) => sectionId === undefined || row.section.id === sectionId);
  if (pending.isError) {
    return <p role="status" className="rounded-xl bg-amber-50 p-3 text-sm text-amber-900">تعذر تحديث جلساتك غير المعتمدة. <button type="button" className="font-bold underline" onClick={() => void pending.refetch()}>إعادة المحاولة</button></p>;
  }
  if (!sessions.length) return null;
  return (
    <section data-testid="pending-attendance" className="space-y-3 rounded-2xl border border-amber-200 bg-amber-50 p-4 sm:p-5">
      <div><h2 className="font-black text-amber-950">تحضير بدأته ولم تعتمدْه</h2><p className="mt-1 text-sm text-amber-900">استكمل جلسات اليوم حتى بعد انتهاء الحصة. راجع الغياب ثم اضغط إرسال التحضير.</p></div>
      <ul className="space-y-2">
        {sessions.map((session) => <li key={session.id}>
          <Link to={`/attendance/section/${session.section.id}?session=${session.id}`} className="flex min-h-12 flex-wrap items-center justify-between gap-2 rounded-xl border border-amber-200 bg-white p-3 text-sm font-bold text-slate-900">
            <span>{sectionLabel(session.section.grade_name, session.section.name, session.section.department)} · {session.period.name}</span><span className="text-teal-700">استكمال التحضير</span>
          </Link>
        </li>)}
      </ul>
    </section>
  );
}
