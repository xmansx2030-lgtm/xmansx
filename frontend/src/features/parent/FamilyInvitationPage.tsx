import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { HeartHandshake } from "lucide-react";
import { useId, useState, type FormEvent } from "react";
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
import { activateFamilyInvitation, checkFamilyInvitation } from "@/features/parent/familyInvitations";
import {
  normalizeRecoveryEmail, RECOVERY_EMAIL_DESCRIPTION, recoveryEmailError, useRecoveryFragment,
} from "@/features/parent/recoveryEmail";

export function FamilyInvitationPage() {
  const token = useRecoveryFragment();
  const instance = useId();
  const client = useQueryClient();
  const navigate = useNavigate();
  const me = useMe();
  const doLogout = useLogout();
  const logout = useMutation({ mutationFn: doLogout });
  const [mobile, setMobile] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const metadata = useQuery({
    queryKey: ["parent-public-family-invitation", instance, me.data?.id],
    queryFn: async ({ signal }) => { await ensureCsrfCookie(); return checkFamilyInvitation(token, signal); },
    enabled: !!token && !me.isPending, retry: false, staleTime: 0, gcTime: 0,
  });
  const signIn = useMutation({
    mutationFn: () => login(toCanonicalMobile(mobile) ?? "", password),
    onSuccess: async (updated) => {
      await client.cancelQueries(); client.clear(); await purgeSensitiveBrowserCaches();
      client.setQueryData(ME_QUERY_KEY, updated); setPassword(""); setError("");
    },
  });
  const activate = useMutation({
    mutationFn: () => activateFamilyInvitation({
      token, email: metadata.data?.email_verified ? undefined : normalizeRecoveryEmail(email),
      new_password: metadata.data?.account_exists ? undefined : password,
      confirm_password: metadata.data?.account_exists ? undefined : confirm,
      current_password: metadata.data?.account_exists && !metadata.data.email_verified ? password : undefined,
    }),
    onSuccess: async (updated) => {
      await client.cancelQueries(); client.clear(); await purgeSensitiveBrowserCaches();
      client.setQueryData(ME_QUERY_KEY, updated);
      navigate("/parent", { replace: true });
    },
  });
  function submit(event: FormEvent) {
    event.preventDefault(); setError("");
    if (metadata.data?.requires_login) {
      if (!toCanonicalMobile(mobile) || !password) { setError("أدخل جوال حسابك الحالي وكلمة المرور."); return; }
      signIn.mutate(); return;
    }
    if (!metadata.data?.email_verified) {
      const emailError = recoveryEmailError(email);
      if (emailError) { setError(emailError); return; }
    }
    if (!metadata.data?.account_exists && (password.length < 8 || password !== confirm || /^[0-9٠-٩]+$/.test(password))) {
      setError("اختر كلمة مرور آمنة من 8 أحرف على الأقل وطابق التأكيد."); return;
    }
    if (metadata.data?.account_exists && !metadata.data.email_verified && !password) {
      setError("أدخل كلمة المرور الحالية لتسجيل بريد الاسترداد."); return;
    }
    activate.mutate();
  }
  return <main className="auth-shell grid min-h-dvh place-items-center px-4 py-8" dir="rtl">
    <div className="auth-card w-full max-w-lg rounded-3xl p-5 sm:p-9">
      <HeartHandshake className="mb-4 text-teal-700" size={32} aria-hidden />
      <h1 className="text-2xl font-black">دعوة متابعة الأبناء</h1>
      <p className="mt-3 text-sm leading-7 text-slate-600">اعتمدت المدرسة ربط الأبناء المحددين في الدعوة. أكمل حسابك ووثّق بريد الاسترداد لبدء المتابعة.</p>
      {!token && <Alert tone="warning" title="افتح رابط الدعوة الأصلي">الرابط صالح لمرة واحدة. اطلب دعوة جديدة من المدرسة عند الحاجة.</Alert>}
      {token && (metadata.isPending || me.isPending) && <PageSkeleton label="جارٍ التحقق من الدعوة" />}
      {metadata.isError && <ErrorState error={metadata.error} />}
      {metadata.data && <form className="mt-5 space-y-4" onSubmit={submit} noValidate>
        <p className="font-black text-teal-800">{metadata.data.school_name}</p>
        <p className="text-sm">دعوة واحدة لربط {metadata.data.children_count} من الأبناء. تظهر بياناتهم بعد اكتمال التفعيل وتوثيق البريد.</p>
        {metadata.data.requires_login ? <>
          <Alert title="لديك حساب بالفعل">سجل الدخول إلى حسابك الحالي؛ تبقى كلمة مروره وعضوياته كما هي.</Alert>
          {me.data && <Button variant="secondary" onClick={() => logout.mutate()} disabled={logout.isPending}>تسجيل الخروج من الحساب الحالي</Button>}
          <TextField label="رقم جوال الحساب الحالي" type="tel" dir="ltr" autoComplete="tel" value={mobile} onChange={(event) => setMobile(toLatinDigits(event.target.value))} required />
          <PasswordInput label="كلمة المرور الحالية" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} required />
        </> : <>
          {metadata.data.account_exists && <Alert title="ربط الأبناء بحسابك الحالي">{me.data?.name}{metadata.data.email_verified && <p>سيبقى بريد الاسترداد الموثق الحالي دون تغيير.</p>}</Alert>}
          {!metadata.data.email_verified && <TextField label="البريد الإلكتروني" description={RECOVERY_EMAIL_DESCRIPTION} type="email" dir="ltr" autoComplete="email" required maxLength={254} value={email} onChange={(event) => setEmail(event.target.value)} />}
          {(!metadata.data.account_exists || !metadata.data.email_verified) && <PasswordInput label={metadata.data.account_exists ? "كلمة المرور الحالية" : "كلمة المرور الجديدة"} autoComplete={metadata.data.account_exists ? "current-password" : "new-password"} value={password} onChange={(event) => setPassword(event.target.value)} required />}
          {!metadata.data.account_exists && <PasswordInput label="تأكيد كلمة المرور الجديدة" autoComplete="new-password" value={confirm} onChange={(event) => setConfirm(event.target.value)} required />}
          {!metadata.data.email_verified && <p className="text-sm leading-7 text-slate-600">سنرسل رابط توثيق إلى بريدك. تبقى موافقة المدرسة محفوظة إذا تعطل الإرسال، ويمكن إعادة إرسال التوثيق من حسابك.</p>}
        </>}
        {error && <Alert tone="danger" title="راجع البيانات">{error}</Alert>}
        {signIn.isError && <ErrorState error={signIn.error} />}
        {activate.isError && <ErrorState error={activate.error} />}
        <Button type="submit" fullWidth loading={signIn.isPending || activate.isPending}>{metadata.data.requires_login ? "تسجيل الدخول لاستكمال الدعوة" : "تفعيل الربط والمتابعة"}</Button>
      </form>}
      <div className="mt-5"><Link to="/login" className="text-sm font-bold text-teal-800 underline">العودة لتسجيل الدخول</Link></div>
    </div>
  </main>;
}
