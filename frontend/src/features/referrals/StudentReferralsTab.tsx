import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Button } from "@/components/Button";
import { ErrorState } from "@/components/ErrorState";
import { Spinner } from "@/components/Spinner";
import { schoolScopedKey, useMe } from "@/features/auth/useMe";
import { getStudentReferrals } from "@/features/referrals/api";
import { ReferralCreateCard } from "@/features/referrals/ReferralCreateCard";
import { ReferralDetailCard } from "@/features/referrals/ReferralDetailCard";
import { ReferralsTable } from "@/features/referrals/ReferralsPage";
import { useActiveSchoolId } from "@/features/settings/hooks";

/** تبويب الإحالات داخل ملف الطالب — التحويل للمرشد للمدير/الوكيل (بند 45/118). */
export function StudentReferralsTab({
  studentId,
  studentName,
}: {
  studentId: number;
  studentName: string;
}) {
  const schoolId = useActiveSchoolId();
  const me = useMe();
  const queryClient = useQueryClient();
  const [creating, setCreating] = useState(false);
  const [selected, setSelected] = useState<number | null>(null);

  const canRefer =
    me.data?.roles.some(
      (role) => role === "SCHOOL_MANAGER" || role === "VICE_PRINCIPAL",
    ) ?? false;

  const list = useQuery({
    queryKey: schoolScopedKey(schoolId, "student-referrals", studentId),
    queryFn: ({ signal }) => getStudentReferrals(studentId, signal),
    enabled: schoolId > 0,
  });

  const refresh = () =>
    queryClient.invalidateQueries({
      queryKey: schoolScopedKey(schoolId, "student-referrals", studentId),
    });

  if (list.isError) return <ErrorState error={list.error} />;

  return (
    <div className="space-y-4" data-testid="student-referrals-tab">
      {canRefer && !creating && (
        <Button onClick={() => setCreating(true)} data-testid="profile-refer-student">
          تحويل إلى المرشد
        </Button>
      )}
      {creating && (
        <ReferralCreateCard
          student={{ id: studentId, name: studentName }}
          onCreated={(referralId) => {
            setCreating(false);
            setSelected(referralId);
            refresh();
          }}
          onContributed={(referralId) => {
            setCreating(false);
            setSelected(referralId);
            refresh();
          }}
          onCancel={() => setCreating(false)}
        />
      )}

      {list.isPending ? (
        <Spinner />
      ) : (
        <ReferralsTable
          rows={list.data?.results ?? []}
          onSelect={(id) => setSelected(selected === id ? null : id)}
          selectedId={selected}
          emptyText="لا توجد إحالات لهذا الطالب."
          testId="student-referrals-rows"
        />
      )}

      {selected !== null && (
        <ReferralDetailCard
          referralId={selected}
          onChanged={refresh}
          onClose={() => setSelected(null)}
        />
      )}
    </div>
  );
}
