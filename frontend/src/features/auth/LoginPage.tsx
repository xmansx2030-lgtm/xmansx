import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Navigate, useNavigate } from "react-router-dom";

import { login } from "@/api/auth";
import { ApiError } from "@/api/client";
import { Button } from "@/components/Button";
import { PasswordInput } from "@/components/PasswordInput";
import { Spinner } from "@/components/Spinner";
import { TextField } from "@/components/TextField";
import { ME_QUERY_KEY, useMe } from "@/features/auth/useMe";
import type { Me } from "@/types/auth";

const MOBILE_RE = /^[+٠-٩\d][\d\s\-٠-٩]{8,15}$/;

export function LoginPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const me = useMe();

  const [mobile, setMobile] = useState("");
  const [password, setPassword] = useState("");
  const [fieldError, setFieldError] = useState<string | null>(null);

  const loginMutation = useMutation({
    mutationFn: () => login(mobile.trim(), password),
    onSuccess: (data: Me) => {
      queryClient.setQueryData(ME_QUERY_KEY, data);
      if (data.must_change_password) {
        navigate("/change-password", { replace: true });
      } else {
        navigate(data.active_school ? "/" : "/select-school", { replace: true });
      }
    },
  });

  // مسجل دخول بالفعل؟ لا معنى لصفحة الدخول
  if (me.isSuccess) {
    if (me.data.must_change_password) {
      return <Navigate to="/change-password" replace />;
    }
    return <Navigate to={me.data.active_school ? "/" : "/select-school"} replace />;
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setFieldError(null);
    if (!MOBILE_RE.test(mobile.trim())) {
      setFieldError("أدخل رقم جوال سعودي صحيح مثل 05XXXXXXXX");
      return;
    }
    if (password.length === 0) {
      setFieldError("أدخل كلمة المرور");
      return;
    }
    loginMutation.mutate();
  }

  const apiError =
    loginMutation.error instanceof ApiError ? loginMutation.error : null;

  return (
    <main className="flex min-h-dvh items-center justify-center bg-slate-50 p-4">
      <div className="w-full max-w-sm">
        <div className="mb-6 text-center">
          <h1 className="text-2xl font-black text-slate-800">منصة المواظبة</h1>
          <p className="mt-1 text-sm text-slate-500">والمتابعة الطلابية للمدارس</p>
        </div>

        <form
          onSubmit={handleSubmit}
          className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"
          noValidate
        >
          <h2 className="mb-4 text-lg font-bold">تسجيل الدخول</h2>

          <TextField
            label="رقم الجوال"
            name="mobile"
            type="tel"
            inputMode="tel"
            dir="ltr"
            placeholder="05XXXXXXXX"
            autoComplete="tel"
            value={mobile}
            onChange={(e) => setMobile(e.target.value)}
            className="mb-4 text-start"
          />

          <PasswordInput
            label="كلمة المرور"
            name="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="mb-4"
          />

          {fieldError && (
            <p role="alert" className="mb-3 text-sm text-red-600">
              {fieldError}
            </p>
          )}
          {apiError && (
            <p role="alert" className="mb-3 rounded-lg bg-red-50 p-2 text-sm text-red-700">
              {apiError.message}
            </p>
          )}

          <Button type="submit" className="w-full" disabled={loginMutation.isPending}>
            {loginMutation.isPending ? <Spinner label="جارٍ الدخول..." /> : "تسجيل الدخول"}
          </Button>
        </form>
      </div>
    </main>
  );
}
