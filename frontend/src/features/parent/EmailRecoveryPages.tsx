import { isCancelledError, useMutation, useQueryClient } from "@tanstack/react-query";
import { MailCheck, ShieldCheck } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";

import { getMe } from "@/api/auth";
import { ApiError } from "@/api/client";
import { purgeSensitiveBrowserCaches } from "@/app/cacheSafety";
import { Alert } from "@/components/Alert";
import { Button } from "@/components/Button";
import { ErrorState } from "@/components/ErrorState";
import { PasswordInput } from "@/components/PasswordInput";
import { PageSkeleton } from "@/components/Skeleton";
import { TextField } from "@/components/TextField";
import { toCanonicalMobile, toLatinDigits } from "@/features/auth/mobile";
import { ME_QUERY_KEY, useLogout, useMe } from "@/features/auth/useMe";
import { parentKey } from "@/features/parent/api";
import type { Me } from "@/types/auth";
import {
  checkParentPasswordRecovery,
  checkRecoveryEmail,
  completeParentPasswordRecovery,
  enrollRecoveryEmail,
  RECOVERY_EMAIL_DESCRIPTION,
  RECOVERY_REQUEST_MESSAGE,
  recoveryEmailError,
  recoveryEmailKey,
  requestParentPasswordRecovery,
  resendRecoveryEmail,
  useRecoveryEmailStatus,
  useRecoveryFragment,
  verifyRecoveryEmail,
  type RecoveryEmailStatus,
} from "@/features/parent/recoveryEmail";
import { SpaceSwitchButton } from "@/features/parent/SpaceSwitchButton";

function RecoveryLayout({ title, children }: { title: string; children: ReactNode }) {
  return (
    <main className="auth-shell grid min-h-dvh place-items-center overflow-x-hidden px-4 py-8" dir="rtl">
      <section className="auth-card w-full min-w-0 max-w-lg rounded-3xl p-5 sm:p-9">
        <span className="mb-4 grid size-12 place-items-center rounded-2xl bg-teal-50 text-teal-800">
          <MailCheck aria-hidden size={25} />
        </span>
        <h1 className="text-2xl font-black">{title}</h1>
        <div className="mt-5 space-y-4">{children}</div>
      </section>
    </main>
  );
}

function DeliveryNotice({ status }: { status: RecoveryEmailStatus["delivery_status"] }) {
  if (status === "FAILED") return (
    <Alert tone="warning" title="تعذر إرسال رسالة التحقق">
      بقيت موافقة المدرسة محفوظة. يمكنك طلب إعادة الإرسال عندما تتاح الخدمة.
    </Alert>
  );
  if (status === "UNKNOWN") return (
    <Alert tone="warning" title="نتيجة إرسال رسالة التحقق غير مؤكدة">
      افحص بريدك والرسائل غير المرغوبة قبل طلب إعادة الإرسال.
    </Alert>
  );
  if (status === "SENDING") return (
    <Alert title="جارٍ إرسال رسالة التحقق" live>
      انتظر اكتمال محاولة الإرسال قبل طلب رابط آخر.
    </Alert>
  );
  if (status === "CANCELLED") return (
    <Alert tone="warning" title="أُلغيت محاولة إرسال رسالة التحقق">
      راجع البريد المطلوب توثيقه، ثم اطلب رابطاً حديثاً عندما تتاح الخدمة.
    </Alert>
  );
  if (status) return (
    <Alert title={status === "PENDING" ? "رسالة التحقق بانتظار الإرسال" : "قُبل طلب إرسال رسالة التحقق"} live>
      افتح أحدث رابط في بريدك واضغط زر توثيق البريد. قبول طلب الإرسال لا يؤكد وصول الرسالة.
    </Alert>
  );
  return null;
}

