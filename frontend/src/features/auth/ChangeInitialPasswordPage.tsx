import { useMutation, useQueryClient } from "@tanstack/react-query";
import { KeyRound, ShieldCheck } from "lucide-react";
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
      navigate(
        updated.is_platform_admin
          ? "/platform"
          : updated.active_school
            ? "/"
            : "/select-school",
        { replace: true },
      );
    },
  });

  if (me.isSuccess && !me.data.must_change_password) {
    return <Navigate to={me.data.is_platform_admin ? "/platform" : "/"} replace />;
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
    <main className="auth-shell flex h-dvh items-center justify-center overflow-y-auto p-4">
      <form
        onSubmit={handleSubmit}
        noValidate
        className="auth-card w-full min-w-0 max-w-md rounded-3xl p-6 sm:p-9"
      >
        <span className="mb-5 grid size-12 place-items-center rounded-2xl bg-teal-50 text-teal-800"><KeyRound aria-hidden size={23} /></span>
        <p className="mb-1 text-sm font-bold text-blue-700">خطوة أمان مطلوبة</p>
        <h1 className="text-2xl font-black text-slate-900">تغيير كلمة المرور</h1>
        <p className="mb-6 mt-2 text-sm leading-6 text-slate-500">
          يجب تغيير كلمة المرور المؤقتة قبل متابعة استخدام المنصة.
        </p>

        <PasswordInput
          label="كلمة المرور الحالية"
          required
          value={current}
          onChange={(e) => setCurrent(e.target.value)}
          autoComplete="current-password"
          className="mb-3"
        />
        <PasswordInput
          label="كلمة المرور الجديدة"
          required
          description="ثمانية أحرف على الأقل، ويفضل أن تكون فريدة لهذا الحساب."
          value={next}
          onChange={(e) => setNext(e.target.value)}
          autoComplete="new-password"
          className="mb-3"
        />
        <PasswordInput
          label="تأكيد كلمة المرور"
          required
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

        <Button type="submit" size="lg" fullWidth className="mt-1" loading={mutation.isPending} loadingLabel="جارٍ الحفظ...">حفظ كلمة المرور</Button>
        <p className="mt-5 flex items-center justify-center gap-2 text-xs text-slate-400"><ShieldCheck aria-hidden size={15} /> اختر كلمة مرور فريدة لا تستخدمها في مكان آخر</p>
      </form>
    </main>
  );
}
