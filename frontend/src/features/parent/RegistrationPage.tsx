import { useMutation, useQuery } from "@tanstack/react-query";
import { HeartHandshake } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";

import { ensureCsrfCookie } from "@/api/auth";
import { Alert } from "@/components/Alert";
import { Button } from "@/components/Button";
import { ErrorState } from "@/components/ErrorState";
import { SelectField, TextareaField } from "@/components/FormField";
import { TextField } from "@/components/TextField";
import { PageSkeleton } from "@/components/Skeleton";
import { toCanonicalMobile, toLatinDigits } from "@/features/auth/mobile";
import { withReturnTo } from "@/features/auth/returnTo";
import { normalizeRecoveryEmail, recoveryEmailError, RECOVERY_EMAIL_DESCRIPTION } from "@/features/parent/recoveryEmail";
import {
  getRegistration,
  getRegistrationStatus,
  registerParent,
} from "@/features/parent/api";

export function RegistrationPage() {
  const { schoolToken = "" } = useParams();
  const school = useQuery({
    queryKey: ["parent-public-school", schoolToken],
    queryFn: ({ signal }) => getRegistration(schoolToken, signal),
    retry: false,
  });
  const [name, setName] = useState("");
  const [mobile, setMobile] = useState("");
  const [email, setEmail] = useState("");
  const [emailError, setEmailError] = useState("");
  const [identifier, setIdentifier] = useState("");
  const [relationship, setRelationship] = useState("FATHER");
  const [error, setError] = useState("");
  const [receipt, setReceipt] = useState("");
  const [tracking, setTracking] = useState("");
  const [applicantNote, setApplicantNote] = useState("");
  const request = useMutation({
    mutationFn: async () => {
      await ensureCsrfCookie();
      return registerParent(schoolToken, {
        name: name.trim(),
        mobile: toCanonicalMobile(mobile) ?? "",
        email: normalizeRecoveryEmail(email),
        student_identifier: toLatinDigits(identifier.trim()),
        relationship_type: relationship,
      });
    },
    onSuccess: (result) => {
      setReceipt(result.receipt_token);
      setName("");
      setMobile("");
      setEmail("");
      setIdentifier("");
    },
  });
  const status = useMutation({
    mutationFn: async () => {
      await ensureCsrfCookie();
      return getRegistrationStatus(tracking.trim());
    },
  });
  const resubmit = useMutation({
    mutationFn: async () => {
      await ensureCsrfCookie();
      return getRegistrationStatus(tracking.trim(), applicantNote.trim());
    },
    onSuccess: (result) => {
      setApplicantNote("");
      status.reset();
      status.mutate();
      if (!result.status) return;
    },
  });
  function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    const invalidEmail = recoveryEmailError(email);
    setEmailError(invalidEmail);
    if (invalidEmail) return;
    if (!name.trim() || !identifier.trim() || !toCanonicalMobile(mobile)) {
      setError("أكمل الاسم ومعرف الطالب وأدخل رقم جوال سعودي صحيحاً.");
      return;
    }
    request.mutate();
  }
  return (
    <main className="auth-shell min-h-dvh overflow-x-hidden px-4 py-8 sm:py-12">
      <div className="auth-card mx-auto max-w-xl rounded-3xl p-5 sm:p-9">
        <span className="mb-4 grid size-12 place-items-center rounded-2xl bg-teal-50 text-teal-800">
          <HeartHandshake aria-hidden />
        </span>
        <h1 className="text-2xl font-black">بوابة أولياء الأمور</h1>
        {school.isPending && <PageSkeleton label="جارٍ تحميل بيانات المدرسة" />}
        {school.isError && <ErrorState error={school.error} />}
        {school.isSuccess && (
          <>
            <p className="mt-2 font-bold text-teal-800">
              {school.data.school_name}
            </p>
            <p className="my-4 text-sm leading-7 text-slate-600">
              قدّم طلب متابعة ابنك. تتحقق المدرسة من صفتك قبل اعتماد العلاقة
              وإرسال رابط التفعيل وتوثيق البريد إلى بريدك الإلكتروني.
            </p>
            {!school.data.enabled && (
              <Alert tone="warning" title="التسجيل غير متاح حالياً">
                تواصل مع إدارة المدرسة.
              </Alert>
            )}
            {request.isSuccess ? (
              <div className="space-y-4">
                <Alert
                  tone="success"
                  title="تم استلام طلبك، وستقوم المدرسة بمراجعته."
                  live
                />
                <TextField
                  label="رمز متابعة الطلب"
                  value={receipt}
                  readOnly
                  dir="ltr"
                  autoComplete="off"
                  description="احفظ الرمز في مكان آمن لمتابعة القرار دون إدخال بيانات الطالب."
                />
                <Button
                  variant="secondary"
                  onClick={() => void navigator.clipboard?.writeText(receipt)}
                >
                  نسخ رمز المتابعة
                </Button>
                <Button variant="ghost" onClick={() => request.reset()}>
                  تقديم طلب آخر
                </Button>
              </div>
            ) : (
              <form onSubmit={submit} className="space-y-4" noValidate>
                <TextField
                  label="اسم ولي الأمر"
                  autoComplete="name"
                  required
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  maxLength={150}
                />
                <TextField
                  label="رقم الجوال"
                  type="tel"
                  inputMode="tel"
                  dir="ltr"
                  autoComplete="tel"
                  required
                  value={mobile}
                  onChange={(e) => setMobile(toLatinDigits(e.target.value))}
                  maxLength={20}
                  description="تُقبل الأرقام العربية والصيغ 05 أو +966."
                />
                <TextField
                  label="البريد الإلكتروني"
                  type="email"
                  inputMode="email"
                  dir="ltr"
                  autoComplete="email"
                  required
                  maxLength={254}
                  value={email}
                  error={emailError}
                  description={RECOVERY_EMAIL_DESCRIPTION}
                  onChange={(event) => {
                    setEmail(event.target.value);
                    if (emailError) setEmailError(recoveryEmailError(event.target.value));
                  }}
                />
                <TextField
                  label="معرف الطالب المسجل لدى المدرسة"
                  required
                  autoComplete="off"
                  value={identifier}
                  onChange={(e) => setIdentifier(toLatinDigits(e.target.value))}
                  maxLength={30}
                  description="الهوية الوطنية أو الإقامة أو الجواز وفق السجل المدرسي."
                />
                <SelectField
                  label="صلة القرابة"
                  value={relationship}
                  onChange={(e) => setRelationship(e.target.value)}
                >
                  <option value="FATHER">الأب</option>
                  <option value="MOTHER">الأم</option>
                  <option value="GUARDIAN">ولي شرعي</option>
                  <option value="OTHER">أخرى</option>
                </SelectField>
                {error && <Alert tone="danger" title={error} />}
                {request.isError && <ErrorState error={request.error} />}
                <Button
                  type="submit"
                  fullWidth
                  loading={request.isPending}
                  disabled={!school.data.enabled}
                >
                  تقديم طلب تسجيل
                </Button>
              </form>
            )}
            <Link
              className="mt-5 inline-flex min-h-11 items-center font-bold text-teal-800"
              to={withReturnTo("/login", `/parent/register/${schoolToken}`)}
            >
              لدي حساب بالفعل
            </Link>
          </>
        )}
        <section className="mt-6 border-t border-slate-200 pt-5">
          <h2 className="font-bold">متابعة طلب سابق</h2>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (tracking.trim()) status.mutate();
            }}
            className="mt-3 space-y-3"
          >
            <TextField
              label="رمز المتابعة"
              dir="ltr"
              autoComplete="off"
              value={tracking}
              onChange={(e) => setTracking(e.target.value)}
              maxLength={150}
              required
            />
            <Button
              type="submit"
              variant="secondary"
              loading={status.isPending}
            >
              عرض حالة الطلب
            </Button>
            {status.isError && <ErrorState error={status.error} />}
            {status.isSuccess && <Alert title={status.data.message} live />}
            {status.data?.status === "NEEDS_INFO" && (
              <>
                <TextareaField
                  label="استكمال طلب التسجيل"
                  required
                  value={applicantNote}
                  onChange={(event) => setApplicantNote(event.target.value)}
                  maxLength={600}
                />
                <Button
                  loading={resubmit.isPending}
                  onClick={() => {
                    if (applicantNote.trim()) resubmit.mutate();
                  }}
                >
                  إرسال الاستكمال إلى المدرسة
                </Button>
                {resubmit.isError && <ErrorState error={resubmit.error} />}
              </>
            )}
          </form>
        </section>
      </div>
    </main>
  );
}
