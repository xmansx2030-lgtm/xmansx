import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Send } from "lucide-react";
import { useState } from "react";

import { ErrorState } from "@/components/ErrorState";
import { PageHeader } from "@/components/PageHeader";
import { Spinner } from "@/components/Spinner";
import { schoolScopedKey } from "@/features/auth/useMe";
import { getMyReferrals } from "@/features/referrals/api";
import { ReferralDetailCard } from "@/features/referrals/ReferralDetailCard";
import { ReferralsTable } from "@/features/referrals/ReferralsPage";
import { useActiveSchoolId } from "@/features/settings/hooks";

/** «إحالاتي» — ما أنشأه المستخدم أو ساهم فيه فقط (بند 42).
 *
 *  هذه صفحة المعلم: لا يرى منها إحالات زملائه ولا صندوق وارد المرشد.
 */
export function MyReferralsPage() {
  const schoolId = useActiveSchoolId();
  const queryClient = useQueryClient();
  const [selected, setSelected] = useState<number | null>(null);

  const list = useQuery({
    queryKey: schoolScopedKey(schoolId, "my-referrals"),
    queryFn: ({ signal }) => getMyReferrals({}, signal),
    enabled: schoolId > 0,
  });

  if (list.isError) return <ErrorState error={list.error} />;

  return (
    <div className="space-y-5">
      <PageHeader icon={Send} eyebrow="مساحة المعلم" title="إحالاتي" description="تابع الإحالات التي أنشأتها أو أضفت إليها ملاحظة، واعرف حالتها لدى المرشد دون كشف ملفات لا تخصك." tone="teacher" />

      {list.isPending ? (
        <Spinner />
      ) : (
        <ReferralsTable
          rows={list.data?.results ?? []}
          onSelect={(id) => setSelected(selected === id ? null : id)}
          emptyText="لم تنشئ أي إحالة بعد. يمكنك التحويل للمرشد من شاشة التحضير."
          testId="my-referrals-rows"
        />
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
