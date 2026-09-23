import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight, Building2, Check, ChevronLeft, LockKeyhole, ShieldCheck,
  Sparkles, UserRound,
} from "lucide-react";
import { useMemo, useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router-dom";

import { ApiError } from "@/api/client";
import { purgeSensitiveBrowserCaches } from "@/app/cacheSafety";
import { Alert } from "@/components/Alert";
import { Button } from "@/components/Button";
import { PasswordInput } from "@/components/PasswordInput";
import { TextField } from "@/components/TextField";
import { toCanonicalMobile, toLatinDigits } from "@/features/auth/mobile";
import { ME_QUERY_KEY, useMe } from "@/features/auth/useMe";
import { getPublicPlans, registerSchool, type SchoolRegistrationInput } from "@/features/public/api";
import type { SchoolType } from "@/types/auth";
import { formatPlanDuration } from "@/utils/planDuration";

type FieldErrors = Partial<Record<keyof SchoolRegistrationInput, string>>;

function firstDetail(details: Record<string, unknown>, key: keyof SchoolRegistrationInput) {
  const value = details[key];
  if (typeof value === "string") return value;
  if (Array.isArray(value) && typeof value[0] === "string") return value[0];
  return undefined;
}

export function RegisterSchoolPage() {
  const me = useMe();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [searchParams] = useSearchParams();
  const requestedPlan = Number(searchParams.get("plan"));
  const plans = useQuery({
    queryKey: ["public-plans"],
    queryFn: ({ signal }) => getPublicPlans(signal),
    select: (catalog) => catalog.filter((plan) => plan.can_self_register),
    staleTime: 5 * 60_000,
  });
  const [step, setStep] = useState<1 | 2>(1);
  const [schoolName, setSchoolName] = useState("");
  const [schoolType, setSchoolType] = useState<SchoolType>("BOYS");
  const [planId, setPlanId] = useState<number | null>(Number.isFinite(requestedPlan) && requestedPlan > 0 ? requestedPlan : null);
  const [managerName, setManagerName] = useState("");
  const [mobile, setMobile] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [termsAccepted, setTermsAccepted] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});

  const effectivePlanId = plans.data?.some((plan) => plan.id === planId)
    ? planId
    : plans.data?.[0]?.id ?? null;
  const selectedPlan = plans.data?.find((plan) => plan.id === effectivePlanId);
  const passwordChecks = useMemo(() => [
    { label: "8 أحرف على الأقل", valid: password.length >= 8 },
    { label: "ليست أرقامًا فقط", valid: password.length > 0 && !/^\d+$/.test(password) },
    { label: "تأكيدها مطابق", valid: confirmPassword.length > 0 && password === confirmPassword },
  ], [confirmPassword, password]);

  const mutation = useMutation({
    mutationFn: (input: SchoolRegistrationInput) => registerSchool(input),
    onSuccess: async (data) => {
      queryClient.clear();
      await purgeSensitiveBrowserCaches();
      queryClient.setQueryData(ME_QUERY_KEY, data);
      navigate("/workspace", { replace: true });
    },
    onError: (error) => {
      if (!(error instanceof ApiError)) return;
      setFieldErrors({
        school_name: firstDetail(error.details, "school_name"),
        school_type: firstDetail(error.details, "school_type"),
        manager_name: firstDetail(error.details, "manager_name"),
        manager_mobile: firstDetail(error.details, "manager_mobile"),
        password: firstDetail(error.details, "password"),
        confirm_password: firstDetail(error.details, "confirm_password"),
        plan_id: firstDetail(error.details, "plan_id"),
        terms_accepted: firstDetail(error.details, "terms_accepted"),
      });
    },
  });

  if (me.isSuccess) {
    if (me.data.must_change_password) return <Navigate to="/change-password" replace />;
    if (me.data.is_platform_admin) return <Navigate to="/platform" replace />;
    return <Navigate to={me.data.active_school ? "/workspace" : "/select-school"} replace />;
  }

  function nextStep() {
    const errors: FieldErrors = {};
    if (schoolName.trim().length < 3) errors.school_name = "أدخل اسم المدرسة من 3 أحرف على الأقل.";
    if (effectivePlanId === null) errors.plan_id = "اختر الباقة المناسبة للبدء.";
    setFieldErrors(errors);
    if (Object.keys(errors).length === 0) setStep(2);
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const canonicalMobile = toCanonicalMobile(mobile);
    const errors: FieldErrors = {};
    if (managerName.trim().length < 3) errors.manager_name = "أدخل اسم مدير المدرسة من 3 أحرف على الأقل.";
    if (!canonicalMobile) errors.manager_mobile = "أدخل رقم جوال سعودي صحيحًا.";
    if (password.length < 8 || /^\d+$/.test(password)) errors.password = "استخدم 8 أحرف على الأقل، ولا تجعلها أرقامًا فقط.";
    if (password !== confirmPassword) errors.confirm_password = "تأكيد كلمة المرور غير مطابق.";
    if (!termsAccepted) errors.terms_accepted = "وافق على الإقرار لإكمال التسجيل.";
    if (effectivePlanId === null) errors.plan_id = "اختر باقة متاحة.";
    setFieldErrors(errors);
    if (Object.keys(errors).length > 0 || !canonicalMobile || effectivePlanId === null) return;
    mutation.mutate({
      school_name: schoolName.trim(), school_type: schoolType,
      manager_name: managerName.trim(), manager_mobile: canonicalMobile,
      password, confirm_password: confirmPassword, plan_id: effectivePlanId,
      terms_accepted: termsAccepted,
    });
  }

  const apiError = mutation.error instanceof ApiError ? mutation.error : null;

  return (
    <main className="registration-shell min-h-dvh bg-[#061916] px-4 py-5 text-slate-900 sm:px-6 sm:py-8 lg:px-8">
      <div className="mx-auto flex max-w-7xl items-center justify-between gap-4">
        <Link to="/" className="flex min-h-11 items-center gap-3 text-white" aria-label="العودة إلى الصفحة الرئيسية"><span className="grid size-10 place-items-center rounded-xl bg-teal-400 text-slate-950"><Building2 size={20} /></span><span><strong className="block text-sm font-black">منصة المواظبة</strong><span className="text-[10px] text-slate-400">تسجيل مدرسة جديدة</span></span></Link>
        <Link to="/login" className="inline-flex min-h-11 items-center gap-2 rounded-xl px-3 text-sm font-bold text-slate-300 hover:bg-white/5 hover:text-white">لديك حساب؟ <span className="text-teal-300">سجّل الدخول</span></Link>
      </div>

      <div className="mx-auto mt-8 grid max-w-7xl gap-8 lg:mt-12 lg:grid-cols-[0.78fr_1.22fr] lg:items-start">
        <aside className="hidden pt-8 text-white lg:block">
          <p className="text-sm font-black text-teal-300">تشغيلك يبدأ من هنا</p>
          <h1 className="mt-5 text-4xl font-black leading-[1.3]">مدرستك على المنصة<br />خلال خطوات واضحة.</h1>
          <p className="mt-5 max-w-md text-base leading-8 text-slate-400">أنشئ الحساب بنفسك، وابدأ تجربة الباقة، ثم انتقل مباشرة إلى لوحة جاهزية المدرسة لإكمال الإعداد.</p>
          <div className="mt-10 space-y-5">
            {[{ icon: Sparkles, title: "تجربة تبدأ فورًا", text: "لا بطاقة دفع ولا انتظار تفعيل يدوي." }, { icon: ShieldCheck, title: "مساحة مستقلة وآمنة", text: "بيانات وصلاحيات مدرستك معزولة بالكامل." }, { icon: UserRound, title: "أنت مدير المدرسة", text: "الحساب الأول يملك أدوات الإعداد والإدارة." }].map((item) => { const Icon = item.icon; return <div key={item.title} className="flex gap-4"><span className="grid size-11 shrink-0 place-items-center rounded-xl border border-white/10 bg-white/5 text-teal-300"><Icon size={20} /></span><div><h2 className="text-sm font-black">{item.title}</h2><p className="mt-1 text-xs leading-6 text-slate-400">{item.text}</p></div></div>; })}
          </div>
        </aside>

        <section className="overflow-hidden rounded-[2rem] border border-white/10 bg-white shadow-[0_35px_90px_rgba(0,0,0,0.3)]">
          <div className="border-b border-slate-100 px-5 py-6 sm:px-9">
            <div className="flex items-center justify-between gap-4"><div><p className="text-xs font-black text-teal-700">الخطوة {step} من 2</p><h1 className="mt-1 text-2xl font-black">{step === 1 ? "بيانات المدرسة والباقة" : "حساب مدير المدرسة"}</h1></div><span className="grid size-11 place-items-center rounded-2xl bg-teal-50 text-teal-800">{step === 1 ? <Building2 size={21} /> : <LockKeyhole size={21} />}</span></div>
            <div className="mt-5 grid grid-cols-2 gap-2" aria-label="تقدم التسجيل"><span className="h-1.5 rounded-full bg-teal-600" /><span className={`h-1.5 rounded-full ${step === 2 ? "bg-teal-600" : "bg-slate-200"}`} /></div>
          </div>

          <form onSubmit={handleSubmit} className="p-5 sm:p-9" noValidate>
            {step === 1 ? <>
              <TextField label="اسم المدرسة" name="school_name" placeholder="مثال: ثانوية الإتقان" autoComplete="organization" maxLength={200} required value={schoolName} onChange={(event) => setSchoolName(event.target.value)} error={fieldErrors.school_name} className="mb-6" />
              <fieldset className="mb-7"><legend className="mb-3 text-sm font-bold text-slate-700">نوع المدرسة <span className="text-red-600">*</span></legend><div className="grid grid-cols-2 gap-3">{(["BOYS", "GIRLS"] as SchoolType[]).map((type) => <label key={type} className={`flex min-h-14 cursor-pointer items-center gap-3 rounded-xl border px-4 transition ${schoolType === type ? "border-teal-500 bg-teal-50 ring-2 ring-teal-100" : "border-slate-200 hover:border-slate-300"}`}><input type="radio" name="school_type" value={type} checked={schoolType === type} onChange={() => setSchoolType(type)} className="size-4" /><span className="font-bold">{type === "BOYS" ? "بنين" : "بنات"}</span></label>)}</div></fieldset>
              <fieldset><legend className="mb-3 text-sm font-bold text-slate-700">اختر الباقة <span className="text-red-600">*</span></legend>{plans.isPending ? <div className="h-28 animate-pulse rounded-2xl bg-slate-100" /> : plans.data && plans.data.length > 0 ? <div className="grid gap-3 sm:grid-cols-2">{plans.data.map((plan) => { const isFree = Number(plan.price_amount) === 0; const duration = formatPlanDuration(plan.duration_value, plan.duration_unit); return <label key={plan.id} className={`relative flex min-h-36 cursor-pointer flex-col rounded-2xl border p-4 transition ${effectivePlanId === plan.id ? "border-teal-500 bg-teal-50 ring-2 ring-teal-100" : "border-slate-200 hover:border-slate-300"}`}><input type="radio" name="plan_id" value={plan.id} checked={effectivePlanId === plan.id} onChange={() => setPlanId(plan.id)} className="sr-only" /><span className="flex items-start justify-between gap-3"><strong>{plan.name}</strong>{effectivePlanId === plan.id && <span className="grid size-6 place-items-center rounded-full bg-teal-700 text-white"><Check size={14} /></span>}</span><span className="mt-2 text-sm font-black text-teal-800">مدة الباقة: {duration}</span><span className="mt-1 text-xs leading-5 text-slate-500">{isFree ? "استخدام مجاني طوال مدة الباقة" : `${plan.trial_days.toLocaleString("ar-SA")} يومًا للتجربة`}</span>{plan.one_time_per_school && <span className="mt-1 text-xs font-black text-amber-700">مرة واحدة فقط لكل مدرسة</span>}<span className="mt-auto pt-3 text-sm font-black text-teal-800">{isFree ? "مجانية" : `${Number(plan.price_amount).toLocaleString("ar-SA")} ${plan.currency}`}</span></label>; })}</div> : <Alert tone="warning" title="لا توجد باقة متاحة">التسجيل الذاتي متوقف مؤقتًا. تواصل مع الدعم للبدء.</Alert>}{fieldErrors.plan_id && <p role="alert" className="mt-2 text-sm text-red-700">{fieldErrors.plan_id}</p>}</fieldset>
              <Button type="button" size="lg" fullWidth className="mt-8" onClick={nextStep} disabled={plans.isPending || !plans.data?.length}>متابعة إلى حساب المدير <ChevronLeft size={18} /></Button>
            </> : <>
              <div className="mb-6 rounded-2xl border border-teal-100 bg-teal-50/70 p-4"><p className="text-xs font-bold text-teal-800">المدرسة المختارة</p><div className="mt-1 flex flex-wrap items-center justify-between gap-2"><strong className="text-sm">{schoolName}</strong><span className="rounded-full bg-white px-3 py-1 text-xs font-bold text-teal-800">{selectedPlan?.name}</span></div></div>
              <div className="grid gap-5 sm:grid-cols-2"><TextField label="اسم مدير المدرسة" name="manager_name" autoComplete="name" placeholder="الاسم الكامل" maxLength={150} required value={managerName} onChange={(event) => setManagerName(event.target.value)} error={fieldErrors.manager_name} /><TextField label="رقم الجوال" name="manager_mobile" type="tel" inputMode="tel" dir="ltr" autoComplete="tel" placeholder="05XXXXXXXX" maxLength={20} required value={mobile} onChange={(event) => setMobile(toLatinDigits(event.target.value))} error={fieldErrors.manager_mobile} /></div>
              <div className="mt-5 grid gap-5 sm:grid-cols-2"><PasswordInput label="كلمة المرور" name="password" autoComplete="new-password" required value={password} onChange={(event) => setPassword(event.target.value)} error={fieldErrors.password} /><PasswordInput label="تأكيد كلمة المرور" name="confirm_password" autoComplete="new-password" required value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} error={fieldErrors.confirm_password} /></div>
              <ul className="mt-4 flex flex-wrap gap-x-5 gap-y-2">{passwordChecks.map((check) => <li key={check.label} className={`flex items-center gap-1.5 text-xs font-semibold ${check.valid ? "text-emerald-700" : "text-slate-400"}`}><span className={`grid size-5 place-items-center rounded-full ${check.valid ? "bg-emerald-50" : "bg-slate-100"}`}><Check size={12} /></span>{check.label}</li>)}</ul>
              <label className={`mt-6 flex cursor-pointer items-start gap-3 rounded-xl border p-4 ${fieldErrors.terms_accepted ? "border-red-300 bg-red-50" : "border-slate-200 bg-slate-50"}`}><input type="checkbox" checked={termsAccepted} onChange={(event) => setTermsAccepted(event.target.checked)} className="mt-0.5 size-5 shrink-0" /><span className="text-sm leading-6 text-slate-600">أقر بصحة بيانات المدرسة، وأوافق على استخدامها لإنشاء الحساب وتشغيل الخدمة.</span></label>{fieldErrors.terms_accepted && <p role="alert" className="mt-2 text-sm text-red-700">{fieldErrors.terms_accepted}</p>}
              {apiError && <Alert tone="danger" title="تعذر إنشاء المدرسة" className="mt-5">{apiError.message}</Alert>}
              <div className="mt-7 flex flex-col-reverse gap-3 sm:flex-row"><Button type="button" variant="secondary" size="lg" className="sm:w-36" disabled={mutation.isPending} onClick={() => { setStep(1); setFieldErrors({}); }}><ArrowRight size={18} /> رجوع</Button><Button type="submit" size="lg" fullWidth loading={mutation.isPending} loadingLabel="جارٍ إنشاء مدرستك...">{Number(selectedPlan?.price_amount) === 0 ? "إنشاء المدرسة مجانًا" : "إنشاء المدرسة وبدء التجربة"} <Sparkles size={18} /></Button></div>
              <p className="mt-5 flex items-center justify-center gap-2 text-center text-xs text-slate-400"><ShieldCheck size={15} /> اتصال آمن، ولن نطلب بيانات طلاب في هذه الخطوة</p>
            </>}
          </form>
        </section>
      </div>
    </main>
  );
}
