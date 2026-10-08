import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Building2, LogOut } from "lucide-react";
import { useState } from "react";
import { Navigate, useNavigate, useSearchParams } from "react-router-dom";

import { acceptInvitation, declineInvitation } from "@/api/auth";
import { ApiError } from "@/api/client";
import { Button } from "@/components/Button";
import { Spinner } from "@/components/Spinner";
import { safeReturnTo } from "@/features/auth/returnTo";
import { ME_QUERY_KEY, useLogout, useMe, useSwitchSchool } from "@/features/auth/useMe";
import { roleLabels } from "@/utils/roles";

export function SelectSchoolPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const me = useMe();
  const switchSchool = useSwitchSchool();
  const doLogout = useLogout();
  const [pendingId, setPendingId] = useState<number | null>(null);
  const returnTo = safeReturnTo(searchParams.get("returnTo"));

  const switchMutation = useMutation({
    mutationFn: (schoolId: number) => switchSchool(schoolId),
    onSuccess: () => navigate(returnTo ?? "/workspace", { replace: true }),
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
      <div className="auth-shell flex min-h-dvh items-center justify-center px-4">
        <div role="status" aria-label="جارٍ تحميل الحساب" className="rounded-2xl border border-white/10 bg-white/5 p-5 text-teal-100">
          <Spinner />
        </div>
      </div>
    );
  }
  if (me.isError) return <Navigate to="/login" replace />;
  if (me.data.must_change_password) return <Navigate to="/change-password" replace />;
  if (me.data.is_platform_admin) return <Navigate to="/platform" replace />;
  if (me.data.has_parent_portal && me.data.memberships.length === 0 && me.data.invitations.length === 0) return <Navigate to="/parent" replace />;
  if (me.data.memberships.length === 0 && me.data.invitations.length === 0) {
    return <Navigate to="/" replace />;
  }

  const apiError = switchMutation.error instanceof ApiError ? switchMutation.error : null;

  return (
    <main className="auth-shell flex min-h-dvh items-center justify-center overflow-x-hidden overflow-y-auto px-4 py-6 sm:px-8 sm:py-10">
      <div className="auth-card w-full min-w-0 max-w-xl rounded-3xl p-5 shadow-[0_24px_70px_rgba(3,27,24,0.18)] sm:p-9">
        <span className="mx-auto mb-5 grid size-12 place-items-center rounded-2xl bg-teal-50 text-teal-800 ring-1 ring-teal-100"><Building2 aria-hidden size={24} /></span>
        <p className="mb-1 text-center text-sm font-bold text-teal-800">مساحة العمل</p>
        <h1 className="text-center text-2xl font-black text-slate-900">اختر المدرسة</h1>
        <p className="mb-7 mt-2 text-center text-sm leading-6 text-slate-600">
          مرحباً {me.data.name}، اختر المدرسة التي تريد الدخول إليها
        </p>

        {apiError && (
          <p role="alert" className="mb-4 rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-800">
            {apiError.message}
          </p>
        )}

        {me.data.invitations.length > 0 && (
          <section className="mb-6" data-testid="invitations-section">
            <h2 className="mb-3 font-black text-slate-800">دعوات مدارس</h2>
            <ul className="space-y-3">
              {me.data.invitations.map((invitation) => (
                <li
                  key={invitation.id}
                  className="rounded-2xl border border-amber-200 bg-amber-50/80 p-4 shadow-sm sm:p-5"
                >
                  <p className="font-bold text-slate-800">{invitation.school.name}</p>
                  <p className="mb-3 text-sm text-slate-600">
                    تدعو حسابك للانضمام{" "}
                    {invitation.roles.length > 0 ? `(${roleLabels(invitation.roles, invitation.school.school_type)})` : ""}
                  </p>
                  {invitationMutation.error instanceof ApiError && (
                    <p role="alert" className="mb-2 text-sm text-red-700">
                      {invitationMutation.error.message}
                    </p>
                  )}
                  <div className="flex flex-col gap-2 min-[380px]:flex-row">
                    <Button
                      className="w-full min-[380px]:w-auto"
                      disabled={invitationMutation.isPending}
                      onClick={() =>
                        invitationMutation.mutate({ id: invitation.id, action: "accept" })
                      }
                    >
                      قبول
                    </Button>
                    <Button
                      className="w-full min-[380px]:w-auto"
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
              <div className="flex flex-col gap-4 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm transition hover:-translate-y-0.5 hover:border-teal-200 hover:shadow-md min-[420px]:flex-row min-[420px]:items-center min-[420px]:justify-between sm:p-5">
                <div className="min-w-0">
                  <p className="font-bold text-slate-800">{membership.school.name}</p>
                  <p className="text-sm text-slate-500">{roleLabels(membership.roles, membership.school.school_type)}</p>
                </div>
                <Button
                  className="w-full min-[420px]:w-auto"
                  onClick={() => {
                    setPendingId(membership.school.id);
                    switchMutation.mutate(membership.school.id);
                  }}
                  disabled={switchMutation.isPending}
                  loading={pendingId === membership.school.id && switchMutation.isPending}
                  loadingLabel="جارٍ الدخول..."
                >
                  دخول
                </Button>
              </div>
            </li>
          ))}
        </ul>

        <div className="mt-6 text-center">
          <button
            type="button"
            className="inline-flex min-h-11 items-center gap-2 rounded-xl px-3 py-2 text-sm font-semibold text-slate-600 transition hover:bg-slate-100 hover:text-slate-900 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-700"
            onClick={() => {
              void doLogout().then(() => navigate("/login", { replace: true }));
            }}
          >
            <LogOut aria-hidden size={16} /> تسجيل الخروج
          </button>
        </div>
      </div>
    </main>
  );
}