export function RecoveryEmailPage() {
  const me = useMe();
  const status = useRecoveryEmailStatus();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const logout = useLogout();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [emailError, setEmailError] = useState("");
  const [editing, setEditing] = useState(false);
  const updateStatus = (value: RecoveryEmailStatus, ownerId?: number) => {
    if (!ownerId || queryClient.getQueryData<Me>(ME_QUERY_KEY)?.id !== ownerId) return;
    queryClient.setQueryData(recoveryEmailKey(ownerId), value);
    setPassword("");
    setEmail("");
    setEditing(false);
  };
  const enroll = useMutation({
    mutationFn: () => enrollRecoveryEmail(email, password),
    onMutate: () => ({ ownerId: me.data?.id }),
    onSuccess: (value, _variables, context) => updateStatus(value, context?.ownerId),
    gcTime: 0,
  });
  const resend = useMutation({
    mutationFn: resendRecoveryEmail,
    onMutate: () => ({ ownerId: me.data?.id }),
    onSuccess: (value, _variables, context) => updateStatus(value, context?.ownerId),
    gcTime: 0,
  });
  function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    const invalid = recoveryEmailError(email);
    setEmailError(invalid);
    if (invalid) return;
    if (!password) {
      setError("أدخل كلمة المرور الحالية لإثبات ملكية حسابك.");
      return;
    }
    enroll.mutate();
  }
  const ready = status.data?.verified;
  const pending = status.data?.pending_email_masked;
  const busy = enroll.isPending || resend.isPending;
  return (
    <RecoveryLayout title="بريد استرداد كلمة المرور">
      {status.isPending && <PageSkeleton label="جارٍ التحقق من بريد الاسترداد" />}
      {status.isError && <ErrorState error={status.error} />}
      {status.isSuccess && (
        <>
          {ready ? (
            <Alert tone="success" title="بريد الاسترداد موثق">
              <span dir="ltr" className="break-all">{status.data.email_masked}</span>
            </Alert>
          ) : (
            <Alert tone="warning" title="بانتظار توثيق بريد الاسترداد">
              أكمل توثيق بريد يمكنك الوصول إليه قبل عرض بيانات الأبناء. تبقى موافقة المدرسة والعلاقات السابقة محفوظة.
            </Alert>
          )}
          <p className="text-sm leading-7 text-slate-600">{RECOVERY_EMAIL_DESCRIPTION}</p>
          {pending && (
            <>
              <p className="text-sm text-slate-600">البريد بانتظار التوثيق: <b dir="ltr" className="break-all">{pending}</b></p>
              <DeliveryNotice status={status.data.delivery_status} />
              <Button variant="secondary" loading={resend.isPending} disabled={!status.data.enabled || busy || status.data.delivery_status === "SENDING"} onClick={() => resend.mutate()}>
                إعادة إرسال رابط التحقق
              </Button>
              {(status.data.delivery_status === "PENDING" || status.data.delivery_status === "SENDING") && (
                <Button variant="ghost" loading={status.isFetching} onClick={() => void status.refetch()}>تحديث حالة البريد</Button>
              )}
            </>
          )}
          {!status.data.enabled && (
            <Alert tone="warning" title="خدمة بريد الاسترداد غير متاحة حالياً">
              حاول لاحقاً. لا يلزم إنشاء حساب جديد، ولا تستطيع المدرسة تغيير بريد حسابك أو كلمة مروره.
            </Alert>
          )}
          {(!ready && !pending || editing) && (
            <form className="space-y-4" onSubmit={submit} noValidate>
              <TextField label="البريد الإلكتروني" type="email" inputMode="email" autoComplete="email" dir="ltr" required maxLength={254} value={email} onChange={(event) => setEmail(event.target.value)} error={emailError} description="يرجى إدخال بريد إلكتروني يمكنك الوصول إليه." />
              <PasswordInput label="كلمة المرور الحالية" autoComplete="current-password" required value={password} onChange={(event) => setPassword(event.target.value)} />
              {error && <Alert tone="danger" title={error} />}
              <Button fullWidth type="submit" loading={enroll.isPending} disabled={!status.data.enabled || busy}>إرسال رابط توثيق البريد</Button>
            </form>
          )}
          {(ready || pending) && !editing && (
            <Button variant="ghost" disabled={!status.data.enabled || busy} onClick={() => setEditing(true)}>تغيير بريد الاسترداد بعد التحقق من كلمة المرور</Button>
          )}
          {enroll.isError && <ErrorState error={enroll.error} />}
          {resend.isError && <ErrorState error={resend.error} />}
          {ready && <Link to="/parent" className="inline-flex min-h-11 items-center font-bold text-teal-800">الانتقال إلى أبنائي</Link>}
        </>
      )}
      <div className="flex flex-wrap items-center gap-3 border-t border-slate-200 pt-4">
        {!!me.data?.memberships.length && (
          <SpaceSwitchButton destination={me.data.active_school ? "/workspace" : "/select-school"}>مساحة العمل</SpaceSwitchButton>
        )}
        <Button variant="ghost" onClick={() => void logout().then(() => navigate("/login", { replace: true }))}>تسجيل الخروج</Button>
      </div>
    </RecoveryLayout>
  );
}

