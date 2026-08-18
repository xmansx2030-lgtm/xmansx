import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Navigate, useNavigate } from "react-router-dom";

import { changeInitialPassword } from "@/api/auth";
import { ApiError } from "@/api/client";
import { Button } from "@/components/Button";
import { PasswordInput } from "@/components/PasswordInput";
import { ME_QUERY_KEY, useMe } from "@/features/auth/useMe";

/** شاشة إجبارية للحسابات الجديدة — لا وصول للتطبيق قبل تغيير الكلمة المؤقتة. */
export function ChangeInitialPasswordPage() {
  const me = useMe();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [fieldError, setFieldError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () => changeInitialPassword(current, next, confirm),
    onSuccess: (updated) => {
      queryClient.setQueryData(ME_QUERY_KEY, updated);
      navigate(updated.active_school ? "/" : "/select-school", { replace: true });
    },
  });

  if (me.isSuccess && !me.data.must_change_password) {
    return <Navigate to="/" replace />;
  }
  if (me.isError) return <Navigate to="/login" replace />;

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setFieldError(null);
    if (next.length < 8) {
      setFieldError("كلمة المرور الجديدة يجب ألا تقل عن 8 أحرف.");
      return;
    }
    if (next !== confirm) {
      setFieldError("تأكيد كلمة المرور غير مطابق.");
      return;
    }
    mutation.mutate();
  }

  const apiError = mutation.error instanceof ApiError ? mutation.error : null;

  return (
    <main className="flex min-h-dvh items-center justify-center bg-slate-50 p-4">
      <form
        onSubmit={handleSubmit}
        noValidate
        className="w-full max-w-sm rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"
      >
        <h1 className="mb-1 text-xl font-bold">تغيير كلمة المرور</h1>
        <p className="mb-5 text-sm text-slate-500">
          يجب تغيير كلمة المرور المؤقتة قبل متابعة استخدام المنصة.
        </p>

        <PasswordInput
          label="كلمة المرور الحالية"
          value={current}
          onChange={(e) => setCurrent(e.target.value)}
          autoComplete="current-password"
          className="mb-3"
        />
        <PasswordInput
          label="كلمة المرور الجديدة"
          value={next}
          onChange={(e) => setNext(e.target.value)}
          autoComplete="new-password"
          className="mb-3"
        />
        <PasswordInput
          label="تأكيد كلمة المرور"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          autoComplete="new-password"
          className="mb-4"
        />

        {fieldError && (
          <p role="alert" className="mb-3 text-sm text-red-700">
            {fieldError}
          </p>
        )}
        {apiError && (
          <p role="alert" className="mb-3 rounded-lg bg-red-50 p-2 text-sm text-red-700">
            {apiError.message}
          </p>
        )}

        <Button type="submit" className="w-full" disabled={mutation.isPending}>
          {mutation.isPending ? "جارٍ الحفظ..." : "حفظ كلمة المرور"}
        </Button>
      </form>
    </main>
  );
}
