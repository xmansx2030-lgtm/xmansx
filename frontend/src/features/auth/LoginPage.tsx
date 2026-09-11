import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Building2, CheckCircle2, ShieldCheck } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Navigate, useNavigate, useSearchParams } from "react-router-dom";

import { login } from "@/api/auth";
import { ApiError } from "@/api/client";
import { purgeSensitiveBrowserCaches } from "@/app/cacheSafety";
import { Alert } from "@/components/Alert";
import { Button } from "@/components/Button";
import { PasswordInput } from "@/components/PasswordInput";
import { TextField } from "@/components/TextField";
import { safeReturnTo, withReturnTo } from "@/features/auth/returnTo";
import { ME_QUERY_KEY, useMe } from "@/features/auth/useMe";
import type { Me } from "@/types/auth";

const LOCAL_MOBILE_RE = /^05\d{8}$/;
const ARABIC_DIGITS = "٠١٢٣٤٥٦٧٨٩";
const WHATSAPP_URL = "https://wa.me/966537720207";

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
  const [fieldErrors, setFieldErrors] = useState<{ mobile?: string; password?: string }>({});

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
    setFieldErrors({});
    if (!LOCAL_MOBILE_RE.test(mobile)) {
      setFieldErrors({ mobile: "أدخل رقم الجوال بصيغة 05XXXXXXXX المكوّنة من 10 أرقام" });
      return;
    }
    if (password.length === 0) {
      setFieldErrors({ password: "أدخل كلمة المرور" });
      return;
    }
    loginMutation.mutate();
  }

  const apiError =
    loginMutation.error instanceof ApiError ? loginMutation.error : null;

  return (
    <main className="auth-shell flex h-dvh items-center justify-center overflow-y-auto p-4 sm:p-8">
      <div className="grid w-full max-w-4xl min-w-0 items-center gap-8 lg:grid-cols-[1fr_1fr]">
        <section className="hidden px-4 text-white lg:block">
          <span className="mb-8 grid size-14 place-items-center rounded-2xl bg-white/10 ring-1 ring-white/15">
            <Building2 aria-hidden size={29} className="text-teal-200" />
          </span>
          <p className="mb-3 text-sm font-bold text-teal-200">منصة مدرسية متكاملة</p>
          <p className="text-xl font-black">منصة المواظبة</p>
          <h2 className="mt-4 max-w-md text-3xl font-black leading-[1.35]">المواظبة والمتابعة، بصورة أوضح كل يوم.</h2>
          <p className="mt-4 max-w-md text-sm leading-7 text-slate-300">مساحة عمل موحدة تساعد الإدارة والهيئة التعليمية والإرشادية على متابعة الطالب أو الطالبة واتخاذ الإجراء المناسب بثقة.</p>
          <div className="mt-8 flex flex-wrap gap-x-6 gap-y-3 text-sm text-slate-300">
            <span className="flex items-center gap-2"><CheckCircle2 size={17} className="text-teal-300" /> متابعة لحظية</span>
            <span className="flex items-center gap-2"><ShieldCheck size={17} className="text-teal-300" /> بيانات آمنة</span>
          </div>
        </section>

        <form onSubmit={handleSubmit} className="auth-card w-full min-w-0 max-w-md justify-self-center rounded-3xl p-6 sm:p-9" noValidate>
          <div className="mb-7">
            <span className="mb-5 grid size-12 place-items-center rounded-2xl bg-teal-50 text-teal-800 lg:hidden"><Building2 aria-hidden size={24} /></span>
            <p className="mb-1 text-sm font-bold text-blue-700">مرحبًا بعودتك</p>
            <h1 className="text-2xl font-black text-slate-900">منصة المواظبة</h1>
            <h2 className="mt-2 text-lg font-extrabold text-slate-700">تسجيل الدخول</h2>
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
            required
            value={mobile}
            error={fieldErrors.mobile}
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
            required
            value={password}
            error={fieldErrors.password}
            onChange={(e) => setPassword(e.target.value)}
            className="mb-5"
          />

          {apiError && (
            <Alert tone="danger" title="تعذر تسجيل الدخول" className="mb-4">{apiError.message}</Alert>
          )}

          <Button type="submit" size="lg" fullWidth className="mt-1" loading={loginMutation.isPending} loadingLabel="جارٍ الدخول...">تسجيل الدخول</Button>
          <p className="mt-6 flex items-center justify-center gap-2 text-xs text-slate-400"><ShieldCheck aria-hidden size={15} /> اتصال آمن ومحمي</p>
        </form>
      </div>

      <a
        href={WHATSAPP_URL}
        target="_blank"
        rel="noopener noreferrer"
        aria-label="تواصل معنا عبر واتساب على الرقم 0537720207"
        title="تواصل معنا عبر واتساب"
        className="fixed bottom-5 left-5 z-40 grid size-14 place-items-center rounded-full bg-[#25D366] text-white shadow-[0_12px_30px_rgba(7,27,25,0.35)] ring-1 ring-white/30 transition duration-200 hover:-translate-y-1 hover:bg-[#20bd5a] hover:shadow-[0_16px_36px_rgba(7,27,25,0.42)] focus-visible:outline-white sm:bottom-7 sm:left-7 sm:size-16"
      >
        <svg
          aria-hidden="true"
          viewBox="0 0 24 24"
          className="size-8 sm:size-9"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M20.5 11.6a8.5 8.5 0 0 1-12.6 7.45L3.5 20.5l1.45-4.28A8.5 8.5 0 1 1 20.5 11.6Z" />
          <path d="M8.15 7.55c.2-.44.4-.45.7-.46h.57c.18 0 .38.07.47.36l.65 1.57c.08.2.04.39-.1.58l-.5.62c-.15.17-.12.34-.02.52.56.98 1.38 1.78 2.36 2.34.2.11.38.1.53-.08l.75-.88c.17-.2.38-.23.6-.13l1.51.72c.24.12.4.18.46.29.07.11.07.62-.14 1.2-.21.57-1.2 1.1-1.69 1.16-.44.06-1 .08-1.62-.12-.37-.12-.84-.28-1.45-.55a8.9 8.9 0 0 1-3.7-3.27c-.38-.53-1.2-1.76-1.2-3.04 0-.63.32-1.14.48-1.37Z" />
        </svg>
      </a>
    </main>
  );
}