export function VerifyRecoveryEmailPage() {
  const token = useRecoveryFragment();
  const me = useMe();
  const queryClient = useQueryClient();
  const logout = useLogout();
  const navigate = useNavigate();
  const checked = useRef(false);
  const check = useMutation({ mutationFn: () => checkRecoveryEmail(token), gcTime: 0 });
  const checkToken = check.mutate;
  const verify = useMutation({
    mutationFn: () => verifyRecoveryEmail(token),
    gcTime: 0,
    onMutate: () => ({ ownerId: me.data?.id }),
    onSuccess: async (value, _variables, context) => {
      const ownerId = context?.ownerId;
      await queryClient.cancelQueries({ queryKey: parentKey(ownerId) });
      queryClient.removeQueries({ queryKey: parentKey(ownerId) });
      await purgeSensitiveBrowserCaches({ preserveAttendanceDrafts: true });
      // Verification changes no session. Never restore a stale user after another login.
      if (ownerId && queryClient.getQueryData<Me>(ME_QUERY_KEY)?.id === ownerId) {
        queryClient.setQueryData(recoveryEmailKey(ownerId), value);
      }
    },
  });
  useEffect(() => {
    if (token && me.isSuccess && !checked.current) {
      checked.current = true;
      checkToken();
    }
  }, [token, me.isSuccess, checkToken]);
  const needsLogin = me.isError && me.error instanceof ApiError && (me.error.status === 401 || me.error.status === 403);
  return (
    <RecoveryLayout title="توثيق بريد الاسترداد">
      {!token && <Alert tone="warning" title="افتح رابط التحقق الأصلي">اطلب رابطاً حديثاً من إعدادات بريد الاسترداد عند الحاجة.</Alert>}
      {token && me.isPending && <PageSkeleton label="جارٍ التحقق من الجلسة" />}
      {needsLogin && (
        <>
          <Alert title="سجل الدخول إلى الحساب صاحب الطلب">بعد تسجيل الدخول برقم الجوال وكلمة المرور، افتح رابط البريد مرة أخرى لإكمال التوثيق.</Alert>
          <Link to="/login" className="inline-flex min-h-11 items-center font-bold text-teal-800">تسجيل الدخول</Link>
        </>
      )}
      {me.isError && !needsLogin && <ErrorState error={me.error} />}
      {check.isPending && <PageSkeleton label="جارٍ فحص رابط التحقق" />}
      {check.isError && <ErrorState error={check.error} />}
      {check.isSuccess && me.isSuccess && !verify.isSuccess && (
        <>
          <p className="text-sm leading-7 text-slate-600">اضغط لتأكيد ملكيتك للبريد الذي استلم هذا الرابط. لن تُستخدم الرسائل إلا لتوثيق البريد واستعادة كلمة المرور.</p>
          <Button fullWidth loading={verify.isPending} onClick={() => verify.mutate()}>توثيق البريد الإلكتروني</Button>
        </>
      )}
      {verify.isError && <ErrorState error={verify.error} />}
      {verify.isSuccess && (
        <>
          <Alert tone="success" title="تم توثيق بريد الاسترداد" live />
          <Link to="/parent" className="inline-flex min-h-11 items-center font-bold text-teal-800">الانتقال إلى أبنائي</Link>
        </>
      )}
      {me.isSuccess && <Link to="/parent/recovery-email" className="inline-flex min-h-11 items-center text-sm font-bold text-teal-800">إعدادات بريد الاسترداد</Link>}
      {me.isSuccess && !verify.isSuccess && <Button variant="ghost" onClick={() => void logout().then(() => navigate("/login", { replace: true }))}>تسجيل الخروج لاستخدام الحساب صاحب الطلب</Button>}
    </RecoveryLayout>
  );
}

