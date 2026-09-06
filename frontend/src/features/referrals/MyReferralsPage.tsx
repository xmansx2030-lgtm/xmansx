import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, CheckCircle2, Clock3, Send } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import { ErrorState } from "@/components/ErrorState";
import { PageHeader } from "@/components/PageHeader";
import { Spinner } from "@/components/Spinner";
import { schoolScopedKey, useMe } from "@/features/auth/useMe";
import { getMyReferrals } from "@/features/referrals/api";
import { ReferralDetailCard } from "@/features/referrals/ReferralDetailCard";
import { ReferralsTable } from "@/features/referrals/ReferralsPage";
import { useActiveSchoolId } from "@/features/settings/hooks";
import { roleLabel } from "@/utils/roles";

/** «إحالاتي» — ما أنشأه المستخدم أو ساهم فيه فقط (بند 42).
 *
 *  هذه صفحة المعلم: لا يرى منها إحالات زملائه ولا صندوق وارد المرشد.
 */
export function MyReferralsPage() {
  const schoolId = useActiveSchoolId();
  const me = useMe();
  const schoolType = me.data?.active_school?.school_type ?? "BOYS";
  const queryClient = useQueryClient();
  const [selected, setSelected] = useState<number | null>(null);

  const list = useQuery({
    queryKey: schoolScopedKey(schoolId, "my-referrals"),
    queryFn: ({ signal }) => getMyReferrals({}, signal),
    enabled: schoolId > 0,
  });

  if (list.isError) return <ErrorState error={list.error} />;

  const rows = list.data?.results ?? [];
  const closedCount = rows.filter((row) => row.status === "CLOSED" || row.status === "CANCELLED").length;
  const activeCount = rows.length - closedCount;

  return (
    <div className="space-y-5">
      <PageHeader
        icon={Send}
        eyebrow={`مساحة ${roleLabel("TEACHER", schoolType)}`}
        title="إحالاتي"
        description="تابع الإحالات التي أنشأتها أو أضفت إليها ملاحظة، واعرف حالتها لدى المرشد دون كشف ملفات لا تخصك."
        tone="teacher"
        badge={list.isPending ? "جارٍ التحديث" : `${rows.length} إحالة`}
        actions={(
          <Link to="/" className="inline-flex min-h-11 items-center gap-2 rounded-xl bg-white/10 px-4 text-sm font-bold text-white ring-1 ring-white/15 transition hover:bg-white/15">
            <ArrowRight aria-hidden size={17} />
            العودة للتحضير
          </Link>
        )}
      />

      {list.isPending ? (
        <Spinner />
      ) : (
        <>
          <section className="grid gap-3 sm:grid-cols-3" aria-label={`ملخص إحالات ${roleLabel("TEACHER", schoolType)}`}>
            <div className="rounded-2xl border border-blue-100 bg-blue-50/70 p-4">
              <Clock3 aria-hidden size={20} className="mb-3 text-blue-600" />
              <p className="text-2xl font-black text-slate-900">{activeCount}</p>
              <p className="text-sm font-medium text-slate-600">قيد المتابعة</p>
            </div>
            <div className="rounded-2xl border border-emerald-100 bg-emerald-50/70 p-4">
              <CheckCircle2 aria-hidden size={20} className="mb-3 text-emerald-600" />
              <p className="text-2xl font-black text-slate-900">{closedCount}</p>
              <p className="text-sm font-medium text-slate-600">مغلقة أو مكتملة</p>
            </div>
            <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
              <Send aria-hidden size={20} className="mb-3 text-slate-500" />
              <p className="text-2xl font-black text-slate-900">{rows.length}</p>
              <p className="text-sm font-medium text-slate-600">إجمالي إحالاتك</p>
            </div>
          </section>
          <ReferralsTable
            rows={rows}
            onSelect={(id) => setSelected(selected === id ? null : id)}
            selectedId={selected}
            emptyText="لم تنشئ أي إحالة بعد. يمكنك التحويل للمرشد من شاشة التحضير."
            testId="my-referrals-rows"
          />
        </>
      )}

      {selected !== null && (
        <ReferralDetailCard
          referralId={selected}
          onChanged={() =>
            queryClient.invalidateQueries({
              queryKey: schoolScopedKey(schoolId, "my-referrals"),
            })
          }
          onClose={() => setSelected(null)}
        />
      )}
    </div>
  );
}
