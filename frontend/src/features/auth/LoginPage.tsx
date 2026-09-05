import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Building2, CheckCircle2, ShieldCheck } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Navigate, useNavigate, useSearchParams } from "react-router-dom";

import { login } from "@/api/auth";
import { ApiError } from "@/api/client";
import { purgeSensitiveBrowserCaches } from "@/app/cacheSafety";
import { Button } from "@/components/Button";
import { PasswordInput } from "@/components/PasswordInput";
import { Spinner } from "@/components/Spinner";
import { TextField } from "@/components/TextField";
import { safeReturnTo, withReturnTo } from "@/features/auth/returnTo";
import { ME_QUERY_KEY, useMe } from "@/features/auth/useMe";
import type { Me } from "@/types/auth";

const LOCAL_MOBILE_RE = /^05\d{8}$/;
const ARABIC_DIGITS = "٠١٢٣٤٥٦٧٨٩";

function normalizeLocalMobileInput(value: string): string | null {
  const latin = [...value].map((char) => {
    const index = ARABIC_DIGITS.indexOf(char);
    return index === -1 ? char : String(index);
  }).join("");
  if (latin === "" || latin === "0" || /^05\d{0,8}$/.test(latin)) return latin;
  return null;
}

function toInternationalMobile(value: string): string {
  return `+966${value.slice(1)}`;
}

function authenticatedDestination(me: Me, returnTo: string | null) {
  if (me.must_change_password) return "/change-password";
  if (me.is_platform_admin) return "/platform";
  if (me.active_school) return returnTo ?? "/";
  return withReturnTo("/select-school", returnTo);
}

export function LoginPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const me = useMe();
  const returnTo = safeReturnTo(searchParams.get("returnTo"));

  const [mobile, setMobile] = useState("");
  const [password, setPassword] = useState("");
  const [fieldError, setFieldError] = useState<string | null>(null);

  const loginMutation = useMutation({
    mutationFn: () => login(toInternationalMobile(mobile), password),
    onSuccess: async (data: Me) => {
      queryClient.clear();
      await purgeSensitiveBrowserCaches();
      queryClient.setQueryData(ME_QUERY_KEY, data);
      navigate(authenticatedDestination(data, returnTo), { replace: true });
    },
  });

  // مسجل دخول بالفعل؟ لا معنى لصفحة الدخول
  if (me.isSuccess) {
    return <Navigate to={authenticatedDestination(me.data, returnTo)} replace />;
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setFieldError(null);
    if (!LOCAL_MOBILE_RE.test(mobile)) {
      setFieldError("أدخل رقم الجوال بصيغة 05XXXXXXXX المكوّنة من 10 أرقام");
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
    <main className="auth-shell flex min-h-dvh items-center justify-center p-4 sm:p-8">
      <div className="grid w-full max-w-5xl items-center gap-10 lg:grid-cols-[1.05fr_0.95fr]">
        <section className="hidden px-6 text-white lg:block">
          <span className="mb-8 grid size-14 place-items-center rounded-2xl bg-white/10 ring-1 ring-white/15">
            <Building2 aria-hidden size={29} className="text-teal-200" />
          </span>
          <p className="mb-3 text-sm font-bold text-teal-200">منصة مدرسية متكاملة</p>
          <h1 className="text-xl font-black">منصة المواظبة</h1>
          <h2 className="mt-4 max-w-lg text-4xl font-black leading-[1.35]">المواظبة والمتابعة، بصورة أوضح كل يوم.</h2>
          <p className="mt-5 max-w-lg text-base leading-8 text-slate-300">مساحة عمل موحدة تساعد الإدارة والمعلمين والمرشدين على متابعة الطالب واتخاذ الإجراء المناسب بثقة.</p>
          <div className="mt-8 flex flex-wrap gap-x-6 gap-y-3 text-sm text-slate-300">
            <span className="flex items-center gap-2"><CheckCircle2 size={17} className="text-teal-300" /> متابعة لحظية</span>
            <span className="flex items-center gap-2"><ShieldCheck size={17} className="text-teal-300" /> بيانات آمنة</span>
          </div>
        </section>

        <form onSubmit={handleSubmit} className="auth-card w-full rounded-3xl p-6 sm:p-9" noValidate>
          <div className="mb-7">
            <span className="mb-5 grid size-12 place-items-center rounded-2xl bg-teal-50 text-teal-800 lg:hidden"><Building2 aria-hidden size={24} /></span>
            <p className="mb-1 text-sm font-bold text-blue-700">مرحبًا بعودتك</p>
            <h2 className="text-2xl font-black text-slate-900">تسجيل الدخول</h2>
            <p className="mt-2 text-sm leading-6 text-slate-500">أدخل بيانات حسابك للوصول إلى لوحة مدرستك.</p>
          </div>

          <TextField
            label="رقم الجوال"
            name="mobile"
            type="tel"
            inputMode="tel"
            dir="ltr"
            placeholder="05XXXXXXXX"
            maxLength={10}
            pattern="05[0-9]{8}"
            autoComplete="tel"
            value={mobile}
            onChange={(e) => {
              const normalized = normalizeLocalMobileInput(e.target.value);
              if (normalized !== null) setMobile(normalized);
            }}
            className="mb-5 text-start"
          />

          <PasswordInput
            label="كلمة المرور"
            name="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="mb-5"
          />

          {fieldError && (
            <p role="alert" className="mb-4 rounded-xl border border-red-100 bg-red-50 p-3 text-sm text-red-700">
              {fieldError}
            </p>
          )}
          {apiError && (
            <p role="alert" className="mb-4 rounded-xl border border-red-100 bg-red-50 p-3 text-sm text-red-700">
              {apiError.message}
            </p>
          )}

          <Button type="submit" className="mt-1 w-full py-3" disabled={loginMutation.isPending}>
            {loginMutation.isPending ? <Spinner label="جارٍ الدخول..." /> : "تسجيل الدخول"}
          </Button>
          <p className="mt-6 flex items-center justify-center gap-2 text-xs text-slate-400"><ShieldCheck aria-hidden size={15} /> اتصال آمن ومحمي</p>
        </form>
      </div>
    </main>
  );
}