export function ForgotParentPasswordPage() {
  const [mobile, setMobile] = useState("");
  const [error, setError] = useState("");
  const request = useMutation({
    mutationFn: () => requestParentPasswordRecovery(toCanonicalMobile(mobile) ?? ""),
    gcTime: 0,
  });
  function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    if (!toCanonicalMobile(mobile)) {
      setError("أدخل رقم الجوال السعودي المسجل للدخول.");
      return;
    }
    request.mutate();
  }
  return (
    <RecoveryLayout title="استعادة كلمة المرور">
      <p className="text-sm leading-7 text-slate-600">تُرسل الاستعادة إلى بريد الحساب الموثق. يبقى تسجيل الدخول برقم الجوال وكلمة المرور.</p>
      {request.isSuccess ? <Alert tone="success" title={RECOVERY_REQUEST_MESSAGE} live /> : (
        <form className="space-y-4" onSubmit={submit} noValidate>
          <TextField label="رقم الجوال المسجل للدخول" type="tel" inputMode="tel" dir="ltr" autoComplete="tel" required maxLength={20} value={mobile} error={error} onChange={(event) => setMobile(toLatinDigits(event.target.value))} />
          {request.isError && <ErrorState error={request.error} />}
          <Button type="submit" fullWidth loading={request.isPending}>إرسال رابط الاستعادة</Button>
        </form>
      )}
      <Link to="/login" className="inline-flex min-h-11 items-center font-bold text-teal-800">العودة إلى تسجيل الدخول</Link>
    </RecoveryLayout>
  );
}

