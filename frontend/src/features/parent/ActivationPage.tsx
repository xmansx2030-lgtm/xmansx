import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyRound } from "lucide-react";
import { useEffect, useId, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

import { ensureCsrfCookie, login } from "@/api/auth";
import { purgeSensitiveBrowserCaches } from "@/app/cacheSafety";
import { Alert } from "@/components/Alert";
import { Button } from "@/components/Button";
import { ErrorState } from "@/components/ErrorState";
import { PasswordInput } from "@/components/PasswordInput";
import { PageSkeleton } from "@/components/Skeleton";
import { TextField } from "@/components/TextField";
import { toCanonicalMobile, toLatinDigits } from "@/features/auth/mobile";
import { ME_QUERY_KEY, useLogout, useMe } from "@/features/auth/useMe";
import { activateParent, checkActivation } from "@/features/parent/api";

export function ActivationPage() {
  // Fragment is never sent to proxy/server logs. It remains in this mounted page only.
  const [token] = useState(
    () => new URLSearchParams(window.location.hash.slice(1)).get("token") ?? "",
  );
  const instance = useId();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const me = useMe();
  const doLogout = useLogout();
  const [mobile, setMobile] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    if (window.location.hash)
      window.history.replaceState(
        window.history.state,
        "",
        `${window.location.pathname}${window.location.search}`,
      );
    const previous = document.querySelector<HTMLMetaElement>(
      'meta[name="referrer"]',
    );
    const policy = previous ?? document.createElement("meta");
    const old = policy.content;
    policy.name = "referrer";
    policy.content = "no-referrer";
    if (!previous) document.head.append(policy);
    return () => {
      if (previous) policy.content = old;
      else policy.remove();
    };
  }, []);
  const metadata = useQuery({
    queryKey: ["parent-public-activation", instance],
    queryFn: async ({ signal }) => {
      await ensureCsrfCookie();
      return checkActivation(token, signal);
    },
    enabled: !!token,
    retry: false,
    staleTime: 0,
    gcTime: 0,
  });
  const activate = useMutation({
    mutationFn: () =>
      activateParent(
        token,
        metadata.data?.account_exists ? undefined : password,
        confirm,
      ),
    onSuccess: async (updated) => {
      await queryClient.cancelQueries();
      queryClient.clear();
      await purgeSensitiveBrowserCaches();
      queryClient.setQueryData(ME_QUERY_KEY, updated);
      navigate("/parent", { replace: true });
    },
  });
  const signIn = useMutation({
    mutationFn: () => login(toCanonicalMobile(mobile) ?? "", password),
    onSuccess: async (updated) => {
      await queryClient.cancelQueries();
      queryClient.clear();
      await purgeSensitiveBrowserCaches();
      queryClient.setQueryData(ME_QUERY_KEY, updated);
      setPassword("");
      await metadata.refetch();
    },
  });
  function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    if (metadata.data?.requires_login) {
      if (!toCanonicalMobile(mobile) || !password) {
        setError("أدخل جوال حسابك الحالي وكلمة المرور.");
        return;
      }
      signIn.mutate();
      return;
    }
    if (
      !metadata.data?.account_exists &&
      (password.length < 8 ||
        password !== confirm ||
        /^[0-9٠-٩]+$/.test(password))
    ) {
      setError("اختر كلمة مرور آمنة من 8 أحرف على الأقل وطابق التأكيد.");
      return;
    }
    activate.mutate();
  }
  const needsLogin = metadata.data?.requires_login;
  return (
    <main className="auth-shell grid min-h-dvh place-items-center px-4 py-8">
      <div className="auth-card w-full max-w-lg rounded-3xl p-5 sm:p-9">
        <span className="mb-4 grid size-12 place-items-center rounded-2xl bg-teal-50 text-teal-800">
          <KeyRound aria-hidden />
        </span>
        <h1 className="text-2xl font-black">تفعيل بوابة ولي الأمر</h1>
        {!token && (
          <Alert tone="warning" title="افتح رابط التفعيل الأصلي">
            الرابط صالح لمرة واحدة. اطلب رابطاً جديداً من المدرسة عند الحاجة.
          </Alert>
        )}
        {token && metadata.isPending && (
          <PageSkeleton label="جارٍ التحقق من رابط التفعيل" />
        )}
        {metadata.isError && <ErrorState error={metadata.error} />}
        {metadata.isSuccess && (
          <form onSubmit={submit} className="mt-5 space-y-4">
            <p className="font-bold text-teal-800">
              {metadata.data.school_name}
            </p>
            {metadata.data.status !== "VALID" ? (
              <Alert tone="warning" title="رابط التفعيل غير متاح">
                تواصل مع المدرسة للحصول على رابط حديث.
              </Alert>
            ) : (
              <>
                {needsLogin ? (
                  <>
                    <Alert title="لديك حساب بالفعل">
                      سجل الدخول إلى الحساب الحالي لاستكمال الربط.
                    </Alert>
                    <TextField
                      label="رقم جوال الحساب الحالي"
                      type="tel"
                      dir="ltr"
                      autoComplete="tel"
                      value={mobile}
                      onChange={(e) => setMobile(toLatinDigits(e.target.value))}
                      required
                    />
                    <PasswordInput
                      label="كلمة المرور الحالية"
                      autoComplete="current-password"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      required
                    />
                  </>
                ) : metadata.data.account_exists ? (
                  <Alert title="استكمال الربط بالحساب الحالي">
                    <p>{me.data?.name}</p>
                    <Button
                      variant="ghost"
                      onClick={() =>
                        void doLogout().then(() => metadata.refetch())
                      }
                    >
                      استخدام حساب آخر
                    </Button>
                  </Alert>
                ) : (
                  <>
                    <p className="text-sm leading-7 text-slate-600">
                      أنشئ كلمة مرور لحسابك العالمي. ستستخدم الحساب نفسه لجميع
                      أبنائك بعد اعتماد مدارسهم.
                    </p>
                    <PasswordInput
                      label="كلمة المرور الجديدة"
                      autoComplete="new-password"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      required
                    />
                    <PasswordInput
                      label="تأكيد كلمة المرور"
                      autoComplete="new-password"
                      value={confirm}
                      onChange={(e) => setConfirm(e.target.value)}
                      required
                    />
                  </>
                )}
                {error && <Alert tone="danger" title={error} />}
                {signIn.isError && <ErrorState error={signIn.error} />}
                {activate.isError && <ErrorState error={activate.error} />}
                <Button
                  type="submit"
                  fullWidth
                  loading={signIn.isPending || activate.isPending}
                >
                  {needsLogin
                    ? "الدخول واستكمال التفعيل"
                    : metadata.data.account_exists
                      ? "ربط الابن بحسابي"
                      : "إنشاء الحساب وتفعيل العلاقة"}
                </Button>
              </>
            )}
          </form>
        )}
        <Link
          to="/login"
          className="mt-5 inline-flex min-h-11 items-center text-sm font-bold text-teal-800"
        >
          تسجيل الدخول
        </Link>
      </div>
    </main>
  );
}
