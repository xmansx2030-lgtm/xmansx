import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";

import { ApiError } from "@/api/client";
import { Button } from "@/components/Button";
import { Spinner } from "@/components/Spinner";
import { useLogout, useMe, useSwitchSchool } from "@/features/auth/useMe";
import { roleLabels } from "@/utils/roles";

export function SelectSchoolPage() {
  const navigate = useNavigate();
  const me = useMe();
  const switchSchool = useSwitchSchool();
  const doLogout = useLogout();
  const [pendingId, setPendingId] = useState<number | null>(null);

  const switchMutation = useMutation({
    mutationFn: (schoolId: number) => switchSchool(schoolId),
    onSuccess: () => navigate("/", { replace: true }),
    onSettled: () => setPendingId(null),
  });

  if (me.isPending) {
    return (
      <div className="flex min-h-dvh items-center justify-center">
        <Spinner />
      </div>
    );
  }
  if (me.isError) return <Navigate to="/login" replace />;
  if (me.data.memberships.length === 0) return <Navigate to="/" replace />;

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