export function ResetParentPasswordPage() {
  const token = useRecoveryFragment();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const logout = useLogout();
  const checked = useRef(false);
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [sessionPresent, setSessionPresent] = useState(false);
  const [sessionUnavailable, setSessionUnavailable] = useState(false);
  const check = useMutation({ mutationFn: () => checkParentPasswordRecovery(token), gcTime: 0 });
  const checkToken = check.mutate;
  const complete = useMutation({
    mutationFn: () => completeParentPasswordRecovery(token, password, confirm),
    gcTime: 0,
    onMutate: () => ({ sessionId: queryClient.getQueryData<Me>(ME_QUERY_KEY)?.id }),
    onSuccess: async (_value, _variables, context) => {
      setPassword("");
      setConfirm("");
      const previousId = context?.sessionId;
      if (queryClient.getQueryData<Me>(ME_QUERY_KEY)?.id !== previousId) return;
      try {
        // Refresh the current session only. This never signs in the reset-token owner.
        const current = await queryClient.fetchQuery({
          queryKey: ME_QUERY_KEY,
          queryFn: ({ signal }) => getMe(signal),
          staleTime: 0,
          retry: false,
        });
        if (queryClient.getQueryData<Me>(ME_QUERY_KEY)?.id !== current.id) return;
        if (current.id !== previousId) {
          await queryClient.cancelQueries({ predicate: (query) => query.queryKey[0] !== "me" });
          queryClient.removeQueries({ predicate: (query) => query.queryKey[0] !== "me" });
        }
        await purgeSensitiveBrowserCaches({ preserveAttendanceDrafts: true });
        setSessionPresent(true);
      } catch (failure) {
        if (isCancelledError(failure) || queryClient.getQueryData<Me>(ME_QUERY_KEY)?.id !== previousId) return;
        queryClient.clear();
        await purgeSensitiveBrowserCaches({ preserveAttendanceDrafts: true });
        if (failure instanceof ApiError && (failure.status === 401 || failure.status === 403)) {
          if (previousId) navigate("/login", { replace: true, state: { parentPasswordRecovered: true } });
        } else {
          setSessionUnavailable(true);
        }
      }
    },
  });
  useEffect(() => {
    if (token && !checked.current) {
      checked.current = true;
      checkToken();
    }
  }, [token, checkToken]);
  function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    if (password.length < 8 || /^[0-9٠-٩]+$/.test(password)) {
      setError("اختر كلمة مرور آمنة من 8 أحرف على الأقل.");
      return;
    }
    if (password !== confirm) {
      setError("تأكيد كلمة المرور لا يطابق كلمة المرور الجديدة.");
      return;
    }
    complete.mutate();
  }
  return (
    <RecoveryLayout title="إنشاء كلمة مرور جديدة">
      {!token && <Alert tone="warning" title="افتح رابط الاستعادة الأصلي">يمكنك طلب رابط حديث من صفحة استعادة كلمة المرور.</Alert>}
      {check.isPending && <PageSkeleton label="جارٍ فحص رابط الاستعادة" />}
      {check.isError && <ErrorState error={check.error} />}
      {check.isSuccess && !complete.isSuccess && (
        <form className="space-y-4" onSubmit={submit} noValidate>
          <p className="text-sm leading-7 text-slate-600">ستُبطل الجلسات السابقة بعد حفظ كلمة المرور. تبقى علاقات أبنائك وعضوياتك محفوظة.</p>
          <PasswordInput label="كلمة المرور الجديدة" autoComplete="new-password" required value={password} onChange={(event) => setPassword(event.target.value)} />
          <PasswordInput label="تأكيد كلمة المرور الجديدة" autoComplete="new-password" required value={confirm} onChange={(event) => setConfirm(event.target.value)} />
          {error && <Alert tone="danger" title={error} />}
          {complete.isError && <ErrorState error={complete.error} />}
          <Button type="submit" fullWidth loading={complete.isPending}>حفظ كلمة المرور الجديدة</Button>
        </form>
      )}
      {complete.isSuccess && (
        <Alert tone="success" title="تم تغيير كلمة المرور" live>
          <span className="inline-flex items-center gap-2"><ShieldCheck aria-hidden size={17} />سجل الدخول برقم الجوال نفسه وكلمة المرور الجديدة.</span>
        </Alert>
      )}
      {complete.isSuccess && sessionPresent && (
        <>
          <Alert title="المتصفح مسجل بحساب">استعادة كلمة المرور لم تغيّر الحساب المستخدم في هذا المتصفح. يمكنك تسجيل الخروج للدخول بحساب آخر.</Alert>
          <Button variant="secondary" onClick={() => void logout().then(() => navigate("/login", { replace: true }))}>تسجيل الخروج للدخول بحساب آخر</Button>
        </>
      )}
      {complete.isSuccess && sessionUnavailable && <Alert tone="warning" title="تعذر التحقق من جلسة المتصفح">تم حفظ كلمة المرور. سجل الدخول مجدداً للمتابعة.</Alert>}
      <Link to="/login" className="inline-flex min-h-11 items-center font-bold text-teal-800">تسجيل الدخول</Link>
      {!complete.isSuccess && <Link to="/forgot-password" className="inline-flex min-h-11 items-center text-sm font-bold text-teal-800">طلب رابط استعادة جديد</Link>}
    </RecoveryLayout>
  );
}
