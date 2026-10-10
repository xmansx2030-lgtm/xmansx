import { useMutation } from "@tanstack/react-query";
import { ArrowUpLeft, KeyRound, Mail, ShieldCheck, UserRound } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { changeAccountPassword } from "@/api/auth";
import { Alert } from "@/components/Alert";
import { Button } from "@/components/Button";
import { ErrorState } from "@/components/ErrorState";
import { PageHeader } from "@/components/PageHeader";
import { PasswordInput } from "@/components/PasswordInput";
import { useMe } from "@/features/auth/useMe";
import { RECOVERY_EMAIL_DESCRIPTION } from "@/features/parent/recoveryEmail";
import { roleLabels } from "@/utils/roles";

const surface = "min-w-0 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6";

export function AccountPage() {
  const me = useMe();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const action = useMutation({
    mutationFn: () => changeAccountPassword(current, next, confirm),
    onSuccess: () => { setCurrent(""); setNext(""); setConfirm(""); },
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    if (action.isPending) return;
    action.reset();
    setError("");
    if (!current || next.length < 8 || /^[0-9٠-٩]+$/.test(next) || next === current) {
      setError("أدخل كلمة المرور الحالية واختر كلمة مرور جديدة من 8 أحرف على الأقل، وليست أرقامًا فقط.");
      return;
    }
    if (next !== confirm) { setError("تأكيد كلمة المرور غير مطابق."); return; }
    action.mutate();
  }

  if (!me.isSuccess) return null;

  return <div className="ds-page" data-testid="account-page">
    <PageHeader icon={UserRound} eyebrow="الحساب الشخصي" title="إدارة الحساب"
      description="راجع بيانات دخولك وأمّن حسابك بكلمة مرور جديدة وبريد للاسترداد." />
    <div className="grid min-w-0 items-start gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
      <div className="min-w-0 space-y-5">
        <section className={surface} aria-labelledby="account-details-title">
          <h2 id="account-details-title" className="flex items-center gap-2 text-lg font-bold"><UserRound aria-hidden size={20} className="text-teal-700" />بيانات الحساب</h2>
          <dl className="mt-5 grid gap-4 text-sm">
            <div><dt className="text-slate-500">الاسم</dt><dd className="mt-1 break-words font-bold text-slate-900">{me.data.name}</dd></div>
            <div><dt className="text-slate-500">جوال الدخول</dt><dd className="mt-1 w-fit font-bold text-slate-900" dir="ltr">{me.data.mobile}</dd></div>
            <div><dt className="text-slate-500">المدرسة الحالية</dt><dd className="mt-1 break-words font-bold text-slate-900">{me.data.active_school?.name}</dd></div>
            <div><dt className="text-slate-500">الدور في المدرسة</dt><dd className="mt-1 font-bold text-slate-900">{roleLabels(me.data.roles, me.data.active_school?.school_type)}</dd></div>
          </dl>
        </section>
        {me.data.school_recovery_email_enabled && <section className={surface} aria-labelledby="account-email-title">
          <h2 id="account-email-title" className="flex items-center gap-2 text-lg font-bold"><Mail aria-hidden size={20} className="text-teal-700" />بريد استرداد الحساب</h2>
          <p className="mt-3 text-sm leading-7 text-slate-600">{RECOVERY_EMAIL_DESCRIPTION}</p>
          <Link to="/account/recovery-email?returnTo=%2Faccount" className="mt-4 inline-flex min-h-11 items-center justify-center gap-2 rounded-xl border border-teal-200 bg-teal-50 px-4 text-sm font-bold text-teal-900 hover:bg-teal-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-700">
            إدارة بريد الاسترداد<ArrowUpLeft aria-hidden size={17} />
          </Link>
        </section>}
      </div>
      <section className={surface} aria-labelledby="account-password-title">
        <h2 id="account-password-title" className="flex items-center gap-2 text-lg font-bold"><KeyRound aria-hidden size={20} className="text-teal-700" />تغيير كلمة المرور</h2>
        <p className="mt-3 text-sm leading-7 text-slate-600">كلمة المرور تخص حسابك في جميع المدارس المرتبطة به. بعد الحفظ تبقى جلستك الحالية ويُطلب تسجيل الدخول مجددًا في الجلسات الأخرى.</p>
        <form onSubmit={submit} className="mt-5 space-y-4">
          <PasswordInput label="كلمة المرور الحالية" autoComplete="current-password" required maxLength={128} disabled={action.isPending} value={current} onChange={event => { setCurrent(event.target.value); action.reset(); setError(""); }} />
          <PasswordInput label="كلمة المرور الجديدة" autoComplete="new-password" required minLength={8} maxLength={128} disabled={action.isPending} value={next} onChange={event => { setNext(event.target.value); action.reset(); setError(""); }} description="8 أحرف على الأقل، ليست رقم جوالك أو أرقامًا فقط، ومختلفة عن الحالية." />
          <PasswordInput label="تأكيد كلمة المرور الجديدة" autoComplete="new-password" required maxLength={128} disabled={action.isPending} value={confirm} onChange={event => { setConfirm(event.target.value); action.reset(); setError(""); }} />
          {error && <Alert tone="danger" title={error} live />}
          {action.isError && <ErrorState error={action.error} />}
          {action.isSuccess && <Alert tone="success" title={action.data.detail} live />}
          <Button type="submit" loading={action.isPending} loadingLabel="جارٍ حفظ كلمة المرور..."><ShieldCheck aria-hidden size={17} />حفظ كلمة المرور</Button>
        </form>
      </section>
    </div>
  </div>;
}
