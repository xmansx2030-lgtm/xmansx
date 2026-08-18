import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";

import { acceptInvitation, declineInvitation } from "@/api/auth";
import { ApiError } from "@/api/client";
import { Button } from "@/components/Button";
import { Spinner } from "@/components/Spinner";
import { ME_QUERY_KEY, useLogout, useMe, useSwitchSchool } from "@/features/auth/useMe";
import { roleLabels } from "@/utils/roles";

export function SelectSchoolPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const me = useMe();
  const switchSchool = useSwitchSchool();
  const doLogout = useLogout();
  const [pendingId, setPendingId] = useState<number | null>(null);

  const switchMutation = useMutation({
    mutationFn: (schoolId: number) => switchSchool(schoolId),
    onSuccess: () => navigate("/", { replace: true }),
    onSettled: () => setPendingId(null),
  });

  const invitationMutation = useMutation({
    mutationFn: ({ id, action }: { id: number; action: "accept" | "decline" }) =>
      action === "accept" ? acceptInvitation(id) : declineInvitation(id),
    onSuccess: (updated) => {
      queryClient.setQueryData(ME_QUERY_KEY, updated);
    },
  });

  if (me.isPending) {
    return (
      <div className="flex min-h-dvh items-center justify-center">
        <Spinner />
      </div>
    );
  }
  if (me.isError) return <Navigate to="/login" replace />;
  if (me.data.must_change_password) return <Navigate to="/change-password" replace />;
  if (me.data.memberships.length === 0 && me.data.invitations.length === 0) {
    return <Navigate to="/" replace />;
  }

  const apiError = switchMutation.error instanceof ApiError ? switchMutation.error : null;

  return (
    <main className="flex min-h-dvh items-center justify-center bg-slate-50 p-4">
      <div className="w-full max-w-md">
        <h1 className="mb-1 text-center text-2xl font-black text-slate-800">اختر المدرسة</h1>
        <p className="mb-6 text-center text-sm text-slate-500">
          مرحباً {me.data.name}، اختر المدرسة التي تريد الدخول إليها
        </p>

        {apiError && (
          <p role="alert" className="mb-4 rounded-lg bg-red-50 p-3 text-sm text-red-700">
            {apiError.message}
          </p>
        )}

        {me.data.invitations.length > 0 && (
          <section className="mb-6" data-testid="invitations-section">
            <h2 className="mb-2 font-bold text-slate-700">دعوات مدارس</h2>
            <ul className="space-y-3">
              {me.data.invitations.map((invitation) => (
                <li
                  key={invitation.id}
                  className="rounded-2xl border border-amber-200 bg-amber-50 p-4"
                >
                  <p className="font-bold text-slate-800">{invitation.school.name}</p>
                  <p className="mb-3 text-sm text-slate-600">
                    تدعو حسابك للانضمام{" "}
                    {invitation.roles.length > 0 ? `(${roleLabels(invitation.roles)})` : ""}
                  </p>
                  {invitationMutation.error instanceof ApiError && (
                    <p role="alert" className="mb-2 text-sm text-red-700">
                      {invitationMutation.error.message}
                    </p>
                  )}
                  <div className="flex gap-2">
                    <Button
                      disabled={invitationMutation.isPending}
                      onClick={() =>
                        invitationMutation.mutate({ id: invitation.id, action: "accept" })
                      }
                    >
                      قبول
                    </Button>
                    <Button
                      variant="secondary"
                      disabled={invitationMutation.isPending}
                      onClick={() =>
                        invitationMutation.mutate({ id: invitation.id, action: "decline" })
                      }
                    >
                      رفض
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          </section>
        )}

        <ul className="space-y-3">
          {me.data.memberships.map((membership) => (
            <li key={membership.id}>
              <div className="flex items-center justify-between rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                <div>
                  <p className="font-bold text-slate-800">{membership.school.name}</p>
                  <p className="text-sm text-slate-500">{roleLabels(membership.roles)}</p>
                </div>
                <Button
                  onClick={() => {
                    setPendingId(membership.school.id);
                    switchMutation.mutate(membership.school.id);
                  }}
                  disabled={switchMutation.isPending}
                >
                  {pendingId === membership.school.id && switchMutation.isPending
                    ? "جارٍ الدخول..."
                    : "دخول"}
                </Button>
              </div>
            </li>
          ))}
        </ul>

        <div className="mt-6 text-center">
          <button
            type="button"
            className="text-sm text-slate-500 underline hover:text-slate-700"
            onClick={() => {
              void doLogout().then(() => navigate("/login", { replace: true }));
            }}
          >
            تسجيل الخروج
          </button>
        </div>
      </div>
    </main>
  );
}
